'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { CASHOUTS_BASE, FINANCE_BASE, dateTime, financeErrorText, usd } from '@/lib/finance-admin'
import { StatusPill, inputClass } from './admin-finance-ui'

/**
 * Individual automatic USDT payouts (owner rules, 2026-10-18):
 *  - Wallet approval queue and the history of decisions. Nothing is paid to a
 *    wallet before an authorised administrator approved it; nobody decides
 *    their own wallet; the password is asked for every decision.
 *  - Commission-to-payout reconciliation: each commission with its own payouts.
 *  - Emergency pause of automatic payouts (resuming is the ordinary activation).
 * Every action is checked and audited by the backend.
 */
export type WalletApprovalRow = {
  id: number
  user_id: number
  username: string | null
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED'
  currency: string
  address: string
  submitted_at: string | null
  verification_method: string | null
  decided_by: number | null
  decided_at: string | null
  decision_note: string | null
}

export type CommissionPayoutRow = {
  commission_id: number
  user_id: number
  amount: string
  status: string
  reserved: boolean
  attempts: { cashout_id: number; status: string; failure_code: string | null; tx_hash: string | null }[]
  problems: string[]
}

export const PROBLEM_LABEL: Record<string, string> = {
  PAID_WITHOUT_PAYOUT: 'Paid, but none of its payouts completed',
  PAYOUT_NOT_POSTED: 'Payout completed, commission not marked paid',
  AMOUNT_MISMATCH: 'Payout amount differs from the commission',
  COMPLETED_WITHOUT_HASH: 'Completed without a transaction hash',
  RESERVED_WITHOUT_PAYOUT: 'Reserved without an open payout',
}

const thClass = 'py-2 pr-3 font-medium'
const tdClass = 'py-2 pr-3'

