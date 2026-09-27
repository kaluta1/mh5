import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock, auth } = vi.hoisted(() => ({ getMock: vi.fn(), auth: { user: null as null | { id: number } } }))

vi.mock('@/lib/api', () => ({ default: { get: getMock }, apiService: {} }))
vi.mock('@/hooks/use-auth', () => ({ useAuth: () => auth }))

import { AdSenseLoader, AdSenseSlot } from './adsense-loader'
import { fetchAdEligibility, NO_ADS } from '@/hooks/use-ad-eligibility'
import { COOKIE_CONSENT_EVENT } from '@/components/ui/cookie-consent'

const scripts = () => document.querySelectorAll('script[src^="https://pagead2.googlesyndication.com"]')

function eligibility(sources: Record<string, unknown> | null, status = 200) {
  getMock.mockResolvedValue({ status, data: sources === null ? {} : { sources } })
}

describe('Phase 9 age-safe ad delivery (frontend)', () => {
  beforeEach(() => {
    getMock.mockReset()
    localStorage.clear()
    document.head.querySelectorAll('script').forEach((s) => s.remove())
    vi.useRealTimers()
  })

  it('fails closed on errors, missing or malformed eligibility', async () => {
    getMock.mockRejectedValue(new Error('network'))
    expect(await fetchAdEligibility()).toEqual(NO_ADS)
    eligibility(null)
    expect(await fetchAdEligibility()).toEqual(NO_ADS)
    eligibility({ adsense: 'yes', annualads_rotator: 1 }, 200)
    expect(await fetchAdEligibility()).toEqual(NO_ADS)
    eligibility({ adsense: true }, 500)
    expect(await fetchAdEligibility()).toEqual(NO_ADS)
  })

  it('an ineligible viewer never requests the provider script, even after consent (AC)', async () => {
    eligibility({ adsense: false, annualads_rotator: false, annualads_sponsor: false })
    localStorage.setItem('myhigh5_cookie_consent', JSON.stringify({ preferences: { advertising: true } }))
    const { container } = render(<><AdSenseLoader /><AdSenseSlot slot="1" /></>)
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/api/v1/ads/eligibility'))
    act(() => window.dispatchEvent(new Event(COOKIE_CONSENT_EVENT)))
    await new Promise((r) => setTimeout(r, 1700))
    expect(scripts().length).toBe(0)
    expect(container.querySelector('ins.adsbygoogle')).toBeNull()
  })

  it('an eligible, consenting viewer gets the script and the slot', async () => {
    eligibility({ adsense: true, annualads_rotator: false, annualads_sponsor: false })
    localStorage.setItem('myhigh5_cookie_consent', JSON.stringify({ preferences: { advertising: true } }))
    const { container } = render(<><AdSenseLoader /><AdSenseSlot slot="1" /></>)
    await waitFor(() => expect(container.querySelector('ins.adsbygoogle')).not.toBeNull())
    await waitFor(() => expect(scripts().length).toBe(1), { timeout: 3000 })
  })

  it('consent alone is not enough, and no consent means no script for eligible viewers', async () => {
    eligibility({ adsense: true, annualads_rotator: false, annualads_sponsor: false })
    render(<AdSenseLoader />)
    await waitFor(() => expect(getMock).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 1700))
    expect(scripts().length).toBe(0)
  })
})
