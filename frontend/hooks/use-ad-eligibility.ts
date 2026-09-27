'use client'

import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { useAuth } from '@/hooks/use-auth'

/** Ad sources the backend decides per viewer (Phase 9, s.33 "never serve
 * age-inappropriate advertisements to minors"). Default = nothing (fail closed). */
export type AdSource = 'adsense' | 'annualads_rotator' | 'annualads_sponsor'
export type AdEligibility = Record<AdSource, boolean>

export const NO_ADS: AdEligibility = { adsense: false, annualads_rotator: false, annualads_sponsor: false }

export async function fetchAdEligibility(): Promise<AdEligibility> {
  try {
    const response = await api.get<{ sources?: Partial<AdEligibility> }>('/api/v1/ads/eligibility')
    if (response.status >= 400 || !response.data?.sources) return NO_ADS
    const sources = response.data.sources
    return {
      adsense: sources.adsense === true,
      annualads_rotator: sources.annualads_rotator === true,
      annualads_sponsor: sources.annualads_sponsor === true,
    }
  } catch {
    return NO_ADS
  }
}

/** Re-evaluated whenever the signed-in account changes; nothing until the backend answers. */
export function useAdEligibility(): AdEligibility {
  const { user } = useAuth()
  const [eligibility, setEligibility] = useState<AdEligibility>(NO_ADS)
  const userId = user?.id ?? null

  useEffect(() => {
    let cancelled = false
    setEligibility(NO_ADS)
    fetchAdEligibility().then((value) => {
      if (!cancelled) setEligibility(value)
    })
    return () => {
      cancelled = true
    }
  }, [userId])

  return eligibility
}
