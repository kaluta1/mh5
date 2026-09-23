'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Crown, Percent, ShoppingBag, Users } from 'lucide-react'
import api from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'

export type BusinessModelSummary = {
  business_model_version: string | null
  direct_commission_rate: number
  referral_pool: { price_usd: number; capacity: number; seats_in_use: number; active_members: number; is_open: boolean }
  leaders: { pool_rate: number; max_members: number }
  marketplace: { markup_rate: number; enabled: boolean }
}

export function useBusinessModelSummary() {
  const [summary, setSummary] = useState<BusinessModelSummary | null>(null)
  useEffect(() => {
    let cancelled = false
    api
      .get<BusinessModelSummary>('/api/v1/business-model/summary')
      .then((res) => {
        if (!cancelled && res.status < 400) setSummary(res.data)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])
  return summary
}

function Section({ icon: Icon, title, children }: { icon: typeof Users; title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 shadow-sm">
      <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-white">
        <Icon className="w-5 h-5 text-myhigh5-primary" aria-hidden="true" />
        {title}
      </h2>
      <div className="mt-3 space-y-2 text-sm sm:text-base text-gray-600 dark:text-gray-300">{children}</div>
    </section>
  )
}

/** Explains the current (NEW_V2) business model. Figures come from the server. */
export function BusinessModelOverview() {
  const { t } = useLanguage()
  const summary = useBusinessModelSummary()
  const pool = summary?.referral_pool

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">{t('business_model.program_title')}</h1>
        <p className="mt-2 text-gray-500 dark:text-gray-400">{t('business_model.program_subtitle')}</p>
      </div>

      <Section icon={Percent} title={t('business_model.direct_title')}>
        <p>{t('business_model.direct_body')}</p>
        <p className="text-gray-500 dark:text-gray-400">{t('business_model.direct_example')}</p>
      </Section>

      <Section icon={Users} title={t('business_model.pool_title')}>
        <p>{t('business_model.pool_body')}</p>
        <p className="text-gray-500 dark:text-gray-400">{t('business_model.pool_legacy_note')}</p>
        {pool && (
          <p className="font-medium text-gray-800 dark:text-gray-200">
            {t('business_model.pool_seats')}: {pool.seats_in_use.toLocaleString()} / {pool.capacity.toLocaleString()}
          </p>
        )}
        <Link href="/dashboard/referral-pool" className="inline-block text-sm font-medium text-myhigh5-primary underline underline-offset-4">
          {t('business_model.learn_more')}
        </Link>
      </Section>

      <Section icon={Crown} title={t('business_model.leaders_title')}>
        <p>{t('business_model.leaders_body')}</p>
        <p className="text-gray-500 dark:text-gray-400">{t('business_model.leaders_formula')}</p>
        <Link href="/dashboard/leaders" className="inline-block text-sm font-medium text-myhigh5-primary underline underline-offset-4">
          {t('business_model.learn_more')}
        </Link>
      </Section>

      <Section icon={ShoppingBag} title={t('business_model.marketplace_title')}>
        <p>{t('business_model.marketplace_body')}</p>
        {summary && !summary.marketplace.enabled && (
          <p className="text-gray-500 dark:text-gray-400">{t('business_model.marketplace_pending')}</p>
        )}
      </Section>

      <p className="text-sm text-gray-500 dark:text-gray-400">{t('business_model.history_note')}</p>
    </div>
  )
}
