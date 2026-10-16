import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock } }))

import ManualPaymentQueue from './manual-payment-queue'
import { allowedActions, validDecisionReason, validEvidence, type ManualPayment } from '@/lib/manual-payments'

// Synthetic values only.
const PASSWORD = 'synthetic-admin-password'
const item = (over: Partial<ManualPayment> = {}): ManualPayment => ({
  id: 5, deposit_id: 9, member_id: 42, product_code: 'kyc', amount: '5.00', currency: 'USD', status: 'REQUESTED',
  created_new_deposit: true, verify_identity_requested: false, requested_by: 7, requested_at: null,
  request_reason: 'Bank transfer ref 2026-10-13/0042', decided_by: null, decided_at: null, evidence_reference: null,
  decision_note: null, member: { id: 42, username: 'member', full_name: 'Synthetic Member', email: 'm@example.com' },
  ...over,
})
const list = (me: number, canDecide = true, items = [item()]) => ({ status: 200, data: { items, current_admin_id: me, can_decide: canDecide } })

beforeEach(() => { getMock.mockReset(); postMock.mockReset() })

describe('manual payment rules in the page', () => {
  it('never offers confirm or reject to the recorder, the member, or someone without the permission', () => {
    expect(allowedActions(item(), 7, true)).toEqual({ confirm: false, reject: false, cancel: true, waitingForSecondAdmin: true })
    expect(allowedActions(item(), 8, true)).toEqual({ confirm: true, reject: true, cancel: false, waitingForSecondAdmin: false })
    expect(allowedActions(item(), 42, true).confirm).toBe(false)
    expect(allowedActions(item(), 8, false).confirm).toBe(false)
    expect(allowedActions(item({ status: 'CONFIRMED' }), 8, true).confirm).toBe(false)
    expect(validEvidence('x')).toBe(false)
    expect(validEvidence('TX-123456')).toBe(true)
    expect(validDecisionReason('no')).toBe(false)
  })
})

describe('Awaiting a second administrator', () => {
  it('the recorder sees only Withdraw', async () => {
    getMock.mockResolvedValue(list(7))
    render(<ManualPaymentQueue />)
    await screen.findByTestId('manual-payment-5')
    expect(screen.queryByRole('button', { name: 'Confirm receipt' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Withdraw' })).toBeInTheDocument()
    expect(screen.getByText(/a second administrator has to confirm it/)).toBeInTheDocument()
  })

  it('a second administrator confirms with the evidence and the password', async () => {
    getMock.mockResolvedValue(list(8))
    postMock.mockResolvedValue({ status: 200, data: { status: 'granted', request: item({ status: 'CONFIRMED' }) } })
    render(<ManualPaymentQueue />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm receipt' }))
    const submit = screen.getByRole('button', { name: 'Confirm and credit' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Where the money was received/), { target: { value: 'TX-0xabc123' } })
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(submit)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/manual-payments/5/confirm',
      { current_password: PASSWORD, evidence_reference: 'TX-0xabc123' }))
    expect(await screen.findByText('Payment confirmed and credited.')).toBeInTheDocument()
  })

  it('shows a server refusal and credits nothing', async () => {
    getMock.mockResolvedValue(list(8))
    postMock.mockResolvedValue({ status: 403, data: { detail: { code: 'SAME_ADMINISTRATOR',
      message: 'The administrator who recorded a payment cannot confirm it: a second administrator has to.' } },
      config: { url: '/x' } })
    render(<ManualPaymentQueue />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }))
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'No such transfer was received' } })
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(screen.getByRole('button', { name: 'Reject payment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('a second administrator has to')
    expect(screen.queryByText('Payment confirmed and credited.')).toBeNull()
  })

  it('says when nothing is waiting', async () => {
    getMock.mockResolvedValue(list(8, true, []))
    render(<ManualPaymentQueue />)
    expect(await screen.findByTestId('manual-payments-empty')).toBeInTheDocument()
  })
})
