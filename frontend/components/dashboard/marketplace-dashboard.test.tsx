import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const post = vi.fn()
const get = vi.fn()
vi.mock('@/lib/api', () => ({
  default: { post: (...a: unknown[]) => post(...a), get: (...a: unknown[]) => get(...a) },
}))
vi.mock('@/hooks/use-auth', () => ({ useAuth: () => ({ user: { id: 5 } }) }))

import { ACCEPTANCE_TEXT, MarketplaceDashboard } from './marketplace-dashboard'

const DISC = { warranty: 'No warranty is offered by the seller.', insurance: 'No insurance is offered with this item.',
  consumer_rights: 'Your statutory consumer rights are not affected.' }
const LISTING = { id: 3, kind: 'PHYSICAL', title: 'Basket', description: 'Woven basket', seller_user_id: 9, buyer_price_usd: '30.00',
  quantity_available: 2, available: true, handover_details: 'Courier', warranty_available: false, insurance_available: false,
  disclosures: DISC, has_file: false, published_at: null }
const ORDER = { id: 11, state: 'FULFILLED', item_type: 'listing', buyer_user_id: 5, seller_user_id: 9, buyer_total_amount: 30,
  seller_base_amount: 25, created_at: null, listing: { ...DISC, title: 'Basket', kind: 'PHYSICAL', handover_details: 'Courier' },
  digital: false, digital_delivered_at: null, can_download: false, acceptance_status: 'NOT_ACCEPTED', acceptance_reference: null,
  accepted_at: null, seller_verified_at: null, handover_instruction: 'Awaiting buyer confirmation.',
  fulfilment_status: 'AWAITING_ACCEPTANCE', settlement_status: 'NOT_STARTED' }

function status(enabled: boolean, checkout = false) {
  return { data: { enabled, checkout_available: checkout, acceptance_policy_version: 'P-1' } }
}

beforeEach(() => {
  post.mockReset()
  get.mockReset()
})

describe('MarketplaceDashboard', () => {
  it('says the marketplace is not open while it is closed', async () => {
    get.mockResolvedValue(status(false))
    render(<MarketplaceDashboard />)
    expect(await screen.findByText('The marketplace is not open yet.')).toBeTruthy()
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('shows warranty and insurance disclosures and no Buy button without checkout', async () => {
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/status') ? status(true, false) : { data: [LISTING] }))
    render(<MarketplaceDashboard />)
    fireEvent.click(await screen.findByText('View details'))
    expect(screen.getByText(DISC.warranty)).toBeTruthy()
    expect(screen.getByText(DISC.insurance)).toBeTruthy()
    expect(screen.getByText(/Checkout is not available yet/)).toBeTruthy()
    expect(screen.queryByText(/Buy for/)).toBeNull()
  })

  it('accepts only after the buyer ticks the acceptance text, with the policy version', async () => {
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/status') ? status(true) : { data: [ORDER] }))
    post.mockResolvedValue({ data: ORDER })
    render(<MarketplaceDashboard />)
    await screen.findByText('Browse')
    fireEvent.click(screen.getByRole('tab', { name: 'My purchases' }))
    const button = await screen.findByText('Confirm and accept')
    expect((button as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByText(ACCEPTANCE_TEXT))
    fireEvent.click(button)
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/marketplace/orders/11/accept', { policy_version: 'P-1', acknowledge: true }))
  })

  it('never offers the buyer acceptance on the seller side', async () => {
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/status') ? status(true)
      : { data: [{ ...ORDER, buyer_user_id: 9, seller_user_id: 5 }] }))
    render(<MarketplaceDashboard />)
    await screen.findByText('Browse')
    fireEvent.click(screen.getByRole('tab', { name: 'My sales' }))
    expect(await screen.findByText('Awaiting buyer confirmation.')).toBeTruthy()
    expect(screen.queryByText('Confirm and accept')).toBeNull()
  })
})

describe('MarketplaceDashboard (Prompt 7)', () => {
  it('filters by category and sort and sends them to the server', async () => {
    get.mockImplementation((url: string) => Promise.resolve(
      url.endsWith('/status') ? status(true) : url.endsWith('/categories')
        ? { data: [{ code: 'HOME', regulated: false }, { code: 'FOOD', regulated: true }] }
        : { data: [{ ...LISTING, category: 'HOME', item_condition: 'USED', images: [{ id: 1, url: '/api/v1/marketplace/listings/3/images/1', width: 1, height: 1 }] }] }))
    render(<MarketplaceDashboard />)
    await screen.findByText('Basket')
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'HOME' } })
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'price_asc' } })
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/marketplace/listings',
      { params: { kind: undefined, q: undefined, category: 'HOME', sort: 'price_asc' } }))
    fireEvent.click(screen.getByText('View details'))
    expect(screen.getByText('Used')).toBeTruthy()
  })

  it('sends a checkout reference with the order', async () => {
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/status') ? status(true, true)
      : url.endsWith('/categories') ? { data: [] } : { data: [{ ...LISTING, images: [] }] }))
    post.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/pay') ? { ...ORDER, payment: {} } : ORDER }))
    render(<MarketplaceDashboard />)
    fireEvent.click(await screen.findByText('View details'))
    fireEvent.click(screen.getByText(/Buy for/))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    const orderCalls = post.mock.calls.filter(([u]) => u === '/api/v1/marketplace/orders')
    expect(orderCalls[0][1]).toMatchObject({ item_type: 'listing', item_id: 3 })
    expect(orderCalls[0][1].client_reference).toMatch(/^chk-[A-Za-z0-9_-]+$/)
  })

  it('lets the buyer ask support for a refund, never refunding by itself', async () => {
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/status') ? status(true) : { data: [ORDER] }))
    post.mockResolvedValue({ data: ORDER })
    render(<MarketplaceDashboard />)
    await screen.findByText('Browse')
    fireEvent.click(screen.getByRole('tab', { name: 'My purchases' }))
    fireEvent.click(await screen.findByText('Ask support to cancel or refund'))
    const send = screen.getByText('Send to support')
    expect((send as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('What happened'), { target: { value: 'The seller never shipped it.' } })
    fireEvent.click(send)
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/marketplace/orders/11/requests',
      { kind: 'REFUND', reason: 'The seller never shipped it.' }))
  })

  it('shows a suspended listing with the MyHigh5 message and no publish button', async () => {
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/status') ? status(true)
      : url.endsWith('/my-listings') ? { data: [{ ...LISTING, status: 'SUSPENDED', moderation_note: 'Counterfeit report', seller_price_usd: '25.00', images: [] }] }
        : { data: [] }))
    render(<MarketplaceDashboard />)
    await screen.findByText('Browse')
    fireEvent.click(screen.getByRole('tab', { name: 'My listings' }))
    expect(await screen.findByText('MyHigh5: Counterfeit report')).toBeTruthy()
    expect(screen.queryByText('Publish')).toBeNull()
    expect(screen.queryByText('Archive')).toBeNull()
  })
})
