import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, putMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), putMock: vi.fn(), postMock: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock, put: putMock, post: postMock }, apiService: {} }))

import AdminKycSettings from './admin-kyc-settings'
import AdminKycSessionGrant, { sessionsLeft } from './admin-kyc-session-grant'
import {
  describeChanges, describeCredential, draftFrom, draftProblems, looksLikeUrl, parseSessionsInput, settingsChanges,
} from '@/lib/kyc-settings'

// Synthetic values only.
const PASSWORD = 'synthetic-admin-password'
const NEW_KEY = 'klt_synthetic_key_for_the_test_0001'
const NEW_SECRET = 'whsec_synthetic_secret_for_the_test_01'
const WEBHOOK = 'https://api.example.test/api/v1/kyc/webhook/kaluta'

const credential = (name: string, label: string, over: Record<string, unknown> = {}) => ({
  name, label, configured: false, saved: false, saved_readable: null, saved_at: null, ...over,
})
const view = (over: Record<string, unknown> = {}) => ({
  source: 'database', provider: 'kaluta', enabled: false,
  credentials: [credential('API_KEY', 'Kaluta API key'), credential('WEBHOOK_SECRET', 'Kaluta webhook secret')],
  ready_to_enable: false, webhook_url: WEBHOOK, redirect_url: null, encryption_key_configured: true,
  member_fee: { amount: '10.00', currency: 'USD', is_free: false, max_amount: '1000.00', product_configured: true, last_change: null },
  sessions_per_attempt: 3, sessions_per_attempt_min: 1, sessions_per_attempt_max: 10, sessions_per_attempt_default: 3,
  version: 4, can_change: true, permission: 'manage_kyc_settings', last_change: null, ...over,
})
const configured = { configured: true, saved: true, saved_readable: true, saved_at: '2026-10-15T10:00:00' }

const type = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
const saveButton = () => screen.getByRole('button', { name: 'Save Settings' })

beforeEach(() => {
  getMock.mockReset()
  putMock.mockReset()
  postMock.mockReset()
  getMock.mockResolvedValue({ status: 200, data: view() })
})

