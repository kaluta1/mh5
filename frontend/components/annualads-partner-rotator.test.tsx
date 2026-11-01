import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/script', () => ({
  default: (props: Record<string, unknown>) => <script data-testid="annualads-script" {...props} />,
}))

const { eligibility } = vi.hoisted(() => ({ eligibility: { annualads_rotator: true } }))

// Phase 9: the backend's per-viewer ad decision (mocked; its own tests cover it).
vi.mock('@/hooks/use-ad-eligibility', () => ({
  useAdEligibility: () => ({ adsense: false, annualads_sponsor: false, ...eligibility }),
}))

const { nav } = vi.hoisted(() => ({ nav: { pathname: '/contests' as string | null } }))
// Placement control: ad scripts load only on allowed public content routes.
vi.mock('next/navigation', () => ({ usePathname: () => nav.pathname }))
vi.mock('@/lib/config', () => ({
  ANNUALADS_PARTNER_ID: 'partner-1',
  ANNUALADS_ROTATOR_SCRIPT_URL: 'https://www.annualads.com/rotator.js',
}))

import { AnnualAdsPartnerRotator } from './annualads-partner-rotator'
import { COOKIE_CONSENT_EVENT } from '@/components/ui/cookie-consent'

describe('AnnualAdsPartnerRotator', () => {
  beforeEach(() => {
    localStorage.clear()
    eligibility.annualads_rotator = true
  })

  it('does not load third-party advertising before consent', () => {
    render(<AnnualAdsPartnerRotator />)
    expect(screen.queryByTestId('annualads-script')).toBeNull()
  })

  it('loads after explicit advertising consent', () => {
    render(<AnnualAdsPartnerRotator />)
    localStorage.setItem(
      'myhigh5_cookie_consent',
      JSON.stringify({ preferences: { advertising: true } })
    )
    act(() => window.dispatchEvent(new Event(COOKIE_CONSENT_EVENT)))
    expect(screen.getByTestId('annualads-script')).toHaveAttribute(
      'src',
      'https://www.annualads.com/rotator.js'
    )
  })

  it('never loads for a viewer the backend does not allow, even with consent (Phase 9)', () => {
    eligibility.annualads_rotator = false
    localStorage.setItem('myhigh5_cookie_consent', JSON.stringify({ preferences: { advertising: true } }))
    render(<AnnualAdsPartnerRotator />)
    act(() => window.dispatchEvent(new Event(COOKIE_CONSENT_EVENT)))
    expect(screen.queryByTestId('annualads-script')).toBeNull()
  })
})

describe('AnnualAdsPartnerRotator placement control', () => {
  it('never loads on excluded routes (messages, settings, wallet, KYC, admin, payments)', () => {
    localStorage.setItem('myhigh5_cookie_consent', JSON.stringify({ preferences: { advertising: true } }))
    for (const path of ['/dashboard/messages', '/dashboard/settings', '/dashboard/wallet', '/dashboard/kyc',
      '/dashboard/admin/finance', '/payments/checkout']) {
      nav.pathname = path
      const { unmount } = render(<AnnualAdsPartnerRotator />)
      expect(screen.queryByTestId('annualads-script')).toBeNull()
      unmount()
    }
    nav.pathname = '/contests'
  })
})
