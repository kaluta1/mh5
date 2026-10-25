import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

/**
 * "Mark as paid" records money as received. The API client does not throw on
 * a 4xx answer; before the answer was checked, a refused request showed
 * "User marked as paid successfully". The real response handling
 * (lib/http-error) is used here; only the network and the chrome are replaced.
 */
const { getMock, postMock, addToast } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn(), addToast: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock } }))
vi.mock('@/lib/cache-service', () => ({ cacheService: { clear: vi.fn() } }))
vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: () => '', language: 'en' }) }))
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ addToast }) }))

import MarkPaidPage from './page'

const PASSWORD = 'synthetic-admin-password'
const TOKEN = 'synthetic-session-token'
const REFERENCE = 'Bank transfer ref 2026-10-13/0042'
const MEMBER = { id: 42, email: 'member@example.com', username: 'member', full_name: 'Synthetic Member',
  first_name: null, last_name: null, avatar_url: null }

const refused = (status: number, code: string, message: string) =>
  ({ status, data: { detail: { code, message }, code: `HTTP_${status}` },
    config: { url: '/api/v1/admin/users/42/grant-payment' } })

const successes = () => addToast.mock.calls.filter(([, kind]) => kind === 'success').map(([text]) => text)
const errors = () => addToast.mock.calls.filter(([, kind]) => kind === 'error').map(([text]) => text)

async function chooseMember(credits = 0) {
  getMock.mockImplementation((url: string) => Promise.resolve(url.endsWith('/payment-status')
    ? { status: 200, data: { user_id: 42, available_credits: { kyc: credits }, identity_verified: false } }
    : { status: 200, data: [MEMBER] }))
  render(<MarkPaidPage />)
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'member' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
  fireEvent.click(await screen.findByRole('button', { name: /Synthetic Member/ }))
  await screen.findByLabelText('Your current password')
}

function fill(reference = REFERENCE, password = PASSWORD) {
  fireEvent.change(screen.getByLabelText(/Payment reference/), { target: { value: reference } })
  fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: password } })
}

