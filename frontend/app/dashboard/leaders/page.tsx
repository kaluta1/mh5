'use client'

import { useEffect, useState } from 'react'
import { Crown } from 'lucide-react'
import api from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'

type LeadersMe = {
  current_month_direct_commission: number
  current_month_unpaid_direct_commission?: number
  rewards: { period: string; rank: number; direct_commission: number; ratio: number; reward: number; payout_status: string }[]
}
type Period = { period: string; eligible_company_revenue: number; pool_amount: number; qualifying_members: number }

const usd = (n: number) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function LeadersPage() {
  const { t } = useLanguage()
  const [me, setMe] = useState<LeadersMe | null>(null)
  const [periods, setPeriods] = useState<Period[]>([])

  useEffect(() => {
    api.get<LeadersMe>('/api/v1/leaders/me').then((r) => r.status < 400 && setMe(r.data)).catch(() => undefined)
    api.get<Period[]>('/api/v1/leaders/periods').then((r) => r.status < 400 && setPeriods(r.data)).catch(() => undefined)
  }, [])

  return (
    <div className="space-y-6 pb-10 max-w-4xl">
      <div>
        <h1 className="flex items-center gap-3 text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">
          <Crown className="w-7 h-7 text-myhigh5-primary" aria-hidden="true" />
          {t('business_model.leaders_page_title')}
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-300">{t('business_model.leaders_body')}</p>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t('business_model.leaders_formula')}</p>
      </div>

      <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <p className="text-sm text-gray-500 dark:text-gray-400">{t('business_model.leaders_this_month')}</p>
        <p className="text-2xl font-bold text-gray-900 dark:text-white">{usd(me?.current_month_direct_commission ?? 0)}</p>
        {(me?.current_month_unpaid_direct_commission ?? 0) > 0 && (
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('business_model.leaders_unpaid_this_month')}: {usd(me?.current_month_unpaid_direct_commission ?? 0)}
          </p>
        )}
      </div>

      <section className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 overflow-x-auto">
        <h2 className="font-semibold text-gray-900 dark:text-white mb-3">{t('business_model.leaders_my_rewards')}</h2>
        {me && me.rewards.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="text-left text-gray-500 dark:text-gray-400">
              <tr>
                <th className="py-1 pr-3">{t('business_model.col_period')}</th>
                <th className="py-1 pr-3">{t('business_model.col_rank')}</th>
                <th className="py-1 pr-3">{t('business_model.col_direct')}</th>
                <th className="py-1 pr-3">{t('business_model.col_share')}</th>
                <th className="py-1 pr-3">{t('business_model.col_reward')}</th>
                <th className="py-1">{t('business_model.col_status')}</th>
              </tr>
            </thead>
            <tbody className="text-gray-800 dark:text-gray-200">
              {me.rewards.map((r) => (
                <tr key={r.period} className="border-t border-gray-100 dark:border-gray-700">
                  <td className="py-1 pr-3">{r.period}</td>
                  <td className="py-1 pr-3">{r.rank}</td>
                  <td className="py-1 pr-3">{usd(r.direct_commission)}</td>
                  <td className="py-1 pr-3">{(r.ratio * 100).toFixed(4)}%</td>
                  <td className="py-1 pr-3 font-semibold">{usd(r.reward)}</td>
                  <td className="py-1">{r.payout_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('business_model.leaders_no_rewards')}</p>
        )}
      </section>

      {periods.length > 0 && (
        <section className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 overflow-x-auto">
          <h2 className="font-semibold text-gray-900 dark:text-white mb-3">{t('business_model.leaders_recent')}</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-gray-500 dark:text-gray-400">
              <tr>
                <th className="py-1 pr-3">{t('business_model.col_period')}</th>
                <th className="py-1 pr-3">{t('business_model.col_revenue')}</th>
                <th className="py-1 pr-3">{t('business_model.col_pool')}</th>
                <th className="py-1">{t('business_model.col_members')}</th>
              </tr>
            </thead>
            <tbody className="text-gray-800 dark:text-gray-200">
              {periods.map((p) => (
                <tr key={p.period} className="border-t border-gray-100 dark:border-gray-700">
                  <td className="py-1 pr-3">{p.period}</td>
                  <td className="py-1 pr-3">{usd(p.eligible_company_revenue)}</td>
                  <td className="py-1 pr-3">{usd(p.pool_amount)}</td>
                  <td className="py-1">{p.qualifying_members}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
