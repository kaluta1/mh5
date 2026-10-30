import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { putMock } = vi.hoisted(() => ({ putMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: putMock }, apiService: {} }))

import SimpleCryptoSettings, { type CryptoSummary } from './admin-crypto-simple'

const PASSWORD = 'synthetic-admin-password'
const CONFIRMATIONS = { provider_fee_mode: 'PROVIDER FEE BEHAVIOUR VERIFIED', fee_terms_approved: 'APPROVE NETWORK FEE LIMITS',
  crypto_auto_payout_enabled: 'ENABLE AUTOMATIC PAYOUTS' }

// Production on 2026-10-30, before the owner's correction.
const summary = (over: Partial<CryptoSummary> = {}): CryptoSummary => ({
  version: 11, minimum_usd: '10.00', member_pays_fee: true, fee_mode: 'DEDUCTED_BY_PROVIDER',
  required_fee_mode: 'ADDED_BY_PROVIDER', fee_mode_confirmed: false, fee_cap_usd: '0.10', fee_cap_percent: '5.000',
  max_network_fee_percent: '10.00', margin_percent: '25', min_net_payout_usd: '0.50', approved: false,
  approval_blocked_by: { code: 'PROVIDER_FEE_MODE_UNVERIFIED', message: 'The provider fee behaviour is not confirmed.' },
  automatic_payouts: { admin_switch: false, server_switch: false },
  preview: { amount: '10.00', network_fee: '0.23', fee_checked: '0.2875', member_receives: '9.77', provider_debit: '10.00',
    provider_minimum: '2', read_at: '2026-10-30T09:00:00Z' },
  ...over,
})

// The page's change(): runs the request, reports a refusal where it was made.
const change = vi.fn(async (request: () => Promise<{ status: number; data?: any }>, _ok: string, failure: string,
  onRefused?: (message: string, field: string | null) => void) => {
  const res = await request()
  if (res.status === 200) return true
  onRefused?.(res.data?.detail?.message ?? failure, null)
  return false
})

const show = (s = summary(), over: { canActivate?: boolean; canManage?: boolean } = {}) =>
  render(<SimpleCryptoSettings summary={s} confirmations={CONFIRMATIONS} canManage={over.canManage ?? true}
    canActivate={over.canActivate ?? true} busy={false} change={change} />)

