'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'
import { apiErrorText } from '@/lib/financial-eligibility'

export type PoolDashboard = {
  sales_enabled: boolean
  allocation_enabled: boolean
  units: {
    purchased: number
    active: number
    suspended: number
    refunded: number
    revoked: number
    pending: number
    waiting_for_next_round: number
  }
  pending_purchases: { count: number; units: number }
  amounts: { paid: string; refunded: string; net_spent: string; currency: string }
  current_round: null | {
    round_number: number
    status: string
    total_slots: number
    filled_slots: number
    void_slots: number
    remaining_slots: number
  }
  my_slots: { open: number; filled: number; void: number }
  assignments: { round_based: number; historical: number }
  recent_assignments: Assignment[]
  waiting_referrals: number
  my_queue_entry: null | { status: string; enqueued_at: string | null }
}

type Assignment = { id: number; assigned_at: string | null; round_number: number | null; kind: string }
type Paged<T> = { items: T[]; page: number; page_size: number; total: number }

const PAGE_SIZE = 10

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return apiErrorText(detail, 'Request failed')
  }
  return e instanceof Error ? e.message : 'Request failed'
}

function Stat({ label, value, hint, testId }: { label: string; value: string | number; hint?: string; testId: string }) {
  return (
    <div className="rounded-lg border border-gray-100 dark:border-gray-700 p-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p data-testid={testId} className="text-xl font-bold text-gray-900 dark:text-white">
        {value}
      </p>
      {hint && <p className="text-xs text-gray-400">{hint}</p>}
    </div>
  )
}

/** Launch state, shown on the member and public pages. */
export function ReferralPoolLaunchStatus({ salesEnabled, allocationEnabled }: { salesEnabled: boolean; allocationEnabled: boolean }) {
  const { t } = useLanguage()
  return (
    <div role="status" data-testid="pool-launch-status" className="rounded-xl border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-4 text-sm space-y-1">
      <p className="font-semibold text-gray-900 dark:text-white">{t('referral_pool.status_title')}</p>
      <p>{salesEnabled ? t('referral_pool.status_sales_on') : t('referral_pool.status_sales_off')}</p>
      <p>{allocationEnabled ? t('referral_pool.status_allocation_on') : t('referral_pool.status_allocation_off')}</p>
      <p className="text-gray-600 dark:text-gray-300">{t('referral_pool.not_guaranteed')}</p>
    </div>
  )
}

/** The member's own Referral Pool numbers. Slots are opportunities; only assignments are referrals received. */
export function ReferralPoolDashboard({ refreshKey = 0 }: { refreshKey?: number }) {
  const { t } = useLanguage()
  const [data, setData] = useState<PoolDashboard | null>(null)
  const [history, setHistory] = useState<Paged<Assignment> | null>(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [d, h] = await Promise.all([
        api.get<PoolDashboard>('/api/v1/referral-pool/units/dashboard'),
        api.get<Paged<Assignment>>('/api/v1/referral-pool/units/assignments', { params: { page, page_size: PAGE_SIZE } }),
      ])
      setData(d.data)
      setHistory(h.data)
    } catch (err) {
      setError(errorDetail(err))
    }
  }, [page])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  if (!data) {
    return error ? (
      <p role="alert" className="text-sm text-red-600">
        {error}
      </p>
    ) : null
  }
  const round = data.current_round
  const pages = history ? Math.max(1, Math.ceil(history.total / history.page_size)) : 1
  const kind = (a: Assignment) =>
    a.kind === 'ROUND' ? `${t('referral_pool.kind_ROUND')} ${a.round_number ?? ''}`.trim() : t('referral_pool.kind_HISTORICAL')

  return (
    <div className="space-y-4">
      <ReferralPoolLaunchStatus salesEnabled={data.sales_enabled} allocationEnabled={data.allocation_enabled} />

      <section className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 space-y-3">
        <h2 className="font-semibold text-gray-900 dark:text-white">{t('referral_pool.dashboard_title')}</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Stat testId="stat-purchased" label={t('referral_pool.stat_purchased')} value={data.units.purchased} />
          <Stat testId="stat-active" label={t('referral_pool.stat_active')} value={data.units.active} />
          <Stat testId="stat-suspended" label={t('referral_pool.stat_suspended')} value={data.units.suspended} />
          <Stat testId="stat-refunded" label={t('referral_pool.stat_refunded')} value={data.units.refunded} />
          <Stat testId="stat-pending" label={t('referral_pool.stat_pending_purchases')} value={data.pending_purchases.count} />
          <Stat
            testId="stat-spent"
            label={t('referral_pool.stat_spent')}
            value={`$${data.amounts.net_spent}`}
            hint={t('referral_pool.stat_spent_hint')}
          />
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-300">
          {t('referral_pool.stat_next_round')}: <span data-testid="stat-next-round">{data.units.waiting_for_next_round}</span>
        </p>
      </section>

      <section className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 space-y-3">
        <h2 className="font-semibold text-gray-900 dark:text-white">{t('referral_pool.round_title')}</h2>
        {round ? (
          <div data-testid="pool-round" className="text-sm text-gray-700 dark:text-gray-200 space-y-1">
            <p>
              {t('referral_pool.round_number')} {round.round_number} · {t('referral_pool.round_slots')}: {round.total_slots} ·{' '}
              {t('referral_pool.round_remaining')}: {round.remaining_slots}
            </p>
            <h3 className="font-medium pt-2">{t('referral_pool.my_slots_title')}</h3>
            <ul className="list-disc pl-5">
              <li>
                {t('referral_pool.my_slots_open')}: <span data-testid="slots-open">{data.my_slots.open}</span>
              </li>
              <li>
                {t('referral_pool.my_slots_filled')}: <span data-testid="slots-filled">{data.my_slots.filled}</span>
              </li>
              <li>
                {t('referral_pool.my_slots_void')}: {data.my_slots.void}
              </li>
            </ul>
          </div>
        ) : (
          <p data-testid="pool-no-round" className="text-sm text-gray-600 dark:text-gray-300">
            {t('referral_pool.round_none')}
          </p>
        )}
        <p className="text-xs text-gray-500 dark:text-gray-400">{t('referral_pool.slots_hint')}</p>
        <p className="text-sm text-gray-600 dark:text-gray-300">
          {t('referral_pool.waiting_total')}: {data.waiting_referrals}
        </p>
        {data.my_queue_entry && (
          <p data-testid="pool-my-queue" className="text-sm text-gray-700 dark:text-gray-200">
            {t('referral_pool.queue_title')}: {t(`referral_pool.queue_${data.my_queue_entry.status}`)}
          </p>
        )}
      </section>

      <section className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 space-y-3">
        <h2 className="font-semibold text-gray-900 dark:text-white">{t('referral_pool.assignments_title')}</h2>
        <p className="text-sm text-gray-700 dark:text-gray-200">
          {t('referral_pool.assignments_round')}: <span data-testid="assigned-round">{data.assignments.round_based}</span> ·{' '}
          {t('referral_pool.assignments_historical')}: <span data-testid="assigned-historical">{data.assignments.historical}</span>
        </p>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('referral_pool.history_title')}</h3>
        {!history || history.items.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('referral_pool.assignments_none')}</p>
        ) : (
          <ul data-testid="assignment-history" className="text-sm text-gray-600 dark:text-gray-300 divide-y divide-gray-100 dark:divide-gray-700">
            {history.items.map((a) => (
              <li key={a.id} className="py-1 flex justify-between gap-3">
                <span>{kind(a)}</span>
                <span>{a.assigned_at ? new Date(a.assigned_at).toLocaleDateString() : '-'}</span>
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
      </section>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}
