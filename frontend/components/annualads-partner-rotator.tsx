'use client'

import Script from 'next/script'
import { ANNUALADS_PARTNER_ID, ANNUALADS_ROTATOR_SCRIPT_URL } from '@/lib/config'

/**
 * Annual Ads partner rotator — load once site-wide (layout/footer).
 * @see https://www.annualads.com/rotator.js
 */
export function AnnualAdsPartnerRotator() {
  const partnerId = ANNUALADS_PARTNER_ID?.trim()
  if (!partnerId || !ANNUALADS_ROTATOR_SCRIPT_URL) return null

  return (
    <Script
      id="annualads-partner-rotator"
      src={ANNUALADS_ROTATOR_SCRIPT_URL}
      strategy="lazyOnload"
      data-partner-id={partnerId}
    />
  )
}
