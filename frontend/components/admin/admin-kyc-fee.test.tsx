import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, putMock } = vi.hoisted(() => ({ getMock: vi.fn(), putMock: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock, put: putMock }, apiService: {} }))

import AdminKycFee from './admin-kyc-fee'

// Synthetic values only.
const PASSWORD = 'synthetic-admin-password'
const view = (over: Record<string, unknown> = {}) => ({
  amount: '10.00', currency: 'USD', is_free: false, retry_policy: 'Each new attempt costs the fee.',
  max_amount: '1000.00', can_change: true, last_change: null, ...over,
})

const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

beforeEach(() => {
  getMock.mockReset()
  putMock.mockReset()
  getMock.mockResolvedValue({ status: 200, data: view() })
})

describe('Admin > KYC: Member KYC Verification Fee', () => {
  it('shows only the member fee: no provider cost and no margin', async () => {
    render(<AdminKycFee />)
    expect(await screen.findByTestId('kyc-fee-current')).toHaveTextContent('10.00 USD')
    expect(screen.getByLabelText('Fee (USD)')).toHaveValue('10.00')
    expect(screen.queryByText(/provider cost/i)).toBeNull()
    expect(screen.queryByText(/margin/i)).toBeNull()
    expect(document.querySelectorAll('input')).toHaveLength(2)            // the fee and the password
  })

  it('saves a new fee with the password and the figure that was shown', async () => {
    putMock.mockResolvedValue({ status: 200, data: view({ amount: '7.50' }) })
    render(<AdminKycFee />)
    await screen.findByTestId('kyc-fee-current')
    const save = screen.getByRole('button', { name: 'Save fee' })
    expect(save).toBeDisabled()                                           // nothing changed yet
    type('Fee (USD)', '7.5')
    expect(save).toBeDisabled()                                           // no password yet
    type('Your current password', PASSWORD)
    fireEvent.click(save)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/kyc/admin/fee', {
      amount: '7.50', current_password: PASSWORD, expected_amount: '10.00',
    }))
    expect(await screen.findByText('Saved. The fee is now 7.50 USD.')).toBeInTheDocument()
    expect(screen.getByLabelText('Your current password')).toHaveValue('')
  })

  it('a fee of 0 is saved as free KYC', async () => {
    putMock.mockResolvedValue({ status: 200, data: view({ amount: '0.00', is_free: true }) })
    render(<AdminKycFee />)
    await screen.findByTestId('kyc-fee-current')
    type('Fee (USD)', '0')
    expect(screen.getByText('Members will not be asked to pay.')).toBeInTheDocument()
    type('Your current password', PASSWORD)
    fireEvent.click(screen.getByRole('button', { name: 'Save fee' }))
    expect(await screen.findByText('Saved. KYC is now free for members.')).toBeInTheDocument()
    expect(putMock.mock.calls[0][1].amount).toBe('0.00')
    expect(screen.getByTestId('kyc-fee-current')).toHaveTextContent('Free')
  })

  it('does not send an amount that is not a fee', async () => {
    render(<AdminKycFee />)
    await screen.findByTestId('kyc-fee-current')
    type('Your current password', PASSWORD)
    for (const bad of ['-1', '1.999', 'abc', '1000.01', '']) {
      type('Fee (USD)', bad)
      expect(screen.getByRole('button', { name: 'Save fee' })).toBeDisabled()
    }
    expect(putMock).not.toHaveBeenCalled()
  })

  it('shows the server refusal and keeps the fee', async () => {
    putMock.mockResolvedValue({ status: 403, data: { detail: { code: 'REAUTH_REQUIRED', message: 'Enter your current password to confirm this change.' } } })
    render(<AdminKycFee />)
    await screen.findByTestId('kyc-fee-current')
    type('Fee (USD)', '5')
    type('Your current password', 'wrong')
    fireEvent.click(screen.getByRole('button', { name: 'Save fee' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter your current password to confirm this change.')
    expect(screen.getByTestId('kyc-fee-current')).toHaveTextContent('10.00 USD')
  })

  it('an administrator without the permission sees the fee and no form', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({ can_change: false }) })
    render(<AdminKycFee />)
    expect(await screen.findByTestId('kyc-fee-current')).toHaveTextContent('10.00 USD')
    expect(screen.queryByLabelText('Fee (USD)')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Save fee' })).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('manage_kyc_settings')
  })
})
