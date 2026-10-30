import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { putMock } = vi.hoisted(() => ({ putMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: putMock }, apiService: {} }))

import SimpleCryptoSettings, { type CryptoSummary } from './admin-crypto-simple'

const PASSWORD = 'synthetic-admin-password'

// Production on 2026-10-30, before the owner's correction.
const summary = (over: Partial<CryptoSummary> = {}): CryptoSummary => ({
  version: 11, minimum_usd: '10.00', member_pays_fee: true, fee_mode: 'DEDUCTED_BY_PROVIDER',
  required_fee_mode: 'ADDED_BY_PROVIDER', fee_mode_confirmed: false, fee_cap_usd: '0.10', fee_cap_percent: '5.000',
  max_network_fee_percent: '10.00', margin_percent: '25', min_net_payout_usd: '0.50', approved: true,
  approval_blocked_by: null, automatic_payouts: { admin_switch: true, server_switch: false },
  preview: { amount: '10.00', network_fee: '0.23', fee_checked: '0.2875', member_receives: '9.77', provider_debit: '10.00',
    provider_minimum: '2', read_at: '2026-10-30T09:00:00Z' },
  ...over,
})
const SAVED = { fee_mode: 'ADDED_BY_PROVIDER', fee_mode_confirmed: true, fee_cap_usd: '0.50', approved: false, version: 12 }

// The page's change(): runs the request, reports a refusal where it was made.
const change = vi.fn(async (request: () => Promise<{ status: number; data?: any }>, _ok: string, failure: string,
  onRefused?: (message: string, field: string | null) => void) => {
  const res = await request()
  if (res.status === 200) return true
  onRefused?.(res.data?.detail?.message ?? failure, null)
  return false
})

const show = (s = summary(), over: { canActivate?: boolean; canManage?: boolean } = {}) =>
  render(<SimpleCryptoSettings summary={s} canManage={over.canManage ?? true} canActivate={over.canActivate ?? true}
    busy={false} change={change} />)

describe('Simple Crypto Cashout settings', () => {
  beforeEach(() => { putMock.mockReset(); change.mockClear(); putMock.mockResolvedValue({ status: 200, data: {} }) })

  it('shows only the essentials, automatic payouts OFF, and no typed phrase anywhere', () => {
    show()
    expect(screen.getByTestId('simple-minimum')).toHaveTextContent('$10.00')
    expect(screen.getByTestId('simple-fee-payer')).toHaveTextContent('Member pays')
    expect(screen.getByTestId('simple-auto')).toHaveTextContent('OFF')                 // the release guard holds them
    expect(screen.getByLabelText('Maximum network fee (USD)')).toHaveValue('0.10')
    expect(screen.queryByLabelText(/to confirm/i)).toBeNull()
    expect(screen.getByTestId('crypto-simple')).not.toHaveTextContent(/VERIFIED|APPROVE NETWORK|DEDUCTED|ADDED_BY/)
    expect(screen.queryByRole('switch')).toBeNull()
    expect(screen.getByTestId('simple-preview')).toHaveTextContent('pays the member 9.77 USDT (network fee 0.23)')
  })

  it('says when the maximum fee is too low for a $10 cashout', () => {
    show()
    expect(screen.getByTestId('simple-too-low')).toHaveTextContent('needs at least 0.2875')
    fireEvent.change(screen.getByLabelText('Maximum network fee (USD)'), { target: { value: '0.50' } })
    expect(screen.queryByTestId('simple-too-low')).toBeNull()
  })

  it('Save Settings sends the changes with the password and version only', async () => {
    show()
    fireEvent.change(screen.getByLabelText('Maximum network fee (USD)'), { target: { value: '0.5' } })
    const save = screen.getByRole('button', { name: 'Save Settings' })
    expect(save).toBeDisabled()                                                       // password first
    fireEvent.change(screen.getByLabelText('Your password'), { target: { value: PASSWORD } })
    fireEvent.click(save)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { provider_fee_mode: 'ADDED_BY_PROVIDER', member_fee_cap_usd: '0.50' }, current_password: PASSWORD,
      expected_version: 11 }))
    const sent = putMock.mock.calls[0][1].changes
    expect(sent).not.toHaveProperty('fee_terms_approved')                            // approval is separate
    expect(sent).not.toHaveProperty('crypto_auto_payout_enabled')
    expect(screen.queryByRole('button', { name: 'Approve Settings' })).toBeNull()      // not before saving
  })

  it('shows an invalid amount and a server refusal in plain words', async () => {
    putMock.mockResolvedValue({ status: 403, data: { detail: { message: 'Your password is not correct.' } } })
    show()
    fireEvent.change(screen.getByLabelText('Maximum network fee (USD)'), { target: { value: 'abc' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Enter an amount above 0')
    fireEvent.change(screen.getByLabelText('Maximum network fee (USD)'), { target: { value: '0.50' } })
    fireEvent.change(screen.getByLabelText('Your password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Settings' }))
    expect(await screen.findByTestId('simple-save-error')).toHaveTextContent('Your password is not correct.')
  })

  it('Approve Settings approves in a change of its own with the password only', async () => {
    show(summary(SAVED))
    expect(screen.getByTestId('simple-saved')).toHaveTextContent('No changes to save')
    const approve = screen.getByRole('button', { name: 'Approve Settings' })
    expect(approve).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Your password', { selector: '#simple-approve-password' }), { target: { value: PASSWORD } })
    fireEvent.click(approve)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { fee_terms_approved: true }, current_password: PASSWORD, expected_version: 12 }))
  })

  it('explains why approval is not possible, and shows Approved once it is', () => {
    const { unmount } = show(summary({ ...SAVED, approval_blocked_by: { code: 'X', message: 'The safety margin is not set.' } }))
    expect(screen.getByTestId('simple-approve-blocked')).toHaveTextContent('The safety margin is not set.')
    unmount()
    const second = show(summary(SAVED), { canActivate: false })
    expect(screen.getByTestId('simple-approve-permission')).toHaveTextContent('not allowed to approve')
    second.unmount()
    show(summary({ ...SAVED, approved: true }))
    expect(screen.getByTestId('simple-approved')).toHaveTextContent('Settings approved.')
  })

  it('is read-only without the manage permission', () => {
    show(summary(), { canManage: false })
    expect(screen.queryByRole('button', { name: 'Save Settings' })).toBeNull()
    expect(screen.getByLabelText('Maximum network fee (USD)')).toBeDisabled()
  })
})