describe('Mark as paid: a refused payment is not a payment', () => {
  const signedOut = vi.fn()

  beforeEach(() => {
    getMock.mockReset(); postMock.mockReset(); addToast.mockReset(); signedOut.mockReset()
    localStorage.setItem('access_token', TOKEN)
    window.addEventListener('auth:unauthorized', signedOut)
    return () => window.removeEventListener('auth:unauthorized', signedOut)
  })

  it('asks for a payment reference and the password before anything is sent', async () => {
    await chooseMember()
    const button = screen.getByRole('button', { name: 'Record payment for confirmation' })
    expect(button).toBeDisabled()
    fill('paid', PASSWORD)
    expect(button).toBeDisabled()                                    // says nothing about which payment
    fill(REFERENCE, '')
    expect(button).toBeDisabled()                                    // no password
    fill()
    expect(button).not.toBeDisabled()
    expect(postMock).not.toHaveBeenCalled()
  })

  it.each([
    [403, 'PERMISSION_REQUIRED', 'The grant_manual_payments permission is required.'],
    [403, 'REAUTH_REQUIRED', 'Enter your current password to confirm this action.'],
    [429, 'REAUTH_LOCKED', 'Too many incorrect passwords.'],
    [403, 'SELF_ACTION_FORBIDDEN', 'An administrator cannot perform this action on their own account.'],
    [403, 'COMMISSION_CONFLICT', 'You cannot record a payment for a member in your own referral line.'],
    [400, 'REASON_REQUIRED', 'Say which payment this is.'],
    [409, 'TARGET_NOT_ELIGIBLE', 'A payment cannot be recorded for an inactive account.'],
  ])('shows the refusal %i %s and changes nothing', async (status, code, message) => {
    await chooseMember(0)
    postMock.mockResolvedValue(refused(status, code, message))
    fill()
    fireEvent.click(screen.getByRole('button', { name: 'Record payment for confirmation' }))

    await waitFor(() => expect(errors()).toEqual([message]))
    expect(postMock).toHaveBeenCalledWith('/api/v1/admin/users/42/grant-payment', {
      product_code: 'kyc', notes: REFERENCE, current_password: PASSWORD })
    expect(successes()).toEqual([])                                  // "marked as paid successfully" was shown here
    // The reference is still there to correct and resend; the password is not kept.
    expect((screen.getByLabelText(/Payment reference/) as HTMLInputElement).value).toBe(REFERENCE)
    expect((screen.getByLabelText('Your current password') as HTMLInputElement).value).toBe('')
    // The credits shown are the ones the server last reported, not ones this page imagined.
    expect(getMock.mock.calls.filter(([url]) => String(url).endsWith('/payment-status')).length).toBe(1)
    // A refusal is not a sign-out.
    expect(localStorage.getItem('access_token')).toBe(TOKEN)
    expect(signedOut).not.toHaveBeenCalled()
  })

  it('does not report a payment when the server fails', async () => {
    await chooseMember()
    postMock.mockResolvedValue({ status: 500, data: { detail: 'Internal server error' }, config: { url: '/x' } })
    fill()
    fireEvent.click(screen.getByRole('button', { name: 'Record payment for confirmation' }))
    await waitFor(() => expect(errors().length).toBe(1))
    expect(successes()).toEqual([])
  })

  it('reports the payment as recorded, not credited: a second administrator has to confirm it', async () => {
    await chooseMember(0)
    postMock.mockResolvedValue({ status: 200, data: { status: 'pending_confirmation', request_id: 5, deposit_id: 9,
      product_code: 'kyc', identity_verified: false, available_credits: { kyc: 0 } } })
    fill()
    fireEvent.click(screen.getByRole('button', { name: 'Record payment for confirmation' }))
    await waitFor(() => expect(successes()).toEqual([
      'Payment recorded. A second administrator must confirm it was received before it is credited.']))
    // The queue of payments awaiting a second administrator is reloaded.
    await waitFor(() => expect(getMock.mock.calls.filter(([url]) => url === '/api/v1/admin/manual-payments').length).toBe(2))
    expect(errors()).toEqual([])
    expect((screen.getByLabelText(/Payment reference/) as HTMLInputElement).value).toBe('')
  })

  it('does not carry a payment reference typed for one member over to the next one', async () => {
    const other = { ...MEMBER, id: 43, email: 'other@example.com', username: 'other', full_name: 'Another Member' }
    getMock.mockImplementation((url: string) => Promise.resolve(url.endsWith('/payment-status')
      ? { status: 200, data: { user_id: 42, available_credits: { kyc: 0 }, identity_verified: false } }
      : { status: 200, data: [MEMBER, other] }))
    render(<MarkPaidPage />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'member' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    fireEvent.click(await screen.findByRole('button', { name: /Synthetic Member/ }))
    await screen.findByLabelText('Your current password')
    fill()
    fireEvent.click(screen.getByRole('button', { name: /Synthetic Member/ }))      // the same member again: kept
    expect((screen.getByLabelText(/Payment reference/) as HTMLInputElement).value).toBe(REFERENCE)
    fireEvent.click(screen.getByRole('button', { name: /Another Member/ }))
    await waitFor(() => expect((screen.getByLabelText(/Payment reference/) as HTMLInputElement).value).toBe(''))
    expect((screen.getByLabelText('Your current password') as HTMLInputElement).value).toBe('')
    expect(screen.getByRole('button', { name: 'Record payment for confirmation' })).toBeDisabled()
    expect(postMock).not.toHaveBeenCalled()
  })

  it('does not treat a refused member lookup as an empty or a loaded result', async () => {
    getMock.mockResolvedValue({ status: 403, data: { detail: 'Vous n\'avez pas les permissions pour accéder à cette ressource' },
      config: { url: '/api/v1/admin/users' } })
    render(<MarkPaidPage />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'member' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(errors()).toEqual(['Vous n\'avez pas les permissions pour accéder à cette ressource']))
    expect(localStorage.getItem('access_token')).toBe(TOKEN)
  })
})
