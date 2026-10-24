'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'
import { apiErrorText } from '@/lib/financial-eligibility'

type Eligibility = {
  sales_enabled: boolean
  unit_price: string
  currency: string
  eligible: boolean
  reason: string | null
  max_units_per_purchase: number | null
  max_units_per_member?: number | null
  units_reserved?: number
  kyc_approved?: boolean
}

type Purchase = {
  id: number
  quantity: number
  total_amount: string
  status: string
  payment: { deposit_id: number; status: string | null }
  units: Record<string, number>
  refund?: { refunded_units: number; in_review_units: number }
  created_at?: string | null
}

type Purchases = { active_units: number; purchases: Purchase[]; page?: number; page_size?: number; total?: number }

type Checkout = { checkout_url?: string | null; invoice_url?: string | null }

const MAX_PER_PAYMENT = 10000 // the server's technical guard per payment
const PAGE_SIZE = 10

/** Display only: the server prices the order itself (quantity x its own unit price). */
export function unitsTotal(quantity: number, unitPrice: string): string {
  const cents = Math.round(Number(unitPrice) * 100)
  return ((quantity * cents) / 100).toFixed(2)
}

export function validQuantity(raw: string, max: number | null): number | null {
  if (!/^\d+$/.test(raw.trim())) return null
  const n = Number(raw)
  const limit = Math.min(max ?? MAX_PER_PAYMENT, MAX_PER_PAYMENT)
  return n >= 1 && n <= limit ? n : null
}

/** The most units this member may add now: the per-purchase limit and what is left of the per-member limit. */
export function allowedNow(e: Pick<Eligibility, 'max_units_per_purchase' | 'max_units_per_member' | 'units_reserved'>): number | null {
  const left = e.max_units_per_member != null ? Math.max(e.max_units_per_member - (e.units_reserved ?? 0), 0) : null
  const caps = [e.max_units_per_purchase, left].filter((c): c is number => c != null)
  return caps.length ? Math.min(...caps) : null
}

function newIdempotencyKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return apiErrorText(detail, 'Request failed')
  }
  return e instanceof Error ? e.message : 'Request failed'
}

/** Multi-Unit Referral Pool purchase card: price, quantity, total, eligibility and limits, a
 * confirmation step, then one payment. The server re-checks everything and prices the order. */
