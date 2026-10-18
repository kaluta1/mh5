import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock } }))

import { CommissionPayouts, PayoutPause, WalletApprovals, type WalletApprovalRow } from './admin-finance-payouts'

// Synthetic values only.
const PASSWORD = 'synthetic-admin-password'
const ADDRESS = '0x' + 'a'.repeat(40)
const pending = (over: Partial<WalletApprovalRow> = {}): WalletApprovalRow => ({
  id: 3, user_id: 42, username: 'member', status: 'PENDING', currency: 'usdtbsc', address: ADDRESS,
  submitted_at: '2026-10-18T09:00:00', verification_method: 'EMAIL', decided_by: null, decided_at: null,
  decision_note: null, ...over,
})

beforeEach(() => { getMock.mockReset(); postMock.mockReset() })

describe('Wallet approvals', () => {
  it('shows the full address and approves with the password', async () => {
    getMock.mockResolvedValue({ status: 200, data: { total: 1, items: [pending()] } })
    postMock.mockResolvedValue({ status: 200, data: { ...pending(), status: 'APPROVED' } })
    render(<WalletApprovals canProcess />)
    expect(await screen.findByText(ADDRESS)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review' }))
    const approve = screen.getByRole('button', { name: 'Approve wallet' })
    expect(approve).toBeDisabled()                                          // no password yet
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(approve)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/cashouts/wallet-approvals/3',
      { decision: 'APPROVE', note: null, current_password: PASSWORD }))
    expect(await screen.findByRole('status')).toHaveTextContent('each as its own payout')
  })

  it('needs a reason to reject, and offers nothing to an administrator without the permission', async () => {
    getMock.mockResolvedValue({ status: 200, data: { total: 1, items: [pending()] } })
    const { unmount } = render(<WalletApprovals canProcess />)
    fireEvent.click(await screen.findByRole('button', { name: 'Review' }))
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    const reject = screen.getByRole('button', { name: 'Reject wallet' })
    expect(reject).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Note/), { target: { value: 'Exchange deposit address' } })
    expect(reject).toBeEnabled()
    unmount()
    render(<WalletApprovals canProcess={false} />)
    await screen.findByText(ADDRESS)
    expect(screen.queryByRole('button', { name: 'Review' })).toBeNull()
  })
})

describe('Commission-to-payout reconciliation', () => {
  it('lists the rows that do not agree in words', async () => {
    const row = { commission_id: 9, user_id: 42, amount: '1.00', status: 'PAID', reserved: false,
      attempts: [{ cashout_id: 5, status: 'completed', failure_code: null, tx_hash: null }],
      problems: ['COMPLETED_WITHOUT_HASH'] }
    getMock.mockResolvedValue({ status: 200, data: { items: [row], problems: [row], checked: 1 } })
    render(<CommissionPayouts />)
    expect(await screen.findByText('Completed without a transaction hash')).toBeInTheDocument()
    expect(screen.getByText('1 commissions checked, 1 with a problem.')).toBeInTheDocument()
  })
})

describe('Emergency pause', () => {
  it('needs a reason and the password, and is hidden when payouts are not running', async () => {
    postMock.mockResolvedValue({ status: 200, data: {} })
    const { unmount } = render(<PayoutPause canProcess active />)
    const button = screen.getByRole('button', { name: 'Pause automatic payouts' })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText(/Reason/), { target: { value: 'Suspicious wallet changes' } })
    fireEvent.change(screen.getByPlaceholderText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(button)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/finance/payouts/pause',
      { reason: 'Suspicious wallet changes', current_password: PASSWORD }))
    expect(await screen.findByRole('status')).toHaveTextContent('paused')
    unmount()
    render(<PayoutPause canProcess active={false} />)
    expect(screen.queryByTestId('payout-pause')).toBeNull()
  })
})
