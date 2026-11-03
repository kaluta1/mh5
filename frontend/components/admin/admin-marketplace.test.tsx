import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock }, apiService: {} }))

import AdminMarketplace from './admin-marketplace'

const LISTING = { id: 7, title: 'Basket', status: 'PUBLISHED', seller_user_id: 9, seller_status: 'APPROVED', seller_can_sell: true,
  buyer_price_usd: '30.00', description: 'Woven', history: [{ action: 'PUBLISHED', by: 'SELLER', from: 'DRAFT', to: 'PUBLISHED', at: 't' }], orders: 0 }
const ORDER = { id: 11, state: 'FUNDS_HELD', buyer_total_amount: 30, settlement_status: 'NOT_STARTED', buyer_user_id: 5,
  seller_user_id: 9, custodian: 'X', events: [], open_request: { kind: 'REFUND', reason: 'Not shipped' } }
const DATA: Record<string, unknown> = {
  '/api/v1/admin/marketplace/overview': { marketplace_enabled: false, seller_verification_enforced: false, custodian: 'UNCONFIGURED',
    checkout_available: false, open_requests: 0, sellers_by_status: {}, applications_by_status: {}, listings_by_status: { PUBLISHED: 1 }, orders_by_state: {} },
  '/api/v1/admin/marketplace/listings': [LISTING],
  '/api/v1/admin/marketplace/listings/7': LISTING,
  '/api/v1/admin/business-model/marketplace/orders': [ORDER],
  '/api/v1/admin/marketplace/reconciliation': { fingerprint: 'f1', issue_count: 1, ok: false, counts: {},
    issues: [{ type: 'ORDER_TOTAL_MISMATCH', expected: '30.00', actual: '31.00', suggestion: 'Review' }] },
}

describe('AdminMarketplace', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    getMock.mockImplementation((url: string) => Promise.resolve({ status: 200, data: DATA[url] }))
  })

  it('shows the overview with the custodian and checkout state', async () => {
    render(<AdminMarketplace />)
    expect(await screen.findByText(/payment custodian: UNCONFIGURED/)).toBeInTheDocument()
    expect(screen.getByText(/checkout not available/)).toBeInTheDocument()
  })

  it('suspends a listing with a reason, a seller message and the password', async () => {
    postMock.mockResolvedValue({ status: 200, data: { ...LISTING, status: 'SUSPENDED' } })
    render(<AdminMarketplace />)
    fireEvent.click(screen.getByRole('tab', { name: 'Listings' }))
    fireEvent.click(await screen.findByText('Open'))
    fireEvent.change(await screen.findByLabelText('Internal reason'), { target: { value: 'Counterfeit report' } })
    fireEvent.change(screen.getByLabelText('Message to the seller'), { target: { value: 'Please contact support' } })
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('Suspend listing'))
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/marketplace/listings/7/moderation',
      { action: 'suspend', reason: 'Counterfeit report', seller_message: 'Please contact support', current_password: 'pw' }))
  })

  it('refunds only with the password and shows the server refusal', async () => {
    postMock.mockResolvedValue({ status: 403, data: { detail: { code: 'PERMISSION_REQUIRED', message: 'The process_cashouts permission is required.' } } })
    render(<AdminMarketplace />)
    fireEvent.click(screen.getByRole('tab', { name: 'Orders' }))
    fireEvent.click(await screen.findByText('Open'))
    fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'Seller unreachable' } })
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByText('Support refund'))
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/business-model/marketplace/orders/11/refund',
      { reason: 'NON_HANDOVER', note: 'Seller unreachable', current_password: 'pw' }))
    expect(await screen.findByText('The process_cashouts permission is required.')).toBeInTheDocument()
    expect(screen.getByText('Decline request')).toBeInTheDocument()
  })

  it('shows the read-only reconciliation issues', async () => {
    render(<AdminMarketplace />)
    fireEvent.click(screen.getByRole('tab', { name: 'Reconciliation' }))
    expect(await screen.findByText(/ORDER_TOTAL_MISMATCH/)).toBeInTheDocument()
    expect(screen.getByText(/Read only · fingerprint f1/)).toBeInTheDocument()
  })
})
