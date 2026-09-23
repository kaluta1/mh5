'use client'

import { useCallback, useEffect, useState } from 'react'
import { Users } from 'lucide-react'
import api from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'
import { useBusinessModelSummary } from '@/components/dashboard/business-model-overview'

type PoolMe = {
  membership: null | {
    status: string
    entitlement_source: string
    joined_at: string | null
    reservation_expires_at: string | null
    assignments_received: number
  }
  assigned_referrals: number
}

type PaymentCreated = { invoice_url?: string | null; pay_address?: string; pay_amount?: string; pay_currency?: string }

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
    if (detail) return String(detail)
  }
  return e instanceof Error ? e.message : 'Request failed'
}

export default function ReferralPoolPage() {
  const { t } = useLanguage()
  const summary = useBusinessModelSummary()
  const [me, setMe] = useState<PoolMe | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [payment, setPayment] = useState<PaymentCreated | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await api.get<PoolMe>('/api/v1/referral-pool/me')
      if (res.status < 400) setMe(res.data)
    } catch (e) {
      setError(errorDetail(e))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const join = async () => {
    setBusy(true)
    setError(null)
    try {
      const idempotencyKey = `referral-pool-${Date.now()}-${Math.random().toString(36).slice(2)}`
      const res = await api.post<PaymentCreated>(
        '/api/v1/payments/create',
        { product_code: 'referral_pool_entry', amount: 100, currency: 'usd' },
        { headers: { 'Idempotency-Key': idempotencyKey } },
      )
      if (res.data?.invoice_url) {
        window.location.href = res.data.invoice_url
        return
      }
      setPayment(res.data)
      await load()
    } catch (e) {
      setError(errorDetail(e))
    } finally {
      setBusy(false)
    }
  }

  const pool = summary?.referral_pool
  const membership = me?.membership
  const canJoin = !membership && (pool?.is_open ?? true)

  return (
    <div className="space-y-6 pb-10 max-w-3xl">
      <div>
        <h1 className="flex items-center gap-3 text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">
          <Users className="w-7 h-7 text-myhigh5-primary" aria-hidden="true" />
          {t('business_model.pool_page_title')}
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-300">{t('business_model.pool_body')}</p>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t('business_model.pool_legacy_note')}</p>
      </div>

      {pool && (
        <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('business_model.pool_seats')}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {pool.seats_in_use.toLocaleString()} / {pool.capacity.toLocaleString()}
          </p>
          <div className="mt-2 h-2 rounded-full bg-gray-100 dark:bg-gray-700" aria-hidden="true">
            <div
              className="h-2 rounded-full bg-myhigh5-primary"
              style={{ width: `${Math.min(100, (pool.seats_in_use / Math.max(1, pool.capacity)) * 100)}%` }}
            />
          </div>
        </div>
      )}

      <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 space-y-3">
        <h2 className="font-semibold text-gray-900 dark:text-white">{t('business_model.pool_status')}</h2>
        {membership ? (
          <>
            <p className="font-medium text-myhigh5-primary">{t(`business_model.status_${membership.status}`)}</p>
            <p className="text-sm text-gray-600 dark:text-gray-300">{t(`business_model.source_${membership.entitlement_source}`)}</p>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {t('business_model.pool_referrals_received')}: {me?.assigned_referrals ?? 0}
            </p>
          </>
        ) : (
          <p className="text-gray-600 dark:text-gray-300">{t('business_model.pool_not_member')}</p>
        )}
        {canJoin && (
          <button
            type="button"
            onClick={join}
            disabled={busy}
            className="rounded-lg bg-myhigh5-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? t('business_model.pool_joining') : t('business_model.pool_join')}
          </button>
        )}
        {!membership && pool && !pool.is_open && <p className="text-sm text-amber-700">{t('business_model.pool_full')}</p>}
        {payment && (
          <p className="text-sm text-gray-600 dark:text-gray-300 break-all">
            {payment.pay_amount} {payment.pay_currency?.toUpperCase()} → {payment.pay_address}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}
