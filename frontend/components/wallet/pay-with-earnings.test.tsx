import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock }, apiService: {} }))

import { EarningsPayments, PayWithEarnings } from './pay-with-earnings'
import AdminInternalWallet from '@/components/admin/admin-internal-wallet'

const OK = { product_code: 'referral_pool_entry', product_name: 'Referral Pool unit', quantity: 1, amount: '100.00',
  currency: 'USD', available: '125.00', remaining_after: '25.00', allowed: true, reason: null, message: null }

describe('PayWithEarnings', () => {
  beforeEach(() => { getMock.mockReset(); postMock.mockReset() })

  it('is hidden while the feature is switched off', async () => {
    getMock.mockResolvedValue({ status: 200, data: { ...OK, allowed: false, reason: 'WALLET_PAYMENTS_DISABLED' } })
    const { container } = render(<PayWithEarnings productCode="referral_pool_entry" quantity={1} />)
    await waitFor(() => expect(getMock).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('shows price, available, deducted and remaining, then pays with a key and the reviewed amount', async () => {
    getMock.mockResolvedValue({ status: 200, data: OK })
    postMock.mockResolvedValue({ status: 200, data: { reference: 'IWP-ABC' } })
    const onPaid = vi.fn()
    render(<PayWithEarnings productCode="referral_pool_entry" quantity={1} onPaid={onPaid} />)
    expect(await screen.findByTestId('earnings-available')).toHaveTextContent('125.00 USD')
    expect(screen.getByTestId('earnings-remaining')).toHaveTextContent('25.00 USD')
    fireEvent.click(screen.getByText('Confirm: pay 100.00 USD with earnings'))
    await waitFor(() => expect(onPaid).toHaveBeenCalled())
    const body = postMock.mock.calls[0][1]
    expect(body).toMatchObject({ product_code: 'referral_pool_entry', quantity: 1, expected_amount: '100.00' })
    expect(body.idempotency_key.length).toBeGreaterThanOrEqual(8)
    expect(screen.getByTestId('earnings-result')).toHaveTextContent('IWP-ABC')
  })

  it.each([
    ['INSUFFICIENT_BALANCE', 'You do not have enough eligible available commission earnings for this purchase.'],
    ['KYC_REQUIRED', 'Approved identity verification (KYC) is required to pay with your earnings.'],
  ])('explains %s and does not allow paying', async (reason, message) => {
    getMock.mockResolvedValue({ status: 200, data: { ...OK, allowed: false, reason, message, remaining_after: null } })
    render(<PayWithEarnings productCode="referral_pool_entry" quantity={1} />)
    expect(await screen.findByTestId('earnings-blocked')).toHaveTextContent(message)
    expect(screen.getByText('Confirm: pay 100.00 USD with earnings')).toBeDisabled()
  })

  it('shows the server refusal of a payment', async () => {
    getMock.mockResolvedValue({ status: 200, data: OK })
    postMock.mockResolvedValue({ status: 409, data: { detail: { code: 'PRICE_CHANGED', message: 'The price is now 110.00 USD.' } } })
    render(<PayWithEarnings productCode="referral_pool_entry" quantity={1} />)
    fireEvent.click(await screen.findByText('Confirm: pay 100.00 USD with earnings'))
    expect(await screen.findByTestId('earnings-result')).toHaveTextContent('The price is now 110.00 USD.')
  })
})

describe('EarningsPayments', () => {
  beforeEach(() => { getMock.mockReset() })

  it('shows spendable, spent, refunded, the remainder note and history', async () => {
    getMock.mockResolvedValue({ status: 200, data: { enabled: true, spendable: '5.50', wallet_only_remainder: '5.50',
      reserved_for_payouts: '0.00', total_spent: '20.00', total_refunded: '100.00', kyc_approved: true, message: null,
      payments: [{ id: 1, reference: 'IWP-1', product_code: 'advertising_credit', quantity: 20, amount: '20.00',
        status: 'COMPLETED', created_at: '2026-11-03T10:00:00', refunded_at: null, failure_code: null },
      { id: 2, reference: 'IWP-2', product_code: 'referral_pool_entry', quantity: 1, amount: '100.00',
        status: 'REFUNDED', created_at: '2026-11-02T10:00:00', refunded_at: '2026-11-03T09:00:00', failure_code: null }] } })
    render(<EarningsPayments />)
    expect(await screen.findByTestId('earnings-payments')).toHaveTextContent('Spent with earnings20.00 USD')
    expect(screen.getByTestId('earnings-remainder')).toHaveTextContent('not included in cash-outs')
    expect(screen.getByText('Refunded', { selector: 'td' })).toBeInTheDocument()
  })

  it('is hidden while off and nothing was ever paid', async () => {
    getMock.mockResolvedValue({ status: 200, data: { enabled: false, spendable: '0.00', payments: [] } })
    const { container } = render(<EarningsPayments />)
    await waitFor(() => expect(getMock).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})

describe('AdminInternalWallet', () => {
  it('shows the switch, reconciliation and payment details with a guarded refund', async () => {
    getMock.mockReset()
    getMock.mockImplementation((url: string) => {
      if (url.endsWith('/overview')) return Promise.resolve({ status: 200, data: { enabled: false,
        switch: 'INTERNAL_WALLET_PAYMENTS_ENABLED', products: [{ product_code: 'annual_ads', name: 'Annual Ads',
          eligible: false, reason: 'NOT_SOLD_HERE' }],
        reconciliation: { ok: true, problems: [], clearing_balance: '0.00', payments_by_status: { COMPLETED: 1 } } } })
      if (url.endsWith('/payments')) return Promise.resolve({ status: 200, data: { payments: [{ id: 7, reference: 'IWP-7',
        user_id: 3, product_code: 'referral_pool_entry', quantity: 1, amount: '100.00', status: 'COMPLETED' }] } })
      return Promise.resolve({ status: 200, data: { id: 7, reference: 'IWP-7', status: 'COMPLETED',
        lines: [{ commission_id: 11, amount: '100.00', status: 'ACTIVE' }], settlement_journal_entry_id: 90, deposit_id: 5 } })
    })
    render(<AdminInternalWallet />)
    expect(await screen.findByTestId('iw-switch')).toHaveTextContent('OFF')
    expect(screen.getByTestId('iw-reconciliation')).toHaveTextContent('consistent')
    fireEvent.click(screen.getByText('Details'))
    expect(await screen.findByTestId('iw-detail')).toHaveTextContent('#11 100.00 (ACTIVE)')
    expect(screen.getByText('Full refund')).toBeDisabled()
  })
})
