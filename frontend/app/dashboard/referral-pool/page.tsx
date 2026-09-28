'use client'

import { useCallback, useEffect, useState } from 'react'
import { Users } from 'lucide-react'
import api from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'
import { apiErrorText } from '@/lib/financial-eligibility'

type PoolMe = {
  retired?: boolean
  membership: null | {
    status: string
    entitlement_source: string
    joined_at: string | null
    reservation_expires_at: string | null
    assignments_received: number
  }
  assigned_referrals: number
}

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return apiErrorText(detail, 'Request failed')
  }
  return e instanceof Error ? e.message : 'Request failed'
}

/** The Referral Pool is retired: this page only shows a member's own historical record. */
export default function ReferralPoolPage() {
  const { t } = useLanguage()
  const [me, setMe] = useState<PoolMe | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  const membership = me?.membership

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
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}