describe('Admin > KYC: Kaluta KYC settings (database only)', () => {
  it('shows every control, the state of each secret but never a value, and the webhook URL read-only', async () => {
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    expect(screen.getByRole('switch', { name: 'Kaluta KYC enabled' })).not.toBeChecked()
    expect(screen.getByTestId('kyc-credential-API_KEY')).toHaveTextContent('Not configured')
    expect(screen.getByTestId('kyc-credential-WEBHOOK_SECRET')).toHaveTextContent('Not configured')
    for (const label of ['Kaluta API key', 'Kaluta webhook secret']) {
      const input = screen.getByLabelText(label) as HTMLInputElement
      expect(input).toHaveValue('')
      expect(input.type).toBe('password')
    }
    expect(screen.getByLabelText('KYC verification fee (USD)')).toHaveValue(10)
    expect(screen.getByLabelText('Sessions per attempt')).toHaveValue(3)
    const url = screen.getByLabelText(/Webhook URL/) as HTMLInputElement
    expect(url).toHaveValue(WEBHOOK)
    expect(url.readOnly).toBe(true)
    expect(saveButton()).toBeDisabled()
    // The server environment is never presented as a source.
    expect(document.body.textContent).not.toMatch(/environment \(in use\)|from the server environment/i)
  })

  it('shows Configured for saved secrets and lets them be replaced without revealing them', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({
      enabled: true, ready_to_enable: true,
      credentials: [credential('API_KEY', 'Kaluta API key', configured), credential('WEBHOOK_SECRET', 'Kaluta webhook secret', configured)],
    }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    expect(screen.getByTestId('kyc-credential-API_KEY')).toHaveTextContent('Configured')
    expect(screen.getByLabelText('Kaluta API key')).toHaveAttribute('placeholder', 'Saved. Leave empty to keep it')
    expect(screen.getByTestId('kyc-enabled-state')).toHaveTextContent('Currently on')
  })

  it('copies the webhook URL', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(WEBHOOK))
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('saves every changed setting in one request, with the password and what was shown, and clears the secrets', async () => {
    putMock.mockResolvedValue({ status: 200, data: view({
      enabled: true, ready_to_enable: true, version: 5, sessions_per_attempt: 5,
      member_fee: { ...view().member_fee, amount: '12.50' },
      credentials: [credential('API_KEY', 'Kaluta API key', configured), credential('WEBHOOK_SECRET', 'Kaluta webhook secret', configured)],
      last_change: { at: null, by_user_id: 1, changed: ['API_KEY', 'KALUTA_ENABLED', 'MEMBER_FEE', 'SESSIONS_PER_ATTEMPT', 'WEBHOOK_SECRET'] },
    }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    fireEvent.click(screen.getByRole('switch', { name: 'Kaluta KYC enabled' }))
    type('Kaluta API key', NEW_KEY)
    type('Kaluta webhook secret', NEW_SECRET)
    type('KYC verification fee (USD)', '12.5')
    type('Sessions per attempt', '5')
    expect(saveButton()).toBeDisabled()                                   // no password yet
    type('Your current password', PASSWORD)
    fireEvent.click(saveButton())
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/kyc/admin/settings', {
      enabled: true, api_key: NEW_KEY, webhook_secret: NEW_SECRET, member_fee: '12.50', sessions_per_attempt: 5,
      current_password: PASSWORD, expected_version: 4, expected_fee: '10.00',
    }))
    expect(await screen.findByText(/^Settings saved: API key, Kaluta KYC on\/off, KYC fee/)).toBeInTheDocument()
    expect(screen.getByLabelText('Kaluta API key')).toHaveValue('')
    expect(screen.getByLabelText('Kaluta webhook secret')).toHaveValue('')
    expect(screen.getByLabelText('Your current password')).toHaveValue('')
    expect(screen.getByLabelText('KYC verification fee (USD)')).toHaveValue(12.5)
    expect(document.body.textContent).not.toContain(NEW_KEY)
    expect(document.body.textContent).not.toContain(NEW_SECRET)
  })

  it('sends only the fee when only the fee changed, and never a blank secret', async () => {
    putMock.mockResolvedValue({ status: 200, data: view({ member_fee: { ...view().member_fee, amount: '0.00', is_free: true } }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    type('KYC verification fee (USD)', '0')
    type('Kaluta API key', '   ')
    type('Your current password', PASSWORD)
    fireEvent.click(saveButton())
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/kyc/admin/settings', {
      member_fee: '0.00', current_password: PASSWORD, expected_version: 4, expected_fee: '10.00',
    }))
  })

  it.each([
    ['KYC verification fee (USD)', '-1', /from 0 to 1000.00/],
    ['KYC verification fee (USD)', '10.001', /at most two decimals/],
    ['KYC verification fee (USD)', '1000.01', /from 0 to 1000.00/],
    ['Sessions per attempt', '0', /whole number from 1 to 10/],
    ['Sessions per attempt', '11', /whole number from 1 to 10/],
    ['Sessions per attempt', '2.5', /whole number from 1 to 10/],
  ])('refuses %s = %s before sending anything', async (label, value, message) => {
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    type(label, value)
    type('Your current password', PASSWORD)
    expect(screen.getByText(message)).toBeInTheDocument()
    expect(screen.getByLabelText(label)).toHaveAttribute('aria-invalid', 'true')
    expect(saveButton()).toBeDisabled()
    expect(putMock).not.toHaveBeenCalled()
  })

  it('refuses a pasted URL in a secret field before sending anything', async () => {
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    type('Kaluta webhook secret', WEBHOOK)
    type('Your current password', PASSWORD)
    expect(screen.getByText(/looks like a URL/)).toBeInTheDocument()
    expect(saveButton()).toBeDisabled()
    expect(putMock).not.toHaveBeenCalled()
  })

  it('says the secrets are needed when switching on without them', async () => {
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    fireEvent.click(screen.getByRole('switch', { name: 'Kaluta KYC enabled' }))
    expect(screen.getByText(/cannot be switched on without them/)).toBeInTheDocument()
  })

  it('shows the server refusal, keeps what was typed (not the secrets) and keeps the switch', async () => {
    putMock.mockResolvedValue({ status: 422, data: { detail: { code: 'INVALID_VALUE', field: 'MEMBER_FEE', message: 'KYC fee: The fee cannot be more than 1000.00 USD.' } } })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    type('KYC verification fee (USD)', '20')
    type('Kaluta API key', NEW_KEY)
    type('Your current password', PASSWORD)
    fireEvent.click(saveButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('KYC fee: The fee cannot be more than 1000.00 USD.')
    expect(screen.getByLabelText('KYC verification fee (USD)')).toHaveValue(20)
    expect(screen.getByLabelText('Kaluta API key')).toHaveValue('')
    expect(screen.getByRole('switch', { name: 'Kaluta KYC enabled' })).not.toBeChecked()
  })

  it('reloads after a conflict (somebody else saved first)', async () => {
    putMock.mockResolvedValue({ status: 409, data: { detail: { code: 'STALE', message: 'The KYC settings were changed by somebody else. Reload and try again.' } } })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    type('Sessions per attempt', '4')
    type('Your current password', PASSWORD)
    fireEvent.click(saveButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('changed by somebody else')
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2))
  })

  it('an administrator without the permission sees every setting read-only, with no password or save', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({ can_change: false }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    expect(screen.getByRole('switch', { name: 'Kaluta KYC enabled' })).toBeDisabled()
    for (const label of ['Kaluta API key', 'Kaluta webhook secret', 'KYC verification fee (USD)', 'Sessions per attempt']) {
      expect(screen.getByLabelText(label)).toBeDisabled()
    }
    expect(screen.queryByLabelText('Your current password')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Save Settings' })).toBeNull()
    expect(screen.getByText(/needs the manage_kyc_settings permission or a Super Admin/)).toBeInTheDocument()
  })

  it('without the encryption key, secrets cannot be entered but the other settings can', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({ encryption_key_configured: false }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    expect(screen.getByLabelText('Kaluta API key')).toBeDisabled()
    expect(screen.getByLabelText('Kaluta webhook secret')).toBeDisabled()
    expect(screen.getByLabelText('KYC verification fee (USD)')).not.toBeDisabled()
    expect(screen.getByText(/PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured/)).toBeInTheDocument()
  })

  it('without the KYC product the fee cannot be edited', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({ member_fee: { ...view().member_fee, product_configured: false } }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-form')
    expect(screen.getByLabelText('KYC verification fee (USD)')).toBeDisabled()
    expect(screen.getByText(/KYC product is not set up/)).toBeInTheDocument()
  })

  it('says so when the settings cannot be loaded', async () => {
    getMock.mockResolvedValue({ status: 403, data: { detail: 'Not enough permissions' } })
    render(<AdminKycSettings />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Not enough permissions')
  })
})

describe('kyc-settings helpers', () => {
  it('describes a credential without its value', () => {
    expect(describeCredential(credential('API_KEY', 'k', configured) as never)).toBe('Configured')
    expect(describeCredential(credential('API_KEY', 'k', { saved: true, saved_readable: false }) as never)).toMatch(/cannot be read/)
    expect(describeCredential(credential('API_KEY', 'k') as never)).toBe('Not configured')
  })

  it('a blank secret is never sent, an unchanged form is null, and an invalid value blocks the save', () => {
    const v = view() as never
    const base = draftFrom(v)
    expect(base).toEqual({ enabled: false, apiKey: '', webhookSecret: '', fee: '10.00', sessions: '3' })
    expect(settingsChanges(v, { ...base, apiKey: '  ', fee: '10' })).toBeNull()
    expect(settingsChanges(v, { ...base, webhookSecret: ' whsec_x ' })).toEqual({ webhook_secret: 'whsec_x' })
    expect(settingsChanges(v, { ...base, sessions: '7' })).toEqual({ sessions_per_attempt: 7 })
    expect(settingsChanges(v, { ...base, sessions: '7', fee: 'abc' })).toBeNull()
    expect(Object.keys(draftProblems(v, { ...base, apiKey: 'has space' }))).toEqual(['apiKey'])
    expect(looksLikeUrl(' https://x.test/hook')).toBe(true)
    expect(looksLikeUrl('whsec_abc')).toBe(false)
  })

  it('parses sessions per attempt as a whole number within the range', () => {
    expect(parseSessionsInput('4')).toBe(4)
    for (const bad of ['', '0', '11', '2.5', '-1', 'x', '1e1']) expect(parseSessionsInput(bad)).toBeNull()
    expect(describeChanges(['MEMBER_FEE', 'API_KEY'])).toBe('KYC fee, API key')
  })
})

describe('Admin > KYC: allow one more provider session', () => {
  const open = { id: 7, status: 'in_progress', attempt_sessions_count: 3, attempt_sessions_granted: 0 }

  it('counts the sessions left, with the sessions-per-attempt setting the server sent', () => {
    expect(sessionsLeft(open)).toBe(0)
    expect(sessionsLeft({ ...open, attempt_sessions_granted: 1 })).toBe(1)
    expect(sessionsLeft({ ...open, attempt_sessions_count: null })).toBeNull()
    expect(sessionsLeft({ ...open, sessions_per_attempt: 5 })).toBe(2)
    expect(sessionsLeft({ ...open, sessions_per_attempt: 1, attempt_sessions_count: 1 })).toBe(0)
  })

  it('is offered only when the open attempt has no session left, and sends the password', async () => {
    postMock.mockResolvedValue({ status: 200, data: { sessions_left: 1 } })
    const onGranted = vi.fn()
    render(<AdminKycSessionGrant verification={open} onGranted={onGranted} />)
    const button = screen.getByRole('button', { name: 'Allow one more session' })
    expect(button).toBeDisabled()
    type('Your current password', PASSWORD)
    fireEvent.click(button)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/kyc/admin/verification/7/grant-session',
      { current_password: PASSWORD }))
    expect(await screen.findByRole('status')).toHaveTextContent('One more session allowed')
    expect(onGranted).toHaveBeenCalled()
  })

  it('is not shown for a closed verification, and offers nothing while sessions are left', () => {
    const { rerender } = render(<AdminKycSessionGrant verification={{ ...open, status: 'approved' }} />)
    expect(screen.queryByTestId('kyc-session-grant')).toBeNull()
    rerender(<AdminKycSessionGrant verification={{ ...open, attempt_sessions_count: 1 }} />)
    expect(screen.getByTestId('kyc-session-grant')).toHaveTextContent('left for this attempt: 2')
    expect(screen.queryByRole('button', { name: 'Allow one more session' })).toBeNull()
  })
})
