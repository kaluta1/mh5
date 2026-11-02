'use client'

import { useEffect, useRef, useState } from 'react'
import api from '@/lib/api'

type Preview = {
  product_code: string
  product_name: string
  quantity: number
  amount: string
  currency: string
  available: string
  remaining_after: string | null
  allowed: boolean
  reason: string | null
  message: string | null
}

function newKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}-wallet`
}

function detailText(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object' && 'message' in (detail as Record<string, unknown>)) {
    return String((detail as Record<string, unknown>).message)
  }
  return typeof detail === 'string' ? detail : 'The payment could not be completed; nothing was charged.'
}

/**
 * "Pay with MyHigh5 Earnings": a full payment with available commission earnings. Hidden while the
 * feature is switched off. The server prices the order and re-checks KYC, the product and the balance;
 * the amount shown here is only what the member reviews (a different server price stops the payment).
 */
export function PayWithEarnings({ productCode, quantity, onPaid }: {
  productCode: string
  quantity: number
  onPaid?: () => void
}) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const key = useRef<string>(newKey())

  useEffect(() => {
    let cancelled = false
    setResult(null)
    key.current = newKey()
    api.get<Preview>('/api/v1/internal-wallet/preview', { params: { product_code: productCode, quantity } })
      .then((res) => { if (!cancelled && res.status < 400) setPreview(res.data) })
      .catch(() => { if (!cancelled) setPreview(null) })
    return () => { cancelled = true }
  }, [productCode, quantity])

  if (!preview || preview.reason === 'WALLET_PAYMENTS_DISABLED') return null

  const pay = async () => {
    if (busy || !preview.allowed) return
    setBusy(true)
    setResult(null)
    try {
      const res = await api.post('/api/v1/internal-wallet/pay', {
        product_code: productCode, quantity, idempotency_key: key.current, expected_amount: preview.amount,
      })
      if (res.status >= 400) throw { response: res }
      setResult({ ok: true, text: `Paid ${preview.amount} ${preview.currency} with your earnings (reference ${res.data.reference}).` })
      key.current = newKey()
      onPaid?.()
    } catch (e) {
      setResult({ ok: false, text: detailText(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div data-testid="pay-with-earnings" className="space-y-2 rounded-lg border border-emerald-300 p-3 text-sm dark:border-emerald-800">
      <p className="font-semibold">Pay with MyHigh5 Earnings</p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
        <dt className="text-gray-500">Product</dt><dd>{preview.product_name} x{preview.quantity}</dd>
        <dt className="text-gray-500">Price</dt><dd>{preview.amount} {preview.currency}</dd>
        <dt className="text-gray-500">Available eligible earnings</dt><dd data-testid="earnings-available">{preview.available} {preview.currency}</dd>
        <dt className="text-gray-500">Amount deducted</dt><dd>{preview.amount} {preview.currency}</dd>
        {preview.remaining_after != null ? (<>
          <dt className="text-gray-500">Remaining after payment</dt><dd data-testid="earnings-remaining">{preview.remaining_after} {preview.currency}</dd>
        </>) : null}
      </dl>
      <p className="text-xs text-gray-500">Only approved, available commissions are used. Pending and missed commissions are never spendable.</p>
      {!preview.allowed && preview.message ? (
        <p data-testid="earnings-blocked" className="text-amber-700 dark:text-amber-400">{preview.message}</p>
      ) : null}
      <button type="button" onClick={pay} disabled={busy || !preview.allowed}
        className="rounded bg-emerald-600 px-3 py-1.5 text-white disabled:opacity-50">
        {busy ? 'Paying…' : `Confirm: pay ${preview.amount} ${preview.currency} with earnings`}
      </button>
      {result ? (
        <p role="status" data-testid="earnings-result" className={result.ok ? 'text-emerald-700' : 'text-red-600'}>{result.text}</p>
      ) : null}
    </div>
  )
}

type Summary = {
  enabled: boolean
  spendable: string
  wallet_only_remainder: string
  reserved_for_payouts: string
  total_spent: string
  total_refunded: string
  kyc_approved: boolean
  message: string | null
  payments: Array<{ id: number; reference: string; product_code: string; quantity: number; amount: string;
    status: string; created_at: string | null; refunded_at: string | null; failure_code: string | null }>
}

const STATUS: Record<string, string> = { COMPLETED: 'Completed', FAILED: 'Failed (nothing charged)', REFUNDED: 'Refunded' }

/** Purchases paid with earnings: the spendable amount (same commission rows as the cashout panel) and history. */
export function EarningsPayments() {
  const [data, setData] = useState<Summary | null>(null)
  useEffect(() => {
    api.get<Summary>('/api/v1/internal-wallet/summary')
      .then((res) => { if (res.status < 400) setData(res.data) })
      .catch(() => undefined)
  }, [])
  if (!data || (!data.enabled && data.payments.length === 0)) return null
  return (
    <section data-testid="earnings-payments" className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
      <h2 className="font-semibold">Purchases paid with earnings</h2>
      <div className="grid gap-3 sm:grid-cols-4">
        <div><p className="text-xs text-gray-500">Spendable earnings</p><p className="text-lg font-semibold">{data.spendable} USD</p></div>
        <div><p className="text-xs text-gray-500">Reserved for payouts</p><p className="text-lg font-semibold">{data.reserved_for_payouts} USD</p></div>
        <div><p className="text-xs text-gray-500">Spent with earnings</p><p className="text-lg font-semibold">{data.total_spent} USD</p></div>
        <div><p className="text-xs text-gray-500">Refunded</p><p className="text-lg font-semibold">{data.total_refunded} USD</p></div>
      </div>
      {Number(data.wallet_only_remainder) > 0 ? (
        <p data-testid="earnings-remainder" className="text-xs text-gray-500">
          {data.wallet_only_remainder} USD is the unused part of commissions already partly spent: it can pay another
          purchase but is not included in cash-outs.
        </p>
      ) : null}
      {data.payments.length === 0 ? <p className="text-gray-500">No purchases paid with earnings yet.</p> : (
        <table className="w-full text-xs sm:text-sm">
          <thead className="text-left text-gray-500"><tr>
            {['Date', 'Reference', 'Product', 'Amount', 'Status'].map((h) => <th key={h} className="py-1 pr-3">{h}</th>)}
          </tr></thead>
          <tbody>
            {data.payments.map((p) => (
              <tr key={p.id} className="border-t border-gray-100 dark:border-gray-700">
                <td className="pr-3">{(p.created_at || '').slice(0, 10)}</td>
                <td className="pr-3">{p.reference}</td>
                <td className="pr-3">{p.product_code} x{p.quantity}</td>
                <td className="pr-3">{p.amount} USD</td>
                <td className="pr-3">{STATUS[p.status] || p.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
