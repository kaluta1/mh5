'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { financeErrorText } from '@/lib/finance-admin'
import { KYC_ADMIN_FEE_URL, parseKycFeeInput, type KycAdminFeeView } from '@/lib/kyc-fee'
import { inputClass } from './admin-finance-ui'

/**
 * Admin > KYC: the Member KYC Verification Fee (USD).
 *
 * One figure: what a member pays MyHigh5 for one new verification attempt.
 * 0 = free KYC. The server authorizes the change (manage_kyc_settings and
 * the administrator's current password) and keeps the amount of every payment
 * that already exists.
 */
export default function AdminKycFee() {
  const [view, setView] = useState<KycAdminFeeView | null>(null)
  const [amount, setAmount] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const res = await api.get(KYC_ADMIN_FEE_URL)
    if (res.status === 200) {
      setView(res.data)
      setAmount(res.data.amount)
    } else {
      setError('The KYC fee could not be loaded.')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const maximum = view ? Number(view.max_amount) : 1000
  const parsed = parseKycFeeInput(amount, maximum)
  const unchanged = !!view && parsed === view.amount
  const canChange = !!view?.can_change

  const save = async () => {
    if (!view || parsed === null) return
    setBusy(true)
    setError('')
    setNotice('')
    const sentPassword = password
    setPassword('')
    const res = await api.put(KYC_ADMIN_FEE_URL, {
      amount: parsed, current_password: sentPassword, expected_amount: view.amount,
    })
    if (res.status === 200) {
      setView(res.data)
      setAmount(res.data.amount)
      setNotice(res.data.is_free ? 'Saved. KYC is now free for members.' : `Saved. The fee is now ${res.data.amount} ${res.data.currency}.`)
    } else {
      setError(financeErrorText(res, 'The fee could not be saved.'))
      if (res.status === 409) void load()
    }
    setBusy(false)
  }

  return (
    <Card className="mb-8">
      <CardContent className="p-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Member KYC Verification Fee</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            What a member pays for one new verification attempt. Enter 0 to make KYC free. A change applies to
            attempts paid from now on; payments that already exist keep their amount.
          </p>
        </div>

        {view && (
          <p className="text-sm" data-testid="kyc-fee-current">
            Current fee:{' '}
            <span className="font-semibold">{view.is_free ? 'Free' : `${view.amount} ${view.currency}`}</span>
            {view.last_change?.at && (
              <span className="text-gray-500"> (last changed {new Date(view.last_change.at).toLocaleString()})</span>
            )}
          </p>
        )}

        {view && !canChange && (
          <p className="text-sm text-amber-700 dark:text-amber-300" role="status">
            You can view the fee. Changing it needs the {view.permission || 'manage_kyc_settings'} permission.
          </p>
        )}

        {view && canChange && (
          <div className="grid gap-4 sm:grid-cols-2 max-w-2xl">
            <div className="space-y-1">
              <label htmlFor="kyc-fee-amount" className="block text-sm font-medium">Fee (USD)</label>
              <input id="kyc-fee-amount" inputMode="decimal" className={inputClass} value={amount} disabled={busy}
                onChange={(e) => setAmount(e.target.value)} aria-invalid={parsed === null} />
              <p className="text-xs text-gray-500">
                {parsed === null
                  ? `Enter an amount from 0 to ${view.max_amount}, with at most two decimals.`
                  : parsed === '0.00' ? 'Members will not be asked to pay.' : 'Members see this fee before they start.'}
              </p>
            </div>
            <div className="space-y-1">
              <label htmlFor="kyc-fee-password" className="block text-sm font-medium">Your current password</label>
              <input id="kyc-fee-password" type="password" autoComplete="current-password" className={inputClass}
                value={password} disabled={busy} onChange={(e) => setPassword(e.target.value)} />
              <p className="text-xs text-gray-500">Required to confirm the change.</p>
            </div>
            <div className="sm:col-span-2">
              <Button onClick={() => void save()} disabled={busy || parsed === null || unchanged || !password}>
                {busy ? 'Saving…' : 'Save fee'}
              </Button>
            </div>
          </div>
        )}

        {notice && <p className="text-sm text-green-700 dark:text-green-300" role="status">{notice}</p>}
        {error && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>}
      </CardContent>
    </Card>
  )
}
