import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

const post = vi.fn()
const get = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { post: (...a: unknown[]) => post(...a), get: (...a: unknown[]) => get(...a) },
}))

import { INVITATION_HELP, MyShortLinks, ShortenLinkForm, ShortLinksManager } from './short-links-manager'
import { userNavSections } from './dashboard-nav-data'

const LINK = {
  id: 7,
  short_code: 'Ab7kP2x',
  short_url: 'https://myhigh5.com/s/Ab7kP2x',
  destination_url: 'https://myhigh5.com/feed/12',
  include_invitation: false,
  is_active: true,
  created_at: '2026-10-27T12:00:00',
  disabled_at: null,
}
const writeText = vi.fn()

// jsdom has no ResizeObserver; the Radix switch measures itself with one.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

beforeEach(() => {
  post.mockReset()
  get.mockReset()
  writeText.mockReset().mockResolvedValue(undefined)
  Object.assign(navigator, { clipboard: { writeText } })
})

function fillUrl(value: string) {
  fireEvent.change(screen.getByLabelText('Paste a MyHigh5 page link'), { target: { value } })
}

describe('Shorten a Link form', () => {
  it('shows the label, the invitation toggle OFF by default and its explanation', () => {
    render(<ShortenLinkForm />)
    expect(screen.getByLabelText('Paste a MyHigh5 page link')).toBeTruthy()
    const toggle = screen.getByRole('switch', { name: 'Include my personal invitation' })
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    expect(screen.getByText(INVITATION_HELP)).toBeTruthy()
    expect(INVITATION_HELP).toBe(
      "When enabled, eligible new members who register through this link will be attributed to you under MyHigh5's referral rules.")
    expect(screen.getByRole('button', { name: 'Create Short Link' })).toBeTruthy()
  })

  it('validates before calling the server', async () => {
    render(<ShortenLinkForm />)
    fireEvent.click(screen.getByRole('button', { name: 'Create Short Link' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Paste the link')
    fillUrl('https://example.com/page')
    fireEvent.click(screen.getByRole('button', { name: 'Create Short Link' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Only MyHigh5 page links')
    expect(post).not.toHaveBeenCalled()
  })

  it('creates a neutral link, then shows it with Copy and Open', async () => {
    let resolve: (v: unknown) => void = () => {}
    post.mockReturnValue(new Promise((r) => { resolve = r }))
    const onCreated = vi.fn()
    render(<ShortenLinkForm onCreated={onCreated} />)
    fillUrl('https://myhigh5.com/feed/12')
    fireEvent.click(screen.getByRole('button', { name: 'Create Short Link' }))
    expect(await screen.findByText('Creating…')).toBeTruthy()                     // loading state
    resolve({ data: LINK })
    expect((await screen.findByTestId('created-short-url')).textContent).toBe(LINK.short_url)
    expect(post).toHaveBeenCalledWith('/api/v1/share-links', { url: 'https://myhigh5.com/feed/12', include_invitation: false })
    expect(screen.getByRole('status').textContent).toContain('ready to share')
    fireEvent.click(screen.getByRole('button', { name: 'Copy Link' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LINK.short_url))
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeTruthy()
    const open = screen.getByRole('link', { name: /Open Link/ })
    expect(open.getAttribute('href')).toBe(LINK.short_url)
    expect(open.getAttribute('target')).toBe('_blank')
    expect(open.getAttribute('rel')).toContain('noopener')
    expect(onCreated).toHaveBeenCalled()
  })

  it('sends only the invitation choice (never an id or code) when the toggle is on', async () => {
    post.mockResolvedValue({ data: { ...LINK, include_invitation: true } })
    render(<ShortenLinkForm />)
    fillUrl('https://myhigh5.com/register')
    fireEvent.click(screen.getByRole('switch', { name: 'Include my personal invitation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create Short Link' }))
    expect((await screen.findByRole('status')).textContent).toContain('includes your personal invitation')
    expect(post.mock.calls[0][1]).toEqual({ url: 'https://myhigh5.com/register', include_invitation: true })
  })

  it("shows the server's refusal", async () => {
    post.mockRejectedValue({ response: { status: 400, data: { detail: 'This MyHigh5 page cannot be shortened.' } } })
    render(<ShortenLinkForm />)
    fillUrl('https://myhigh5.com/dashboard/wallet')
    fireEvent.click(screen.getByRole('button', { name: 'Create Short Link' }))
    expect((await screen.findByRole('alert')).textContent).toBe('This MyHigh5 page cannot be shortened.')
  })
})

describe('My Short Links', () => {
  it('shows loading, then the empty state', async () => {
    get.mockResolvedValue({ data: { items: [], total: 0 } })
    render(<MyShortLinks />)
    expect(screen.getByText(/Loading your short links/)).toBeTruthy()
    expect(await screen.findByText(/have not created any short links yet/)).toBeTruthy()
  })

  it('lists links with destination, invitation, date and status', async () => {
    get.mockResolvedValue({ data: { items: [LINK, { ...LINK, id: 8, short_code: 'Km9R4tQ', short_url: 'https://myhigh5.com/s/Km9R4tQ',
      include_invitation: true, is_active: false, disabled_at: '2026-10-27T13:00:00' }], total: 2 } })
    render(<MyShortLinks />)
    const first = await screen.findByTestId('short-link-7')
    expect(first.textContent).toContain(LINK.short_url)
    expect(first.textContent).toContain(LINK.destination_url)
    expect(first.textContent).toContain('Invitation off')
    expect(first.textContent).toContain('Active')
    expect(first.textContent).toMatch(/Created .*2026/)
    const second = screen.getByTestId('short-link-8')
    expect(second.textContent).toContain('Invitation on')
    expect(second.textContent).toContain('Disabled')
    expect(within(second).queryByRole('button', { name: /Disable/ })).toBeNull()      // nothing to manage
    expect(within(second).queryByRole('link', { name: /Open/ })).toBeNull()
  })

  it('disables only after confirmation', async () => {
    get.mockResolvedValue({ data: { items: [LINK], total: 1 } })
    post.mockResolvedValue({ data: { ...LINK, is_active: false } })
    render(<MyShortLinks />)
    const row = await screen.findByTestId('short-link-7')
    fireEvent.click(within(row).getByRole('button', { name: /Disable/ }))
    expect(screen.getByText('Disable this short link?')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Keep it' }))
    expect(post).not.toHaveBeenCalled()
    fireEvent.click(within(row).getByRole('button', { name: /Disable/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Disable link' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/share-links/7/disable'))
    await waitFor(() => expect(screen.getByTestId('short-link-7').textContent).toContain('Disabled'))
  })

  it('copies a row link and reports a load failure with a retry', async () => {
    get.mockResolvedValueOnce({ data: { items: [LINK], total: 1 } })
    render(<MyShortLinks />)
    const row = await screen.findByTestId('short-link-7')
    fireEvent.click(within(row).getByRole('button', { name: 'Copy' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LINK.short_url))

    get.mockRejectedValueOnce({ response: { status: 500, data: { detail: 'Traceback (most recent call last) ...'.repeat(20) } } })
    fireEvent.click(screen.getByRole('button', { name: 'Refresh my short links' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('could not be loaded')                // internals never shown
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeTruthy()
  })
})

describe('layout, themes and navigation', () => {
  it('is responsive and styled for light and dark themes', async () => {
    get.mockResolvedValue({ data: { items: [LINK], total: 1 } })
    const { container } = render(<ShortLinksManager />)
    await screen.findByTestId('short-link-7')
    const html = container.innerHTML
    expect(html).toContain('dark:text-white')
    expect(html).toContain('dark:text-gray-400')
    expect(html).toContain('md:flex-row')
    expect(html).toContain('break-all')                                      // long URLs never overflow on mobile
    expect(screen.getByRole('heading', { name: 'Shorten a Link' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'My Short Links' })).toBeTruthy()
  })

  it('appears in the member dashboard menu next to Affiliates', () => {
    const business = userNavSections.find((s) => s.titleLabel === 'Business')!
    const hrefs = business.items.map((i) => i.href)
    expect(hrefs).toContain('/dashboard/short-links')
    expect(hrefs.indexOf('/dashboard/short-links')).toBe(hrefs.indexOf('/dashboard/affiliates') + 1)
    expect(business.items.find((i) => i.href === '/dashboard/short-links')!.label).toBe('Short Links')
  })
})

describe('KYC eligibility warning', () => {
  const toggleOn = () => fireEvent.click(screen.getByRole('switch', { name: 'Include my personal invitation' }))

  it('explains a KYC restriction when the invitation is turned on, and still allows creating', async () => {
    get.mockImplementation((url: string) => url.endsWith('/invitation-status')
      ? Promise.resolve({ data: { eligible: false, reason: 'KYC_IN_PROGRESS',
          message: 'Your identity verification (KYC) is still being reviewed.' } })
      : Promise.resolve({ data: { items: [], total: 0 } }))
    post.mockResolvedValue({ data: { ...LINK, include_invitation: true } })
    render(<ShortenLinkForm />)
    expect(screen.queryByTestId('invitation-warning')).toBeNull()                 // not asked while OFF
    expect(get).not.toHaveBeenCalled()
    toggleOn()
    const warning = await screen.findByTestId('invitation-warning')
    expect(warning.textContent).toContain('still being reviewed')
    expect(within(warning).getByRole('link', { name: 'Go to identity verification' }).getAttribute('href')).toBe('/dashboard/kyc')
    fillUrl('https://myhigh5.com/register')
    fireEvent.click(screen.getByRole('button', { name: 'Create Short Link' }))
    expect(await screen.findByTestId('created-short-url')).toBeTruthy()
    toggleOn()                                                                    // OFF again: warning gone
    expect(screen.queryByTestId('invitation-warning')).toBeNull()
  })

  it('shows nothing for an eligible member or when the status cannot be read', async () => {
    get.mockResolvedValueOnce({ data: { eligible: true, reason: null, message: null } })
    const { unmount } = render(<ShortenLinkForm />)
    toggleOn()
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/share-links/invitation-status'))
    expect(screen.queryByTestId('invitation-warning')).toBeNull()
    unmount()
    get.mockRejectedValueOnce(new Error('network'))
    render(<ShortenLinkForm />)
    toggleOn()
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    expect(screen.queryByTestId('invitation-warning')).toBeNull()
  })

  it('a restriction is explained without a verification link', async () => {
    get.mockResolvedValue({ data: { eligible: false, reason: 'RESTRICTED', message: 'Invitations from your account are currently restricted.' } })
    render(<ShortenLinkForm />)
    toggleOn()
    const warning = await screen.findByTestId('invitation-warning')
    expect(within(warning).queryByRole('link')).toBeNull()
  })
})

describe('result panel after disabling', () => {
  it('stops offering Copy/Open for a link disabled from the list', async () => {
    get.mockImplementation((url: string) => url.endsWith('/invitation-status')
      ? Promise.resolve({ data: { eligible: true, reason: null, message: null } })
      : Promise.resolve({ data: { items: [LINK], total: 1 } }))
    post.mockImplementation((url: string) => Promise.resolve(
      { data: url.endsWith('/disable') ? { ...LINK, is_active: false } : LINK }))
    render(<ShortLinksManager />)
    fillUrl('https://myhigh5.com/feed/12')
    fireEvent.click(screen.getByRole('button', { name: 'Create Short Link' }))
    expect(await screen.findByTestId('created-short-url')).toBeTruthy()
    const row = await screen.findByTestId('short-link-7')
    fireEvent.click(within(row).getByRole('button', { name: /Disable/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Disable link' }))
    expect((await screen.findByTestId('created-link-disabled')).textContent).toContain('no longer opens')
    expect(screen.queryByTestId('created-short-url')).toBeNull()
    expect(screen.queryByRole('link', { name: /Open Link/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Copy Link' })).toBeNull()
  })
})