export function WalletApprovals({ canProcess }: { canProcess: boolean }) {
  const [status, setStatus] = useState<'PENDING' | ''>('PENDING')
  const [rows, setRows] = useState<WalletApprovalRow[]>([])
  const [selected, setSelected] = useState<WalletApprovalRow | null>(null)
  const [note, setNote] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const res = await api.get(`${CASHOUTS_BASE}/wallet-approvals`, { params: status ? { status } : {} })
    if (res.status === 200) setRows(res.data.items)
    else setError(financeErrorText(res, 'Wallet submissions could not be loaded.'))
  }, [status])

  useEffect(() => { void load() }, [load])

  const decide = async (decision: 'APPROVE' | 'REJECT') => {
    if (!selected) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const res = await api.post(`${CASHOUTS_BASE}/wallet-approvals/${selected.id}`, {
        decision, note: note.trim() || null, current_password: password,
      })
      if (res.status === 200) {
        setNotice(decision === 'APPROVE'
          ? 'Wallet approved. The member\'s available commissions are queued, each as its own payout.'
          : 'Wallet rejected. Nothing will be paid to it.')
        setSelected(null)
        setNote('')
        await load()
      } else setError(financeErrorText(res, 'The decision could not be recorded.'))
    } finally {
      setPassword('')
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4" data-testid="wallet-approvals">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">Payout wallet approvals</h3>
          <label className="text-sm">
            <span className="sr-only">Show</span>
            <select className={inputClass} value={status} onChange={(e) => setStatus(e.target.value as 'PENDING' | '')}>
              <option value="PENDING">Waiting for a decision</option>
              <option value="">All decisions (history)</option>
            </select>
          </label>
        </div>
        <p className="text-xs text-gray-500">
          Compare the full address with the member&apos;s request before approving. If the provider requires
          whitelisted payout addresses, add the approved address there too.
        </p>
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        {notice && <p className="text-sm text-green-700" role="status">{notice}</p>}
        {rows.length === 0 ? (
          <p className="text-sm text-gray-500">{status ? 'No wallet waits for a decision.' : 'No wallet decisions yet.'}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-gray-500">
                <tr>
                  <th className={thClass}>Member</th>
                  <th className={thClass}>Wallet (USDT BEP20)</th>
                  <th className={thClass}>Submitted</th>
                  <th className={thClass}>Status</th>
                  <th className={thClass} />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className={tdClass}>#{row.user_id} {row.username ?? ''}</td>
                    <td className={`${tdClass} break-all font-mono text-xs`}>{row.address}</td>
                    <td className={tdClass}>{dateTime(row.submitted_at)}</td>
                    <td className={tdClass}>
                      <StatusPill status={row.status === 'APPROVED' ? 'completed' : row.status === 'PENDING' ? 'unknown' : 'failed'}>
                        {row.status}
                      </StatusPill>
                      {row.decision_note && <span className="block text-xs text-gray-500">{row.decision_note}</span>}
                    </td>
                    <td className={`${tdClass} text-right`}>
                      {canProcess && row.status === 'PENDING' && (
                        <Button size="sm" variant="outline" onClick={() => setSelected(row)}>Review</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {selected && (
          <div className="space-y-2 rounded-lg border border-gray-200 p-3 dark:border-gray-700" data-testid="wallet-decision">
            <p className="text-sm">
              Member #{selected.user_id}: <span className="break-all font-mono">{selected.address}</span> ({selected.currency})
            </p>
            <label className="block text-sm">
              Note (required to reject, at least 10 characters)
              <input className={inputClass} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
            </label>
            <label className="block text-sm">
              Your current password
              <input className={inputClass} type="password" autoComplete="current-password" value={password}
                onChange={(e) => setPassword(e.target.value)} />
            </label>
            <div className="flex gap-2">
              <Button disabled={busy || !password} onClick={() => void decide('APPROVE')}>Approve wallet</Button>
              <Button variant="outline" disabled={busy || !password || note.trim().length < 10}
                onClick={() => void decide('REJECT')}>Reject wallet</Button>
              <Button variant="ghost" disabled={busy} onClick={() => setSelected(null)}>Close</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function CommissionPayouts() {
  const [data, setData] = useState<{ items: CommissionPayoutRow[]; problems: CommissionPayoutRow[]; checked: number } | null>(null)
  const [onlyProblems, setOnlyProblems] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    void (async () => {
      const res = await api.get(`${CASHOUTS_BASE}/commission-payouts`)
      if (res.status === 200) setData(res.data)
      else setError(financeErrorText(res, 'The reconciliation could not be loaded.'))
    })()
  }, [])

  const rows = data ? (onlyProblems ? data.problems : data.items) : []
  return (
    <Card>
      <CardContent className="space-y-3 p-4" data-testid="commission-payouts">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">Commission-to-payout reconciliation</h3>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />
            Only rows that do not agree
          </label>
        </div>
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        {data && (
          <p className="text-xs text-gray-500">
            {data.checked} commissions checked, {data.problems.length} with a problem.
          </p>
        )}
        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-gray-500">
                <tr>
                  <th className={thClass}>Commission</th>
                  <th className={thClass}>Member</th>
                  <th className={`${thClass} text-right`}>Amount</th>
                  <th className={thClass}>Status</th>
                  <th className={thClass}>Payouts</th>
                  <th className={thClass}>Problems</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {rows.map((row) => (
                  <tr key={row.commission_id}>
                    <td className={tdClass}>#{row.commission_id}</td>
                    <td className={tdClass}>#{row.user_id}</td>
                    <td className={`${tdClass} text-right tabular-nums`}>{usd(row.amount)}</td>
                    <td className={tdClass}>{row.status}{row.reserved ? ' (reserved)' : ''}</td>
                    <td className={`${tdClass} text-xs`}>
                      {row.attempts.length === 0 ? '-' : row.attempts.map((a) => (
                        <span key={a.cashout_id} className="block">#{a.cashout_id} {a.status}{a.failure_code ? ` (${a.failure_code})` : ''}</span>
                      ))}
                    </td>
                    <td className={`${tdClass} text-xs text-red-700`}>
                      {row.problems.map((p) => PROBLEM_LABEL[p] ?? p).join('; ') || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function PayoutPause({ canProcess, active }: { canProcess: boolean; active: boolean }) {
  const [reason, setReason] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  if (!canProcess || !active || done) {
    return done ? <p className="text-sm text-green-700" role="status">Automatic payouts are paused.</p> : null
  }
  const pause = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await api.post(`${FINANCE_BASE}/payouts/pause`, { reason, current_password: password })
      if (res.status === 200) setDone(true)
      else setError(financeErrorText(res, 'Payouts could not be paused.'))
    } finally {
      setPassword('')
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardContent className="space-y-2 p-4" data-testid="payout-pause">
        <h3 className="font-semibold text-red-700">Emergency pause</h3>
        <p className="text-xs text-gray-500">
          Stops new automatic payouts at once. Payouts already sent keep being checked with the provider. Resuming is
          done by switching automatic payouts on again in the Crypto Cashout settings.
        </p>
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        <input className={inputClass} placeholder="Reason (at least 10 characters)" value={reason} maxLength={500}
          onChange={(e) => setReason(e.target.value)} />
        <input className={inputClass} type="password" placeholder="Your current password" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button variant="destructive" disabled={busy || !password || reason.trim().length < 10} onClick={() => void pause()}>
          Pause automatic payouts
        </Button>
      </CardContent>
    </Card>
  )
}
