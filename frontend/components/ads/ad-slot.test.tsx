import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { postMock, nav, elig } = vi.hoisted(() => ({
  postMock: vi.fn(),
  nav: { pathname: '/contests/1/entry/2' as string | null },
  elig: { adsense: true, annualads_rotator: false, annualads_sponsor: false, myhigh5_ads: true },
}))
vi.mock('@/lib/api', () => ({ default: { post: postMock } }))
vi.mock('next/navigation', () => ({ usePathname: () => nav.pathname }))
vi.mock('@/hooks/use-ad-eligibility', () => ({ useAdEligibility: () => elig }))

import { AdSlot } from './ad-slot'

const consent = () => localStorage.setItem('myhigh5_cookie_consent', JSON.stringify({ preferences: { advertising: true } }))
const filled = {
  fill: true,
  decision_id: '11111111-1111-4111-8111-111111111111',
  source: 'MYHIGH5',
  sponsored_label: 'Sponsored',
  creative: { headline: 'Shoes', body: 'New', image_url: null, destination_url: 'https://ex.com/' },
}

type Entry = { intersectionRatio: number }
class IO {
  static last: IO | null = null
  cb: (e: Entry[]) => void
  constructor(cb: (e: Entry[]) => void) {
    this.cb = cb
    IO.last = this
  }
  observe() {}
  disconnect() {}
}

const viewableCalls = () => postMock.mock.calls.filter(([, b]) => b?.event_type === 'VIEWABLE')

describe('AdSlot', () => {
  beforeEach(() => {
    postMock.mockReset()
    localStorage.clear()
    nav.pathname = '/contests/1/entry/2'
    ;(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = IO
  })

  it('is labelled Sponsored and reports SERVED, then VIEWABLE once after 50% for 1 second', async () => {
    consent()
    postMock.mockImplementation((url: string) =>
      Promise.resolve(url.endsWith('/decide') ? { status: 200, data: filled } : { status: 200, data: { status: 'RECORDED' } }))
    render(<AdSlot pageType="CONTEST_ENTRY" slotKind="IN_CONTENT" slotKey="e" contestantId={2} />)
    await waitFor(() => expect(screen.getByText('Sponsored')).toBeInTheDocument())
    expect(screen.getByRole('link').getAttribute('rel')).toContain('sponsored')
    expect(postMock).toHaveBeenCalledWith('/api/v1/ads/decide', expect.objectContaining({ contestant_id: 2 }))
    await waitFor(() => expect(postMock.mock.calls.some(([, b]) => b?.event_type === 'SERVED')).toBe(true))
    vi.useFakeTimers()
    act(() => IO.last!.cb([{ intersectionRatio: 0.3 }]))
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(viewableCalls()).toHaveLength(0)                       // under 50%: never viewable
    act(() => IO.last!.cb([{ intersectionRatio: 0.8 }]))
    act(() => {
      vi.advanceTimersByTime(1100)
    })
    expect(viewableCalls()).toHaveLength(1)
    act(() => IO.last!.cb([{ intersectionRatio: 0.2 }]))
    act(() => IO.last!.cb([{ intersectionRatio: 0.9 }]))
    act(() => {
      vi.advanceTimersByTime(1100)
    })
    expect(viewableCalls()).toHaveLength(1)                       // at most once per decision
    vi.useRealTimers()
  })

  it('renders nothing and asks nothing without consent or on an excluded route', async () => {
    postMock.mockResolvedValue({ status: 200, data: filled })
    const first = render(<AdSlot pageType="FEED" slotKind="IN_FEED" slotKey="f" />)
    await new Promise((r) => setTimeout(r, 20))
    expect(postMock).not.toHaveBeenCalled()
    first.unmount()
    consent()
    nav.pathname = '/dashboard/messages'
    render(<AdSlot pageType="FEED" slotKind="IN_FEED" slotKey="f" />)
    await new Promise((r) => setTimeout(r, 20))
    expect(postMock).not.toHaveBeenCalled()
    expect(screen.queryByTestId('ad-slot')).toBeNull()
  })

  it('collapses when the server has no fill', async () => {
    consent()
    postMock.mockResolvedValue({ status: 200, data: { fill: false, reason: 'NO_FILL' } })
    render(<AdSlot pageType="FEED" slotKind="IN_FEED" slotKey="f" />)
    await waitFor(() => expect(postMock).toHaveBeenCalled())
    expect(screen.queryByTestId('ad-slot')).toBeNull()
  })

  it('a sidebar unit is desktop-only', async () => {
    consent()
    nav.pathname = '/dashboard/feed'
    postMock.mockResolvedValue({ status: 200, data: filled })
    render(<AdSlot pageType="FEED" slotKind="SIDEBAR" slotKey="s" />)
    await waitFor(() => expect(screen.getByTestId('ad-slot')).toBeInTheDocument())
    expect(screen.getByTestId('ad-slot').className).toContain('hidden lg:block')
  })
})