describe('Simple Crypto Cashout settings', () => {
  beforeEach(() => { putMock.mockReset(); change.mockClear(); putMock.mockResolvedValue({ status: 200, data: {} }) })

  it('shows only the essentials in plain words, with automatic payouts OFF and no contradictory fee text', () => {
    show()
    expect(screen.getByTestId('simple-minimum')).toHaveTextContent('$10.00')
    expect(screen.getByTestId('simple-fee-payer')).toHaveTextContent('Member pays')
    expect(screen.getByTestId('simple-auto')).toHaveTextContent('OFF')
    expect(screen.getByLabelText('Maximum network fee per payout (USD)')).toHaveValue('0.10')
    expect(screen.getByTestId('simple-fee-rule')).toHaveTextContent('adds its network fee on top')
    expect(screen.getByTestId('crypto-simple')).not.toHaveTextContent('takes its fee out')
    expect(screen.getByTestId('crypto-simple')).not.toHaveTextContent('DEDUCTED_BY_PROVIDER')
    expect(screen.queryByRole('switch')).toBeNull()                          // no automatic-payout switch here
  })

  it('previews a $10 payout and says when the maximum fee is too low for it', () => {
    show()
    const preview = screen.getByTestId('simple-preview')
    expect(preview).toHaveTextContent('9.77 USDT')
    expect(preview).toHaveTextContent('0.23 USDT')
    expect(preview).toHaveTextContent('10.00 USDT')
    expect(screen.getByTestId('simple-preview-limit')).toHaveTextContent('Above your maximum fee')
    fireEvent.change(screen.getByLabelText('Maximum network fee per payout (USD)'), { target: { value: '0.50' } })
    expect(screen.getByTestId('simple-preview-limit')).toHaveTextContent('Within your maximum fee')
    expect(screen.getByTestId('simple-preview-limit')).toHaveTextContent('limit is 0.50')
  })

  it('step 1 saves the fee rule and the maximum fee with the phrase, password and version', async () => {
    show()
    fireEvent.change(screen.getByLabelText('Maximum network fee per payout (USD)'), { target: { value: '0.5' } })
    const save = screen.getByRole('button', { name: 'Save settings' })
    fireEvent.change(screen.getByLabelText('Your password'), { target: { value: PASSWORD } })
    expect(save).toBeDisabled()                                               // phrase still missing
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'PROVIDER FEE BEHAVIOUR VERIFIED' } })
    expect(save).not.toBeDisabled()
    expect(screen.getByTestId('simple-approve-wait')).toHaveTextContent('Save step 1 first')
    fireEvent.click(save)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { provider_fee_mode: 'ADDED_BY_PROVIDER', member_fee_cap_usd: '0.50' }, current_password: PASSWORD,
      confirmation: 'PROVIDER FEE BEHAVIOUR VERIFIED', expected_version: 11 }))
    expect(putMock.mock.calls[0][1].changes).not.toHaveProperty('fee_terms_approved')   // approval is separate
    expect(putMock.mock.calls[0][1].changes).not.toHaveProperty('crypto_auto_payout_enabled')
  })

  it('rejects an invalid maximum fee and shows the server refusal', async () => {
    putMock.mockResolvedValue({ status: 409, data: { detail: { message: 'The configuration was changed by someone else.' } } })
    show()
    fireEvent.change(screen.getByLabelText('Maximum network fee per payout (USD)'), { target: { value: 'abc' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Enter an amount above 0')
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Maximum network fee per payout (USD)'), { target: { value: '0.50' } })
    fireEvent.change(screen.getByLabelText('Your password'), { target: { value: PASSWORD } })
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'PROVIDER FEE BEHAVIOUR VERIFIED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(await screen.findByTestId('simple-save-error')).toHaveTextContent('Not saved: The configuration was changed by someone else.')
  })

  it('step 2 approves in a change of its own once step 1 is saved', async () => {
    show(summary({ fee_mode: 'ADDED_BY_PROVIDER', fee_mode_confirmed: true, fee_cap_usd: '0.50', approval_blocked_by: null, version: 12 }))
    expect(screen.getByTestId('simple-step1-done')).toBeInTheDocument()
    const approve = screen.getByRole('button', { name: 'Approve fee settings' })
    fireEvent.change(screen.getByLabelText('Your password'), { target: { value: PASSWORD } })
    expect(approve).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'APPROVE NETWORK FEE LIMITS' } })
    fireEvent.click(approve)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { fee_terms_approved: true }, current_password: PASSWORD, confirmation: 'APPROVE NETWORK FEE LIMITS',
      expected_version: 12 }))
  })

  it('says why approval is not possible instead of offering a button that fails', () => {
    show(summary({ fee_mode_confirmed: true, fee_cap_usd: '0.50',
      approval_blocked_by: { code: 'FEE_SAFETY_MARGIN_NOT_SET', message: 'The safety margin is not set.' } }))
    expect(screen.getByTestId('simple-approve-blocked')).toHaveTextContent('The safety margin is not set.')
    expect(screen.queryByRole('button', { name: 'Approve fee settings' })).toBeNull()
  })

  it('without the activation permission explains it; without manage permission shows read-only', () => {
    const { unmount } = show(summary({ fee_mode_confirmed: true, fee_cap_usd: '0.50', approval_blocked_by: null }), { canActivate: false })
    expect(screen.getByTestId('simple-approve-permission')).toHaveTextContent('activate_financial_operations')
    unmount()
    show(summary(), { canManage: false })
    expect(screen.queryByRole('button', { name: 'Save settings' })).toBeNull()
    expect(screen.getByLabelText('Maximum network fee per payout (USD)')).toBeDisabled()
  })

  it('shows Approved once the settings are approved', () => {
    show(summary({ fee_mode_confirmed: true, fee_cap_usd: '0.50', approved: true, approval_blocked_by: null }))
    expect(screen.getByTestId('simple-approved')).toBeInTheDocument()
    expect(screen.getByTestId('simple-approval')).toHaveTextContent('Approved')
  })
})
