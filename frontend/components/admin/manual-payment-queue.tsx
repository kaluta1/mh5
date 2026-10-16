'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { adminErrorText } from '@/lib/admin-security'
import { throwIfApiError } from '@/lib/http-error'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  EVIDENCE_MIN_LENGTH,
  MANUAL_PAYMENTS_URL,
  allowedActions,
  manualPaymentActionUrl,
  validDecisionReason,
  validEvidence,
  type ManualPayment,
  type ManualPaymentList,
} from '@/lib/manual-payments'

type Mode = 'confirm' | 'reject' | 'cancel'

/**
 * Admin > Mark as paid: payments recorded by hand that wait for a SECOND
 * administrator. The administrator who recorded one can only withdraw it;
 * another authorised administrator confirms (evidence reference) or rejects it.
 */
export default function ManualPaymentQueue({ refreshKey = 0, onChanged }: { refreshKey?: number; onChanged?: () => void }) {
  const [data, setData] = useState<ManualPaymentList | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [active, setActive] = useState<{ id: number; mode: Mode } | null>(null)
  const [text, setText] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await api.get(MANUAL_PAYMENTS_URL, { params: { status: 'REQUESTED' } })
      throwIfApiError(res, 'The manual payments could not be loaded.')
      setData(res.data)
    } catch (e: any) {
      setError(adminErrorText(e, 'The manual payments could not be loaded.'))
    }
  }, [])

  useEffect(() => { void load() }, [load, refreshKey])

  const open = (id: number, mode: Mode) => {
    setActive({ id, mode })
    setText('')
    setPassword('')
    setError('')
    setNotice('')
  }

  const submit = async () => {
    if (!active) return
    const sentPassword = password
    setPassword('')
    setBusy(true)
    setError('')
    try {
      const body = active.mode === 'confirm'
        ? { current_password: sentPassword, evidence_reference: text.trim() }
        : { current_password: sentPassword, note: text.trim() }
      const res = await api.post(manualPaymentActionUrl(active.id, active.mode), body)
      throwIfApiError(res, 'The action was refused.')
      setNotice(active.mode === 'confirm'
        ? (res.data?.status === 'superseded' ? 'The payment provider had already confirmed this payment.' : 'Payment confirmed and credited.')
        : active.mode === 'reject' ? 'Payment rejected. Nothing was credited.' : 'Request withdrawn. Nothing was credited.')
      setActive(null)
      setText('')
      onChanged?.()
      await load()
    } catch (e: any) {
      setError(adminErrorText(e, 'The action was refused.'))
    } finally {
      setBusy(false)
    }
  }

  const items = data?.items ?? []
  const valid = active?.mode === 'confirm' ? validEvidence(text) : validDecisionReason(text)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Awaiting a second administrator</CardTitle>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          A payment recorded by hand is credited only after a different administrator confirms that the money was
          received.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length === 0 && <p className="text-sm text-gray-500" data-testid="manual-payments-empty">Nothing is waiting.</p>}
        {items.map((item: ManualPayment) => {
          const can = allowedActions(item, data!.current_admin_id, data!.can_decide)
          const member = item.member?.full_name || item.member?.username || item.member?.email || `#${item.member_id}`
          return (
            <div key={item.id} className="rounded-lg border p-3 space-y-2" data-testid={`manual-payment-${item.id}`}>
              <div className="flex flex-wrap justify-between gap-2 text-sm">
                <span className="font-medium">{member} · {item.product_code} · {item.amount} {item.currency}</span>
                <span className="text-gray-500">recorded by admin #{item.requested_by}</span>
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-400">{item.request_reason}</p>
              {item.verify_identity_requested && (
                <p className="text-xs text-amber-700 dark:text-amber-300">Also marks the member's identity as verified on confirmation.</p>
              )}
              {can.waitingForSecondAdmin && (
                <p className="text-xs text-gray-500">You recorded this payment: a second administrator has to confirm it.</p>
              )}
              <div className="flex flex-wrap gap-2">
                {can.confirm && <Button size="sm" onClick={() => open(item.id, 'confirm')}>Confirm receipt</Button>}
                {can.reject && <Button size="sm" variant="outline" onClick={() => open(item.id, 'reject')}>Reject</Button>}
                {can.cancel && <Button size="sm" variant="outline" onClick={() => open(item.id, 'cancel')}>Withdraw</Button>}
              </div>
              {active?.id === item.id && (
                <div className="space-y-2 pt-2 border-t">
                  <label htmlFor={`mp-text-${item.id}`} className="text-sm font-medium block">
                    {active.mode === 'confirm' ? 'Where the money was received (transaction id, bank reference)' : 'Reason'}
                  </label>
                  <Input id={`mp-text-${item.id}`} value={text} maxLength={active.mode === 'confirm' ? 255 : 1000}
                    onChange={(e) => setText(e.target.value)} />
                  {active.mode === 'confirm' && (
                    <p className="text-xs text-gray-500">At least {EVIDENCE_MIN_LENGTH} characters. Kept with the payment and in the audit trail.</p>
                  )}
                  <label htmlFor={`mp-password-${item.id}`} className="text-sm font-medium block">Your current password</label>
                  <Input id={`mp-password-${item.id}`} type="password" autoComplete="current-password" value={password}
                    onChange={(e) => setPassword(e.target.value)} />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => void submit()} disabled={busy || !password || !valid}>
                      {busy ? 'Working…' : active.mode === 'confirm' ? 'Confirm and credit' : active.mode === 'reject' ? 'Reject payment' : 'Withdraw request'}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setActive(null)} disabled={busy}>Close</Button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
        {notice && <p className="text-sm text-green-700 dark:text-green-300" role="status">{notice}</p>}
        {error && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>}
      </CardContent>
    </Card>
  )
}
