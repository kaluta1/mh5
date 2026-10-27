'use client'

import { useEffect } from 'react'
import { usePathname } from 'next/navigation'

/** The key the register page reads (and several pages already write) for a personal invitation. */
export const REFERRAL_STORAGE_KEY = 'referral_code'
const CODE_RE = /^[A-Za-z0-9_-]{2,64}$/

/** The invitation code carried by a page URL (?ref= or ?referral=), if it is well formed. */
export function referralCodeFromSearch(search: string): string | null {
  const params = new URLSearchParams(search)
  const code = (params.get('ref') || params.get('referral') || '').trim()
  return CODE_RE.test(code) ? code : null
}

/**
 * The existing invitation rule, applied on EVERY page instead of only some: a ?ref= in the URL is
 * remembered for registration and the latest one wins (as the home, contests, feed, entry, login,
 * register and pitching pages already do). An invitation short link can lead to any shareable page,
 * so its ?ref= must count wherever it lands. Nothing is removed or replaced without a new ?ref=; the
 * server still decides eligibility and never replaces an existing sponsor.
 */
export function ReferralCapture() {
  const pathname = usePathname()
  useEffect(() => {
    try {
      const code = referralCodeFromSearch(window.location.search)
      if (code) localStorage.setItem(REFERRAL_STORAGE_KEY, code)
    } catch {
      /* storage unavailable: the signed attribution cookie still applies */
    }
  }, [pathname])
  return null
}
