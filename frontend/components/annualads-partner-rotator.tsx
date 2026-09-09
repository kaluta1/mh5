'use client'

import Script from 'next/script'
import { useEffect, useState } from 'react'
import { ANNUALADS_PARTNER_ID, ANNUALADS_ROTATOR_SCRIPT_URL } from '@/lib/config'
import { COOKIE_CONSENT_EVENT } from '@/components/ui/cookie-consent'

const COOKIE_CONSENT_KEY = 'myhigh5_cookie_consent'

function hasAdvertisingConsent(): boolean {
  try {
    const value = JSON.parse(localStorage.getItem(COOKIE_CONSENT_KEY) || '{}')
    return value?.preferences?.advertising === true
  } catch {
    return false
  }
}

/**
 * Annual Ads partner rotator — load once site-wide (layout/footer).
 * @see https://www.annualads.com/rotator.js
 */
export function AnnualAdsPartnerRotator() {
  const [consented, setConsented] = useState(false)
  const partnerId = ANNUALADS_PARTNER_ID?.trim()

  useEffect(() => {
    const refresh = () => setConsented(hasAdvertisingConsent())
    refresh()
    window.addEventListener('storage', refresh)
    window.addEventListener(COOKIE_CONSENT_EVENT, refresh)
    return () => {
      window.removeEventListener('storage', refresh)
      window.removeEventListener(COOKIE_CONSENT_EVENT, refresh)
    }
  }, [])

  if (!consented || !partnerId || !ANNUALADS_ROTATOR_SCRIPT_URL) return null

  return (
    <Script
      id="annualads-partner-rotator"
      src={ANNUALADS_ROTATOR_SCRIPT_URL}
      strategy="lazyOnload"
      data-partner-id={partnerId}
    />
  )
}
