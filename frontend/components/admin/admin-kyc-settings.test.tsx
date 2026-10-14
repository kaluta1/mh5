import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, putMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), putMock: vi.fn(), postMock: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock, put: putMock, post: postMock }, apiService: {} }))

import AdminKycSettings from './admin-kyc-settings'
import AdminKycSessionGrant, { sessionsLeft } from './admin-kyc-session-grant'
import { describeCredential, looksLikeUrl, settingsChanges } from '@/lib/kyc-settings'

// Synthetic values only.
const PASSWORD = 'synthetic-admin-password'
const NEW_KEY = 'klt_synthetic_key_for_the_test_0001'
const WEBHOOK = 'https://api.example.test/api/v1/kyc/webhook/kaluta'

const credential = (name: string, label: string, over: Record<string, unknown> = {}) => ({
  name, label, saved: false, saved_readable: null, saved_at: null, environment_configured: true,
  in_use: 'environment', configured: true, ...over,
})
const view = (over: Record<string, unknown> = {}) => ({
  provider: 'kaluta', enabled: false, enabled_source: 'environment',
  credentials: [credential('API_KEY', 'Kaluta API key'), credential('WEBHOOK_SECRET', 'Kaluta webhook secret')],
  ready_to_enable: true, webhook_url: WEBHOOK, redirect_url: null, encryption_key_configured: true,
  sessions_per_attempt: 3, version: 4, can_change: true, permission: 'manage_kyc_settings', last_change: null, ...over,
})

const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

beforeEach(() => {
  getMock.mockReset()
  putMock.mockReset()
  postMock.mockReset()
  getMock.mockResolvedValue({ status: 200, data: view() })
})

describe('Admin > KYC: Kaluta KYC settings', () => {
  it('shows the state of each secret, never a value, and the webhook URL read-only', async () => {
    render(<AdminKycSettings />)
    expect(await screen.findByTestId('kyc-credential-API_KEY')).toHaveTextContent('From the server environment (in use)')
    const url = screen.getByLabelText(/Webhook URL/) as HTMLInputElement
    expect(url).toHaveValue(WEBHOOK)
    expect(url.readOnly).toBe(true)
    // The secret fields always start empty and are password fields.
    for (const label of ['New Kaluta API key', 'New Kaluta webhook secret']) {
      const input = screen.getByLabelText(label) as HTMLInputElement
      expect(input).toHaveValue('')
      expect(input.type).toBe('password')
    }
  })

  it('copies the webhook URL', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-state')
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(WEBHOOK))
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('sends only what changed, with the password and the version, and clears the secrets', async () => {
    putMock.mockResolvedValue({ status: 200, data: view({ enabled: true, enabled_source: 'admin_panel', version: 5 }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-state')
    const save = screen.getByRole('button', { name: 'Save KYC settings' })
    expect(save).toBeDisabled()                                           // nothing changed
    fireEvent.click(screen.getByLabelText('Kaluta KYC enabled'))
    type('New Kaluta API key', NEW_KEY)
    expect(save).toBeDisabled()                                           // no password yet
    type('Your current password', PASSWORD)
    fireEvent.click(save)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/kyc/admin/settings', {
      enabled: true, api_key: NEW_KEY, current_password: PASSWORD, expected_version: 4,
    }))
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
    expect(screen.getByLabelText('New Kaluta API key')).toHaveValue('')
    expect(screen.getByLabelText('Your current password')).toHaveValue('')
    expect(document.body.textContent).not.toContain(NEW_KEY)
  })

  it('refuses a pasted URL in a secret field before sending anything', async () => {
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-state')
    type('New Kaluta webhook secret', WEBHOOK)
    type('Your current password', PASSWORD)
    expect(screen.getByRole('alert')).toHaveTextContent('looks like a URL')
    expect(screen.getByRole('button', { name: 'Save KYC settings' })).toBeDisabled()
    expect(putMock).not.toHaveBeenCalled()
  })

  it('shows the server refusal and keeps the switch as it was', async () => {
    putMock.mockResolvedValue({ status: 409, data: { detail: { code: 'NOT_READY', message: 'Save the Kaluta webhook secret before switching Kaluta KYC on. Nothing was changed.' } } })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-state')
    fireEvent.click(screen.getByLabelText('Kaluta KYC enabled'))
    type('Your current password', PASSWORD)
    fireEvent.click(screen.getByRole('button', { name: 'Save KYC settings' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nothing was changed.')
    expect(screen.getByLabelText('Kaluta KYC enabled')).not.toBeChecked()
  })

  it('an administrator without the permission sees the state and no form', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({ can_change: false }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-state')
    expect(screen.queryByLabelText('New Kaluta API key')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Save KYC settings' })).toBeNull()
    expect(screen.getByText(/needs the manage_kyc_settings permission/)).toBeInTheDocument()
  })

  it('without the encryption key, secrets cannot be entered', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({ encryption_key_configured: false }) })
    render(<AdminKycSettings />)
    await screen.findByTestId('kyc-settings-state')
    expect(screen.getByLabelText('New Kaluta API key')).toBeDisabled()
    expect(screen.getByText(/PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured/)).toBeInTheDocument()
  })
})

describe('kyc-settings helpers', () => {
  it('describes a credential without its value', () => {
    expect(describeCredential(credential('API_KEY', 'k', { saved: true, saved_readable: true, in_use: 'admin_panel' }) as never))
      .toBe('Saved in the Admin Panel (in use)')
    expect(describeCredential(credential('API_KEY', 'k', { saved: true, saved_readable: false, in_use: 'environment' }) as never))
      .toMatch(/cannot be read/)
    expect(describeCredential(credential('API_KEY', 'k', { in_use: null, configured: false }) as never)).toBe('Not configured')
  })

  it('a blank secret is never sent, and nothing to save is null', () => {
    const v = view() as never
    expect(settingsChanges(v, { enabled: false, apiKey: '  ', webhookSecret: '' })).toBeNull()
    expect(settingsChanges(v, { enabled: false, apiKey: '', webhookSecret: ' whsec_x ' })).toEqual({ webhook_secret: 'whsec_x' })
    expect(looksLikeUrl(' https://x.test/hook')).toBe(true)
    expect(looksLikeUrl('whsec_abc')).toBe(false)
  })
})

describe('Admin > KYC: allow one more provider session', () => {
  const open = { id: 7, status: 'in_progress', attempt_sessions_count: 3, attempt_sessions_granted: 0 }

  it('counts the sessions left', () => {
    expect(sessionsLeft(open)).toBe(0)
    expect(sessionsLeft({ ...open, attempt_sessions_granted: 1 })).toBe(1)
    expect(sessionsLeft({ ...open, attempt_sessions_count: null })).toBeNull()
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
