'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  CASHOUTS_BASE,
  CASHOUT_STATUS_LABEL,
  FINANCE_BASE,
  dateTime,
  financeErrorText,
  humanize,
  usd,
  type AdminCashout,
  type Reconciliation,
} from '@/lib/finance-admin'
import { Row, StatusPill, inputClass } from './admin-finance-ui'

/**
 * Cashout Transactions and Reconciliation & Audit Logs.
 *
 * There is deliberately no "pay now" control: an administrator records a USD
 * settlement that happened outside the platform, cancels a request, or settles
 * a crypto payout whose outcome is unknown after checking the provider. Each
 * action needs the process_cashouts permission and is audited by the backend.
 */
const PAGE = 25
const STATUSES: AdminCashout['status'][] = ['requested', 'processing', 'unknown', 'completed', 'failed', 'cancelled']

type Detail = {
  cashout: AdminCashout
  member: { id: number; username: string | null; cashout_method: string | null; wallet: string | null; wallet_status: string | null }
  commissions: { id: number; amount: number; status: string; level: number; transaction_date: string | null }[]
  attempts: AdminCashout[]
}

const thClass = 'py-2 pr-3 font-medium'
const tdClass = 'py-2 pr-3'

export function CashoutTransactions({ canProcess }: { canProcess: boolean }) {
  const [method, setMethod] = useState('')
  const [status, setStatus] = useState('')
  const [userId, setUserId] = useState('')
  const [page, setPage] = useState(0)
  const [rows, setRows] = useState<AdminCashout[]>([])
  const [total, setTotal] = useState(0)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [reference, setReference] = useState('')
  const [reason, setReason] = useState('')
  const [destination, setDestination] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const params: Record<string, string | number> = { skip: page * PAGE, limit: PAGE }
    if (method) params.method = method
    if (status) params.status = status
    if (/^\d+$/.test(userId.trim())) params.user_id = Number(userId.trim())
    const res = await api.get(CASHOUTS_BASE, { params })
    if (res.status === 200) {
      setRows(res.data.items)
      setTotal(res.data.total)
    } else setError(financeErrorText(res, 'Cashouts could not be loaded.'))
  }, [method, status, userId, page])

  useEffect(() => { void load() }, [load])

  const open = async (id: number) => {
    setDestination(null)
    setReference('')
    setReason('')
    const res = await api.get(`${CASHOUTS_BASE}/${id}`)
    if (res.status === 200) setDetail(res.data)
    else setError(financeErrorText(res, 'The cashout could not be loaded.'))
  }

  const act = async (path: string, body: Record<string, unknown>, ok: string) => {
    if (!detail) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const res = await api.post(`${CASHOUTS_BASE}/${detail.cashout.id}/${path}`, body)
      if (res.status === 200) {
        setNotice(ok)
        await Promise.all([load(), open(detail.cashout.id)])
      } else setError(financeErrorText(res, 'The action could not be completed.'))
    } finally {
      setBusy(false)
    }
  }

  const showDestination = async () => {
    if (!detail) return
    const res = await api.get(`${CASHOUTS_BASE}/${detail.cashout.id}/destination`)
    if (res.status === 200) setDestination(res.data.destination ?? '')
    else setError(financeErrorText(res, 'The destination details could not be shown.'))
  }

  const c = detail?.cashout
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="block text-xs text-gray-500">Method</span>
              <select aria-label="Method" className={inputClass} value={method}
                onChange={(e) => { setPage(0); setMethod(e.target.value) }}>
                <option value="">All methods</option>
                <option value="CRYPTO">Crypto</option>
                <option value="USD">USD</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="block text-xs text-gray-500">Status</span>
              <select aria-label="Status" className={inputClass} value={status}
                onChange={(e) => { setPage(0); setStatus(e.target.value) }}>
                <option value="">All statuses</option>
                {STATUSES.map((s) => <option key={s} value={s}>{CASHOUT_STATUS_LABEL[s]}</option>)}
              </select>
            </label>
            <label className="text-sm">
              <span className="block text-xs text-gray-500">Member ID</span>
              <input aria-label="Member ID" className={inputClass} inputMode="numeric" value={userId}
                onChange={(e) => { setPage(0); setUserId(e.target.value) }} />
            </label>
            <Button variant="outline" size="sm" onClick={() => { setPage(0); setMethod(''); setStatus('unknown') }}>
              Unknown outcomes
            </Button>
            <Button variant="outline" size="sm" onClick={() => { setPage(0); setMethod(''); setStatus('failed') }}>
              Failed payouts
            </Button>
          </div>
          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          {notice && <p role="status" className="text-sm text-green-700 dark:text-green-400">{notice}</p>}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm text-left">
              <thead className="text-xs text-gray-500">
                <tr>
                  <th className={thClass}>ID</th><th className={thClass}>Requested</th><th className={thClass}>Member</th>
                  <th className={thClass}>Method</th><th className={`${thClass} text-right`}>Gross</th>
                  <th className={`${thClass} text-right`}>Fee</th><th className={`${thClass} text-right`}>Net</th>
                  <th className={thClass}>Status</th><th className={thClass}>Reference</th><th className={thClass} />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className={tdClass}>#{r.id}</td>
                    <td className={tdClass}>{dateTime(r.requested_at)}</td>
                    <td className={tdClass}>{r.username ?? 'Member'} <span className="text-xs text-gray-500">#{r.user_id}</span></td>
                    <td className={tdClass}>{r.method === 'USD' ? 'USD' : 'Crypto'}</td>
                    <td className={`${tdClass} text-right tabular-nums`}>{usd(r.gross_amount)}</td>
                    <td className={`${tdClass} text-right tabular-nums`}>{usd(r.fee)}</td>
                    <td className={`${tdClass} text-right tabular-nums`}>{usd(r.net_amount)}</td>
                    <td className={tdClass}><StatusPill status={r.status}>{CASHOUT_STATUS_LABEL[r.status]}</StatusPill></td>
                    <td className={`${tdClass} font-mono text-xs`}>{r.reference ?? '-'}</td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="outline" onClick={() => void open(r.id)}>Details</Button>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={10} className="py-6 text-center text-gray-500">No cashouts match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>{total} cashout{total === 1 ? '' : 's'}</span>
            <span className="flex gap-2">
              <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button size="sm" variant="outline" disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}>Next</Button>
            </span>
          </div>
        </CardContent>
      </Card>

      {detail && c && (
        <Card>
          <CardContent className="p-4 space-y-4" data-testid="cashout-detail">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-gray-900 dark:text-white">Cashout #{c.id}</h2>
              <StatusPill status={c.status}>{CASHOUT_STATUS_LABEL[c.status]}</StatusPill>
            </div>
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2 text-sm">
              <Row label="Member" value={`${detail.member.username ?? 'Member'} (#${detail.member.id})`} />
              <Row label="Method" value={c.method === 'USD' ? 'USD Cashout' : 'Crypto Cashout'} />
              <Row label="Gross amount" value={usd(c.gross_amount)} />
              <Row label="MyHigh5 fee" value={usd(c.fee)} />
              <Row label="Net amount to member" value={usd(c.net_amount)} />
              {c.method === 'CRYPTO' && (<>
                <Row label="Network fee estimate" value={c.network_fee !== null ? `${usd(c.network_fee)} (${humanize(c.network_fee_policy)})` : '-'} />
                <Row label="Destination wallet" value={<span className="font-mono">{c.destination ?? '-'}</span>} />
                <Row label="Provider payout ID" value={<span className="font-mono text-xs">{c.provider_batch_id ?? '-'}</span>} />
                <Row label="Provider status" value={c.provider_status ?? '-'} />
              </>)}
              <Row label="Outcome code" value={c.failure_code ? humanize(c.failure_code) : '-'} />
              <Row label="Settlement reference" value={<span className="font-mono text-xs">{c.reference ?? '-'}</span>} />
              <Row label="Requested" value={dateTime(c.requested_at)} />
              <Row label="Processed" value={dateTime(c.processed_at)} />
              <Row label="Member wallet now" value={`${detail.member.wallet ?? 'Not set'} (${humanize(detail.member.wallet_status)})`} />
              <Row label="Reviewed by" value={c.reviewed_by ? `Administrator #${c.reviewed_by}` : '-'} />
            </dl>

            <div>
              <h3 className="text-sm font-semibold mb-1">Commissions held by this cashout</h3>
              <ul className="text-sm text-gray-700 dark:text-gray-300">
                {detail.commissions.map((row) => (
                  <li key={row.id}>#{row.id} · {usd(row.amount)} · {humanize(row.status)} · {dateTime(row.transaction_date)}</li>
                ))}
                {detail.commissions.length === 0 && <li className="text-gray-500">None (released).</li>}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold mb-1">Member&apos;s payout attempts</h3>
              <ul className="text-sm text-gray-700 dark:text-gray-300">
                {detail.attempts.map((a) => (
                  <li key={a.id}>#{a.id} · {a.method === 'USD' ? 'USD' : 'Crypto'} · {usd(a.gross_amount)} · {CASHOUT_STATUS_LABEL[a.status]}
                    {a.failure_code ? ` · ${humanize(a.failure_code)}` : ''} · {dateTime(a.requested_at)}</li>
                ))}
              </ul>
              <p className="text-xs text-gray-500 mt-1">A payout is never sent twice: each attempt is a separate cashout.</p>
            </div>

            {!canProcess && (
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Acting on a cashout needs the <code>process_cashouts</code> permission.
              </p>
            )}
            {canProcess && c.method === 'USD' && c.status === 'requested' && (
              <div className="space-y-3 border-t border-gray-200 dark:border-gray-700 pt-3">
                {c.has_destination_details && (
                  destination === null
                    ? <Button size="sm" variant="outline" onClick={() => void showDestination()}>Show payout destination (audited)</Button>
                    : <p className="text-sm whitespace-pre-wrap rounded bg-gray-50 dark:bg-gray-900/40 p-2" data-testid="usd-destination">{destination}</p>
                )}
                <div className="space-y-1">
                  <label htmlFor="settle-reference" className="block text-sm font-medium">External payment reference</label>
                  <input id="settle-reference" className={inputClass} value={reference} maxLength={200}
                    onChange={(e) => setReference(e.target.value)} />
                  <p className="text-xs text-gray-500">
                    Record a settlement only after {usd(c.net_amount)} has actually been paid to the member outside the platform.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy || reference.trim().length < 3}
                    onClick={() => void act('settle-usd', { reference: reference.trim() }, 'Settlement recorded.')}>
                    Record USD settlement
                  </Button>
                </div>
                <div className="space-y-1">
                  <label htmlFor="cancel-reason" className="block text-sm font-medium">Cancellation reason</label>
                  <input id="cancel-reason" className={inputClass} value={reason} maxLength={500}
                    onChange={(e) => setReason(e.target.value)} />
                  <Button variant="outline" disabled={busy || !reason.trim()}
                    onClick={() => void act('cancel', { reason: reason.trim() }, 'Request cancelled. The amount is back in the member\'s available balance.')}>
                    Cancel request
                  </Button>
                </div>
              </div>
            )}
            {canProcess && c.method === 'CRYPTO' && c.status === 'unknown' && (
              <div className="space-y-3 border-t border-gray-200 dark:border-gray-700 pt-3">
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  The provider&apos;s answer is unknown. The amount stays reserved and is never sent again automatically.
                  Check the payout in the provider dashboard, then record what happened.
                </p>
                <div className="space-y-1">
                  <label htmlFor="resolve-reference" className="block text-sm font-medium">Provider reference (if it was sent)</label>
                  <input id="resolve-reference" className={inputClass} value={reference} maxLength={200}
                    onChange={(e) => setReference(e.target.value)} />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy || (!reference.trim() && !c.provider_batch_id)}
                    onClick={() => void act('resolve', { outcome: 'SENT', reference: reference.trim() || undefined }, 'Recorded as sent.')}>
                    It was sent
                  </Button>
                  <Button variant="outline" disabled={busy}
                    onClick={() => void act('resolve', { outcome: 'NOT_SENT' }, 'Recorded as not sent. The amount is available again.')}>
                    It was not sent
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

type AuditItem = {
  id: number; version?: number; action: string; actor_id: number | null; created_at: string | null
  changed_fields?: string[]; old_values: Record<string, unknown>; new_values: Record<string, unknown>
  table?: string; record_id?: number
}
type WalletHistory = {
  items: { id: number; user_id: number; old_wallet: string | null; new_wallet: string; payout_currency: string; changed_at: string; payable_from: string; verified_by: string | null }[]
  pending: { id: number; user_id: number; wallet: string; payout_currency: string; requested_at: string; expires_at: string }[]
}

const show = (values: Record<string, unknown>) =>
  Object.entries(values).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') || '-' : String(value)}`).join(' · ') || '-'

export function ReconciliationAndAudit({ canManage }: { canManage: boolean }) {
  const [report, setReport] = useState<Reconciliation | null>(null)
  const [config, setConfig] = useState<AuditItem[]>([])
  const [events, setEvents] = useState<AuditItem[]>([])
  const [wallets, setWallets] = useState<WalletHistory | null>(null)
  const [error, setError] = useState('')

  const loadReport = useCallback(async (readProvider = false) => {
    const res = await api.get(`${FINANCE_BASE}/reconciliation`, { params: readProvider ? { read_provider: true } : {} })
    if (res.status === 200) setReport(res.data)
    else setError(financeErrorText(res, 'The reconciliation report could not be loaded.'))
  }, [])

  useEffect(() => {
    void loadReport()
    void (async () => {
      const [a, f, w] = await Promise.all([
        api.get(`${FINANCE_BASE}/audit`, { params: { limit: 50 } }),
        api.get(`${FINANCE_BASE}/financial-audit`, { params: { limit: 50 } }),
        api.get(`${FINANCE_BASE}/wallet-history`, { params: { limit: 50 } }),
      ])
      if (a.status === 200) setConfig(a.data.items)
      if (f.status === 200) setEvents(f.data.items)
      if (w.status === 200) setWallets(w.data)
    })()
  }, [loadReport])

  return (
    <div className="space-y-4">
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {report && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <h2 className="font-semibold text-gray-900 dark:text-white">Reconciliation</h2>
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2 text-sm">
              <Row label="Commissions pending" value={usd(report.owed.pending)} />
              <Row label="Commissions available" value={usd(report.owed.available)} />
              <Row label="Commissions reserved" value={usd(report.owed.reserved)} />
              <Row label="Total owed to members" value={usd(report.owed_total)} />
              <Row label="Owed to Crypto Cashout members" value={usd(report.owed_to_crypto_cashout_members)} />
              <Row label="Open cashouts" value={show(report.open_cashouts)} />
              <Row label="Crypto paid out, last 24 hours"
                value={`${usd(report.last_24_hours.crypto_payout_amount)} of ${usd(report.last_24_hours.amount_limit)} · ${report.last_24_hours.crypto_payout_count} of ${report.last_24_hours.count_limit}`} />
              <Row label="Provider custody balance" value={
                report.provider_balance !== null ? String(report.provider_balance)
                  : <StatusPill status={report.provider_balance_state} />} />
            </dl>
            <p className="text-xs text-gray-500">
              These amounts are MyHigh5&apos;s own records of what is owed. They are not proof of the funds held by the
              provider: the custody balance is shown only when it has been read from the provider.
            </p>
            {canManage && (
              <Button size="sm" variant="outline" onClick={() => void loadReport(true)}>Read provider balance (read-only)</Button>
            )}
            <h3 className="text-sm font-semibold pt-2">Discrepancies</h3>
            {report.discrepancies.length === 0
              ? <p className="text-sm text-green-700 dark:text-green-400">No internal discrepancy found.</p>
              : (
                <ul className="space-y-1 text-sm" data-testid="discrepancies">
                  {report.discrepancies.map((d, index) => (
                    <li key={`${d.type}-${index}`} className="flex gap-2">
                      <StatusPill status={d.severity === 'critical' ? 'ERROR' : 'PARTIAL'}>{humanize(d.type)}</StatusPill>
                      <span>{d.message}</span>
                    </li>
                  ))}
                </ul>
              )}
          </CardContent>
        </Card>
      )}

      <AuditTable title="Configuration changes" empty="No configuration change has been recorded." rows={config}
        describe={(r) => `Version ${r.version} · ${show(r.new_values)}${Object.keys(r.old_values).length ? ` (was ${show(r.old_values)})` : ''}`} />
      <AuditTable title="Financial audit events" empty="No cashout event has been recorded." rows={events}
        describe={(r) => `${r.table === 'affiliate_cashout_requests' ? `Cashout #${r.record_id}` : `Member #${r.record_id}`} · ${show(r.new_values)}`} />

      {wallets && (
        <Card>
          <CardContent className="p-4 space-y-2">
            <h2 className="font-semibold text-gray-900 dark:text-white">Member payout wallet history</h2>
            <ul className="text-sm space-y-1">
              {wallets.pending.map((p) => (
                <li key={`p-${p.id}`}>Member #{p.user_id} · {p.wallet} · awaiting email confirmation until {dateTime(p.expires_at)}</li>
              ))}
              {wallets.items.map((w) => (
                <li key={w.id}>Member #{w.user_id} · {w.old_wallet ?? 'none'} → {w.new_wallet} · {dateTime(w.changed_at)} ·
                  verified by {humanize(w.verified_by) || 'password'} · payable from {dateTime(w.payable_from)}</li>
              ))}
              {wallets.items.length + wallets.pending.length === 0 && <li className="text-gray-500">No wallet change has been recorded.</li>}
            </ul>
            <p className="text-xs text-gray-500">Wallet addresses are masked. Entries are never edited or deleted.</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function AuditTable({ title, empty, rows, describe }: {
  title: string; empty: string; rows: AuditItem[]; describe: (row: AuditItem) => string
}) {
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <h2 className="font-semibold text-gray-900 dark:text-white">{title}</h2>
        {rows.length === 0 ? <p className="text-sm text-gray-500">{empty}</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm text-left">
              <thead className="text-xs text-gray-500">
                <tr><th className={thClass}>When</th><th className={thClass}>Action</th><th className={thClass}>By</th><th className={thClass}>Details</th></tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className={`${tdClass} whitespace-nowrap`}>{dateTime(r.created_at)}</td>
                    <td className={tdClass}>{humanize(r.action)}</td>
                    <td className={tdClass}>{r.actor_id ? `#${r.actor_id}` : 'System'}</td>
                    <td className={`${tdClass} text-xs break-words`}>{describe(r)}</td>
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
