'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'

type Json = Record<string, any>
const BASE = '/api/v1/admin/finance/internal-wallet'

function errorText(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object') return String((detail as Json).message || JSON.stringify(detail))
  return typeof detail === 'string' ? detail : 'Request failed'
}

/** Internal wallet payments: switch state, product policy, reconciliation, payments (filters), details and
 * full refunds (process_cashouts permission + current password, enforced by the server). Read-only otherwise. */
export default function AdminInternalWallet() {
  const [overview, setOverview] = useState<Json | null>(null)
  const [payments, setPayments] = useState<Json[]>([])
  const [filters, setFilters] = useState({ user_id: '', product_code: '', status: '' })
  const [detail, setDetail] = useState<Json | null>(null)
  const [reason, setReason] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
      const [o, p] = await Promise.all([api.get(`${BASE}/overview`), api.get(`${BASE}/payments`, { params })])
      if (o.status >= 400) throw { response: o }
      setOverview(o.data)
      setPayments(p.status < 400 ? p.data.payments || [] : [])
    } catch (e) {
      setMessage(errorText(e))
    }
  }, [filters])

  useEffect(() => { load() }, [load])

  const open = async (id: number) => {
    const res = await api.get(`${BASE}/payments/${id}`)
    if (res.status < 400) setDetail(res.data)
  }

  const refund = async () => {
    if (!detail) return
    setMessage('')
    try {
      const res = await api.post(`${BASE}/payments/${detail.id}/refund`, { reason, current_password: password })
      if (res.status >= 400) throw { response: res }
      setMessage(`Payment ${detail.reference} refunded`)
      setDetail(res.data)
      await load()
    } catch (e) {
      setMessage(errorText(e))
    }
  }

  if (!overview) return message ? <p className="text-sm text-red-600">{message}</p> : null
  const rec = overview.reconciliation || {}
  return (
    <section data-testid="admin-internal-wallet" className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
      <h2 className="font-semibold">Payments with MyHigh5 earnings (internal wallet)</h2>
      <p data-testid="iw-switch">Switch: <strong>{overview.enabled ? 'ON' : 'OFF'}</strong> — {overview.switch}</p>
      <p data-testid="iw-reconciliation">Reconciliation: {rec.ok ? 'consistent' : 'PROBLEMS'} · clearing 1050 {rec.clearing_balance} ·
        {' '}{JSON.stringify(rec.payments_by_status || {})}</p>
      {(rec.problems || []).map((p: Json, i: number) => <p key={i} className="text-red-600">{p.type}: {p.message}</p>)}
      <details>
        <summary className="cursor-pointer">Products and eligibility</summary>
        <ul className="mt-1 list-disc pl-5">
          {(overview.products || []).map((p: Json) => (
            <li key={p.product_code}>{p.name}: {p.eligible ? 'payable with earnings' : `${p.reason} — ${p.message || ''}`}</li>
          ))}
        </ul>
      </details>
      <div className="flex flex-wrap items-end gap-2">
        {(['user_id', 'product_code'] as const).map((k) => (
          <input key={k} placeholder={k === 'user_id' ? 'Member id' : 'Product code'} aria-label={k} value={filters[k]}
            onChange={(e) => setFilters({ ...filters, [k]: e.target.value })} className="rounded border px-2 py-1 dark:bg-gray-900" />
        ))}
        <select aria-label="status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className="rounded border px-2 py-1 dark:bg-gray-900">
          <option value="">Any status</option><option>COMPLETED</option><option>FAILED</option><option>REFUNDED</option>
        </select>
      </div>
      {payments.length === 0 ? <p className="text-gray-500">No payments.</p> : (
        <table className="w-full text-xs sm:text-sm">
          <thead className="text-left text-gray-500"><tr>
            {['Reference', 'Member', 'Product', 'Amount', 'Status', 'Date', ''].map((h) => <th key={h} className="py-1 pr-3">{h}</th>)}
          </tr></thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id} className="border-t border-gray-100 dark:border-gray-700">
                <td className="pr-3">{p.reference}</td><td className="pr-3">#{p.user_id}</td>
                <td className="pr-3">{p.product_code} x{p.quantity}</td><td className="pr-3">{p.amount} USD</td>
                <td className="pr-3">{p.status}{p.failure_code ? ` (${p.failure_code})` : ''}</td>
                <td className="pr-3">{(p.created_at || '').slice(0, 16)}</td>
                <td><button type="button" className="underline" onClick={() => open(p.id)}>Details</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {detail ? (
        <div data-testid="iw-detail" className="space-y-1 rounded border border-gray-200 p-2 dark:border-gray-700">
          <p className="font-medium">{detail.reference} — {detail.status}</p>
          <p>Commissions used: {(detail.lines || []).map((l: Json) => `#${l.commission_id} ${l.amount} (${l.status})`).join(', ') || '—'}</p>
          <p>Journal: settlement #{detail.settlement_journal_entry_id ?? '—'}{detail.refund_journal_entry_id ? `, refund #${detail.refund_journal_entry_id}` : ''};
            {' '}payment record (deposit) #{detail.deposit_id ?? '—'}</p>
          {detail.status === 'COMPLETED' ? (
            <div className="flex flex-wrap items-end gap-2">
              <input placeholder="Refund reason" aria-label="Refund reason" value={reason} onChange={(e) => setReason(e.target.value)}
                className="rounded border px-2 py-1 dark:bg-gray-900" />
              <input type="password" placeholder="Current password" aria-label="Current password" value={password}
                onChange={(e) => setPassword(e.target.value)} className="rounded border px-2 py-1 dark:bg-gray-900" autoComplete="current-password" />
              <button type="button" disabled={reason.trim().length < 5} onClick={refund}
                className="rounded bg-red-600 px-2 py-1 text-white disabled:opacity-50">Full refund</button>
            </div>
          ) : null}
        </div>
      ) : null}
      {message ? <p role="status">{message}</p> : null}
    </section>
  )
}
