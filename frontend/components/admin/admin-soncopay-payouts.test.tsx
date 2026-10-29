import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock }, apiService: {} }))

import AdminSoncoPayPayouts, { destinationText } from './admin-soncopay-payouts'

const VIEW = {
  blockers: [{ code: 'SONCOPAY_PAYOUTS_NOT_AUTHORIZED', message: 'The owner has not recorded it.' }],
  authorization: null,
  confirmation_phrase: 'SONCOPAY ALLOWS MEMBER PAYOUTS',
  destination_limit: 50,
  counts: { PENDING_CONFIRMATION: 1 },
  destinations: [{ id: 1, user_id: 7, username: 'm1', address: '0x55d3…7955', status: 'PENDING_CONFIRMATION',
    usable: false, usable_from: null, confirmed_at: null, destination_id: 'pd_1', last_error: null }],
  provider: null,
}

describe('AdminSoncoPayPayouts', () => {
  beforeEach(() => { getMock.mockReset(); postMock.mockReset() })

  it('lists blockers and destinations, masked, and records the authorization only with every field', async () => {
    getMock.mockResolvedValue({ status: 200, data: VIEW })
    postMock.mockResolvedValue({ status: 200, data: {} })
    render(<AdminSoncoPayPayouts />)
    expect(await screen.findByTestId('sp-blockers')).toHaveTextContent('The owner has not recorded it.')
    expect(screen.getByTestId('sp-destination-table')).toHaveTextContent('Awaiting confirmation in the SoncoPay dashboard')
    const record = screen.getByRole('button', { name: 'Record authorization' })
    expect(record).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Where SoncoPay confirmed it'), { target: { value: 'Support ticket 1234' } })
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'SONCOPAY ALLOWS MEMBER PAYOUTS' } })
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'pw' } })
    fireEvent.click(record)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/finance/soncopay/payouts/authorization',
      { note: 'Support ticket 1234', confirmation: 'SONCOPAY ALLOWS MEMBER PAYOUTS', current_password: 'pw' }))
  })

  it('explains the waiting period', () => {
    expect(destinationText({ status: 'ACTIVE', usable: false, usable_from: '2026-10-30T10:00:00' }))
      .toBe('Security waiting period until 2026-10-30 10:00 UTC')
    expect(destinationText({ status: 'ACTIVE', usable: true, usable_from: null })).toBe('Ready for automatic payouts')
  })
})

describe('AdminSoncoPayPayouts: small commissions added together', () => {
  it('shows the threshold, the accumulating members and the commissions of each combined payout', async () => {
    getMock.mockResolvedValue({ status: 200, data: { ...VIEW, accumulation: {
      threshold: '2.23', fee: '0.23', minimum: '2', read_at: '2026-10-29T12:00:00Z',
      members: [{ user_id: 7, username: 'm1', unpaid: '1.80', commissions: 2, accumulating: '1.80',
        accumulating_commissions: 2, reaches_threshold: false, blocked_by: null }],
      payouts: [{ cashout_id: 11, user_id: 8, status: 'processing', failure_code: null, gross_amount: '2.30',
        amount_sent: '2.07', network_fee_estimate: '0.23', commission_ids: [3, 4, 5],
        provider_payout_id: 'po_000001', tx_hash: null, requested_at: '2026-10-29T12:00:00' }],
    } } })
    render(<AdminSoncoPayPayouts />)
    expect(await screen.findByTestId('sp-threshold')).toHaveTextContent('Smallest payout 2.23 USDT')
    expect(screen.getByTestId('sp-accumulation-table')).toHaveTextContent('m1 (#7)')
    expect(screen.getByTestId('sp-combined-table')).toHaveTextContent('#3, #4, #5')
    expect(screen.getByTestId('sp-combined-table')).toHaveTextContent('2.30 (sent 2.07)')
  })
})
