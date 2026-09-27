'use client'

import { useEffect, useState } from 'react'
import { useAdEligibility } from '@/hooks/use-ad-eligibility'
import { COOKIE_CONSENT_EVENT } from '@/components/ui/cookie-consent'

export const ADSENSE_SRC = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5582556318526474'
const COOKIE_CONSENT_KEY = 'myhigh5_cookie_consent'

export function hasAdvertisingConsent(): boolean {
  try {
    const value = JSON.parse(localStorage.getItem(COOKIE_CONSENT_KEY) || '{}')
    return value?.preferences?.advertising === true
  } catch {
    return false
  }
}

/**
 * Loads the AdSense script only when BOTH the viewer consented to advertising
 * cookies AND the backend says this viewer may receive AdSense (Phase 9). For an
 * ineligible viewer no request is ever made to the ad provider.
 */
export function AdSenseLoader() {
  const { adsense } = useAdEligibility()
  const [consented, setConsented] = useState(false)

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

  useEffect(() => {
    if (!adsense || !consented) return
    if (document.querySelector('script[src^="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"]')) return
    const load = () => {
      const s = document.createElement('script')
      s.async = true
      s.src = ADSENSE_SRC
      s.crossOrigin = 'anonymous'
      document.head.appendChild(s)
    }
    // After first paint so third-party JS doesn't compete with hydration.
    const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }
    if (w.requestIdleCallback) w.requestIdleCallback(load, { timeout: 3000 })
    else setTimeout(load, 1500)
  }, [adsense, consented])

  return null
}

/** One AdSense slot, rendered only for an eligible viewer. */
export function AdSenseSlot({ slot }: { slot: string }) {
  const { adsense } = useAdEligibility()

  useEffect(() => {
    if (!adsense) return
    try {
      const w = window as Window & { adsbygoogle?: unknown[] }
      ;(w.adsbygoogle = w.adsbygoogle || []).push({})
    } catch {
      /* the provider script may not be loaded yet */
    }
  }, [adsense])

  if (!adsense) return null
  return (
    <ins
      className="adsbygoogle"
      style={{ display: 'block' }}
      data-ad-client="ca-pub-5582556318526474"
      data-ad-slot={slot}
      data-ad-format="auto"
      data-full-width-responsive="true"
    />
  )
}
