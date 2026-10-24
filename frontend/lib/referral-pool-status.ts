'use client'

import { useEffect, useState } from 'react'
import api from '@/lib/api'

export type ReferralPoolStatus = { sales_enabled: boolean; allocation_enabled: boolean } | null

/** The public launch state from GET /referral-pool/status; null while loading or when it cannot be read. */
export function useReferralPoolStatus(): ReferralPoolStatus {
  const [status, setStatus] = useState<ReferralPoolStatus>(null)
  useEffect(() => {
    let live = true
    Promise.resolve(api.get<ReferralPoolStatus>('/api/v1/referral-pool/status'))
      .then((res) => {
        const data = res?.data
        if (live && data && typeof data.sales_enabled === 'boolean') setStatus(data)
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [])
  return status
}

/** Launch-status wording driven by the real switches; unknown means "not launched" (never claims more). */
export function referralPoolLaunchText(t: (key: string) => string, status: ReferralPoolStatus): string {
  if (!status || (!status.sales_enabled && !status.allocation_enabled)) return t('referral_pool.launch_pending')
  return [
    t(status.sales_enabled ? 'referral_pool.status_sales_on' : 'referral_pool.status_sales_off'),
    t(status.allocation_enabled ? 'referral_pool.status_allocation_on' : 'referral_pool.status_allocation_off'),
  ].join(' ')
}

export function referralPoolFaqAnswer(t: (key: string) => string, status: ReferralPoolStatus): string {
  return `${t('landing.faq.answer_referral_pool')} ${referralPoolLaunchText(t, status)}`
}
