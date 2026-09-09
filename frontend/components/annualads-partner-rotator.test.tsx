import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/script', () => ({
  default: (props: Record<string, unknown>) => <script data-testid="annualads-script" {...props} />,
}))

vi.mock('@/lib/config', () => ({
  ANNUALADS_PARTNER_ID: 'partner-1',
  ANNUALADS_ROTATOR_SCRIPT_URL: 'https://www.annualads.com/rotator.js',
}))

import { AnnualAdsPartnerRotator } from './annualads-partner-rotator'
import { COOKIE_CONSENT_EVENT } from '@/components/ui/cookie-consent'

describe('AnnualAdsPartnerRotator', () => {
  beforeEach(() => localStorage.clear())

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
})
