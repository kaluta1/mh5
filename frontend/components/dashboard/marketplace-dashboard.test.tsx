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