export function ReferralPoolUnitsCard({ onChange }: { onChange?: () => void } = {}) {
  const { t } = useLanguage()
  const [eligibility, setEligibility] = useState<Eligibility | null>(null)
  const [history, setHistory] = useState<Purchases>({ active_units: 0, purchases: [] })
  const [page, setPage] = useState(1)
  const [rawQuantity, setRawQuantity] = useState('1')
  const [reviewing, setReviewing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [paymentLink, setPaymentLink] = useState<string | null>(null)

  const label = (key: string, fallbackKey: string) => (t(key) !== key ? t(key) : t(fallbackKey))

  const load = useCallback(async () => {
    try {
      const [e, p] = await Promise.all([
        api.get<Eligibility>('/api/v1/referral-pool/units/eligibility'),
        api.get<Purchases>('/api/v1/referral-pool/units/purchases', { params: { page, page_size: PAGE_SIZE } }),
      ])
      setEligibility(e.data)
      setHistory(p.data)
    } catch (err) {
      setError(errorDetail(err))
    }
  }, [page])

  useEffect(() => {
    load()
  }, [load])

  if (!eligibility) return null
  const cap = allowedNow(eligibility)
  const quantity = validQuantity(rawQuantity, cap)
  const canBuy = eligibility.sales_enabled && eligibility.eligible && cap !== 0
  const total = history.total ?? history.purchases.length
  const pages = Math.max(1, Math.ceil(total / (history.page_size ?? PAGE_SIZE)))

  const buy = async () => {
    if (!quantity || busy || !canBuy) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.post<Checkout>(
        '/api/v1/payments/create',
        {
          product_code: 'referral_pool_entry',
          quantity,
          amount: unitsTotal(quantity, eligibility.unit_price),
          currency: 'usd',
        },
        { headers: { 'Idempotency-Key': newIdempotencyKey() } },
      )
      const link = res.data.checkout_url || res.data.invoice_url || null
      setPaymentLink(link)
      setReviewing(false)
      if (link) window.location.assign(link)
      await load()
      onChange?.()
    } catch (err) {
      setError(errorDetail(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 space-y-4">
      <h2 className="font-semibold text-gray-900 dark:text-white">{t('business_model.units_title')}</h2>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm text-gray-600 dark:text-gray-300">
        <div className="flex justify-between gap-2">
          <dt>{t('business_model.units_price')}</dt>
          <dd className="font-medium text-gray-900 dark:text-white">${eligibility.unit_price} {eligibility.currency}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>{t('business_model.units_kyc_status')}</dt>
          <dd data-testid="units-kyc" className="font-medium text-gray-900 dark:text-white">
            {eligibility.kyc_approved ? t('business_model.units_kyc_approved') : t('business_model.units_kyc_missing')}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>{t('business_model.units_limit_purchase')}</dt>
          <dd data-testid="units-limit-purchase">{eligibility.max_units_per_purchase ?? t('business_model.units_no_limit')}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>{t('business_model.units_limit_member')}</dt>
          <dd data-testid="units-limit-member">{eligibility.max_units_per_member ?? t('business_model.units_no_limit')}</dd>
        </div>
      </dl>

      {!eligibility.sales_enabled ? (
        <p data-testid="units-unavailable" className="font-medium text-gray-700 dark:text-gray-200">
          {t('business_model.units_unavailable')}
        </p>
      ) : !eligibility.eligible ? (
        <p data-testid="units-ineligible" className="text-amber-700 dark:text-amber-400">
          {label(`business_model.units_reason_${eligibility.reason}`, 'business_model.units_reason_default')}
        </p>
      ) : cap === 0 ? (
        <p data-testid="units-ineligible" className="text-amber-700 dark:text-amber-400">
          {t('business_model.units_reason_MEMBER_LIMIT')}
        </p>
      ) : null}

      {canBuy && !reviewing && (
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm text-gray-700 dark:text-gray-200">
            {t('business_model.units_quantity')}
            <input
              aria-label={t('business_model.units_quantity')}
              inputMode="numeric"
              value={rawQuantity}
              onChange={(e) => setRawQuantity(e.target.value)}
              className="mt-1 block w-28 rounded border border-gray-300 dark:border-gray-600 bg-transparent px-2 py-1"
            />
          </label>
          <p className="text-sm font-medium text-gray-900 dark:text-white" data-testid="units-total">
            {t('business_model.units_total')}: ${quantity ? unitsTotal(quantity, eligibility.unit_price) : '-'}
          </p>
          <button
            type="button"
            onClick={() => setReviewing(true)}
            disabled={!quantity}
            className="rounded bg-myhigh5-primary px-4 py-2 text-white disabled:opacity-50"
          >
            {t('business_model.units_buy')}
          </button>
        </div>
      )}

      {canBuy && reviewing && quantity && (
        <div data-testid="units-review" className="rounded-lg border border-myhigh5-primary/40 p-4 space-y-2">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('business_model.units_review')}</h3>
          <p className="text-sm text-gray-700 dark:text-gray-200">
            {quantity} x ${eligibility.unit_price} = <strong>${unitsTotal(quantity, eligibility.unit_price)}</strong> {eligibility.currency}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('business_model.units_confirm_note')}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={buy} disabled={busy} className="rounded bg-myhigh5-primary px-4 py-2 text-white disabled:opacity-50">
              {busy ? t('business_model.units_buying') : t('business_model.units_confirm')}
            </button>
            <button type="button" onClick={() => setReviewing(false)} disabled={busy} className="rounded bg-gray-100 dark:bg-gray-700 px-4 py-2">
              {t('business_model.units_change')}
            </button>
          </div>
        </div>
      )}
      {paymentLink && (
        <a href={paymentLink} className="text-sm text-myhigh5-primary underline">
          {t('business_model.units_continue')}
        </a>
      )}

      <div className="space-y-2">
        <p className="text-sm text-gray-700 dark:text-gray-200">
          {t('business_model.units_active')}: <span data-testid="units-active">{history.active_units}</span>
        </p>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('business_model.units_purchases')}</h3>
        {history.purchases.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('business_model.units_none')}</p>
        ) : (
          <ul className="text-sm text-gray-600 dark:text-gray-300 divide-y divide-gray-100 dark:divide-gray-700" data-testid="units-history">
            {history.purchases.map((p) => (
              <li key={p.id} className="py-2 flex flex-wrap gap-x-3 gap-y-1">
                <span className="font-medium text-gray-900 dark:text-white">
                  {p.quantity} x ${(Number(p.total_amount) / Math.max(p.quantity, 1)).toFixed(2)} = ${p.total_amount}
                </span>
                <span>{label(`business_model.units_status_${p.status}`, 'business_model.units_payment')}</span>
                <span>
                  {t('business_model.units_payment')}: {p.payment.status ?? '-'}
                </span>
                {p.refund && (p.refund.refunded_units > 0 || p.refund.in_review_units > 0) && (
                  <span data-testid={`units-refund-${p.id}`}>
                    {t('business_model.units_refund')}: {p.refund.refunded_units} {t('business_model.units_refunded')}
                    {p.refund.in_review_units > 0 && `, ${p.refund.in_review_units} ${t('business_model.units_refund_review')}`}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {pages > 1 && (
          <div className="flex items-center gap-2 text-sm">
            <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded bg-gray-100 dark:bg-gray-700 px-2 py-1 disabled:opacity-50">
              {t('referral_pool.page_previous')}
            </button>
            <span>
              {t('referral_pool.page_label')} {page} / {pages}
            </span>
            <button type="button" disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded bg-gray-100 dark:bg-gray-700 px-2 py-1 disabled:opacity-50">
              {t('referral_pool.page_next')}
            </button>
          </div>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}
