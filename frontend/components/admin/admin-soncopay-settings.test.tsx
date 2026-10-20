import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, putMock } = vi.hoisted(() => ({ getMock: vi.fn(), putMock: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock, put: putMock, post: vi.fn() }, apiService: {} }))

import AdminSoncoPaySettings from './admin-soncopay-settings'
import { FINANCE_SECTIONS } from '@/lib/finance-admin'
import {
  describeChanges, describeCredential, draftFrom, draftProblems, settingsChanges, type SoncoPayCredentialStatus,
} from '@/lib/soncopay-settings'

// Synthetic values only.
const PASSWORD = 'synthetic-admin-password'
const TEST_KEY = 'sp_test_synthetic_key_0000001'
const TEST_SECRET = 'whsec_test_synthetic_secret_01'
const LIVE_KEY = 'sp_live_synthetic_key_0000002'
const WEBHOOK = 'https://api.example.test/api/v1/webhooks/soncopay'

const credential = (name: string, environment: 'test' | 'live', kind: 'api_key' | 'webhook_secret', label: string,
  over: Record<string, unknown> = {}): SoncoPayCredentialStatus => ({
  name, environment, kind, label, configured: false, saved: false, saved_readable: null, saved_at: null, masked: null,
  ...(over as Partial<SoncoPayCredentialStatus>),
})
const credentials = (over: Record<string, Record<string, unknown>> = {}) => [
  credential('TEST_API_KEY', 'test', 'api_key', 'Test API key', over.TEST_API_KEY),
  credential('TEST_WEBHOOK_SECRET', 'test', 'webhook_secret', 'Test webhook signing secret', over.TEST_WEBHOOK_SECRET),
  credential('LIVE_API_KEY', 'live', 'api_key', 'Live API key', over.LIVE_API_KEY),
  credential('LIVE_WEBHOOK_SECRET', 'live', 'webhook_secret', 'Live webhook signing secret', over.LIVE_WEBHOOK_SECRET),
]
const view = (over: Record<string, unknown> = {}) => ({
  provider: 'soncopay', source: 'database', enabled: false, environment: 'test', environments: ['test', 'live'],
  default_provider: 'nowpayments', default_provider_in_force: 'nowpayments',
  checkout_providers: [
    { provider: 'nowpayments', label: 'NOWPayments', available: true },
    { provider: 'soncopay', label: 'SoncoPay', available: false, note: 'SoncoPay checkout is not implemented yet.' },
  ],
  credentials: credentials(), ready: { test: false, live: false }, webhook_url: WEBHOOK, webhook_operational: false,
  connection_test: { available: false, reason: "SoncoPay's API documentation has not been provided yet." },
  live_confirmation: 'USE SONCOPAY LIVE', encryption_key_configured: true, version: 2, can_change: true,
  last_change: null, ...over,
})
const saved = { configured: true, saved: true, saved_readable: true, saved_at: '2026-10-20T10:00:00' }

const type = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
const saveButton = () => screen.getByRole('button', { name: 'Save Settings' })

beforeEach(() => {
  getMock.mockReset()
  putMock.mockReset()
  getMock.mockResolvedValue({ status: 200, data: view() })
})

describe('Finance & Payments > SoncoPay Configuration', () => {
  it('is a section of the Finance & Payments pages, beside NOWPayments', () => {
    const slugs = FINANCE_SECTIONS.map((s) => s.slug)
    expect(slugs).toContain('nowpayments')
    expect(slugs.indexOf('soncopay')).toBe(slugs.indexOf('nowpayments') + 1)
  })

  it('shows every control, write-only secret fields, the webhook URL and the not-operational notice', async () => {
    render(<AdminSoncoPaySettings />)
    await screen.findByTestId('soncopay-settings-form')
    expect(screen.getByRole('switch', { name: 'SoncoPay enabled' })).not.toBeChecked()
    expect(screen.getByLabelText('Environment')).toHaveValue('test')
    for (const label of ['Test API key', 'Test webhook signing secret', 'Live API key', 'Live webhook signing secret']) {
      const input = screen.getByLabelText(label) as HTMLInputElement
      expect(input).toHaveValue('')
      expect(input.type).toBe('password')
    }
    const url = screen.getByLabelText(/Webhook URL/) as HTMLInputElement
    expect(url).toHaveValue(WEBHOOK)
    expect(url.readOnly).toBe(true)
    expect(screen.getByTestId('soncopay-not-operational')).toHaveTextContent('not active yet')
    // No documented endpoint: the connection test cannot be run.
    expect(screen.getByTestId('soncopay-connection-test')).toBeDisabled()
    // NOWPayments stays the default checkout; SoncoPay cannot be picked yet.
    const select = screen.getByLabelText('Default customer checkout') as HTMLSelectElement
    expect(select).toHaveValue('nowpayments')
    expect(select).toBeDisabled()
    expect(screen.getByRole('option', { name: /SoncoPay \(not available yet\)/ })).toBeDisabled()
    expect(saveButton()).toBeDisabled()
  })

  it('shows Configured and an API key\'s last four characters, never more', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({
      credentials: credentials({ TEST_API_KEY: { ...saved, masked: '••••0001' }, TEST_WEBHOOK_SECRET: saved }),
      ready: { test: true, live: false },
    }) })
    render(<AdminSoncoPaySettings />)
    await screen.findByTestId('soncopay-settings-form')
    expect(screen.getByTestId('soncopay-credential-TEST_API_KEY')).toHaveTextContent('Configured (••••0001)')
    expect(screen.getByTestId('soncopay-credential-TEST_WEBHOOK_SECRET')).toHaveTextContent(/^Configured$/)
    expect(screen.getByTestId('soncopay-credential-LIVE_API_KEY')).toHaveTextContent('Not configured')
    expect(document.body.textContent).not.toContain(TEST_KEY)
  })

  it('sends only what changed with the password, then clears every secret from the page', async () => {
    putMock.mockResolvedValue({ status: 200, data: view({ last_change: { at: null, by_user_id: 1, changed: ['TEST_API_KEY', 'TEST_WEBHOOK_SECRET'] } }) })
    render(<AdminSoncoPaySettings />)
    await screen.findByTestId('soncopay-settings-form')
    type('Test API key', TEST_KEY)
    type('Test webhook signing secret', TEST_SECRET)
    type('Your current password', PASSWORD)
    fireEvent.click(saveButton())
    await waitFor(() => expect(putMock).toHaveBeenCalledTimes(1))
    expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/soncopay', {
      test_api_key: TEST_KEY, test_webhook_secret: TEST_SECRET, current_password: PASSWORD, expected_version: 2,
    })
    expect(await screen.findByText('Settings saved: Test API key, Test webhook secret.')).toBeInTheDocument()
    expect(screen.getByLabelText('Test API key')).toHaveValue('')
    expect(screen.getByLabelText('Your current password')).toHaveValue('')
  })

  it('needs the typed confirmation to switch to Live', async () => {
    putMock.mockResolvedValue({ status: 200, data: view({ environment: 'live' }) })
    render(<AdminSoncoPaySettings />)
    await screen.findByTestId('soncopay-settings-form')
    fireEvent.change(screen.getByLabelText('Environment'), { target: { value: 'live' } })
    type('Your current password', PASSWORD)
    expect(saveButton()).toBeDisabled()
    type(/to switch to Live/, 'use soncopay live')
    expect(saveButton()).toBeDisabled()
    type(/to switch to Live/, 'USE SONCOPAY LIVE')
    fireEvent.click(saveButton())
    await waitFor(() => expect(putMock).toHaveBeenCalledTimes(1))
    expect(putMock.mock.calls[0][1]).toMatchObject({ environment: 'live', confirmation: 'USE SONCOPAY LIVE' })
  })

  it('shows a refusal and keeps nothing secret in the page', async () => {
    putMock.mockResolvedValue({ status: 409, data: { detail: { code: 'NOT_READY', message: 'SoncoPay cannot be on in Test yet. Save the Test API key first. Nothing was changed.' } } })
    render(<AdminSoncoPaySettings />)
    await screen.findByTestId('soncopay-settings-form')
    fireEvent.click(screen.getByRole('switch', { name: 'SoncoPay enabled' }))
    type('Live API key', LIVE_KEY)
    type('Your current password', PASSWORD)
    fireEvent.click(saveButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('Save the Test API key first')
    expect(screen.getByLabelText('Live API key')).toHaveValue('')
  })

  it('is read-only for an administrator who may only view', async () => {
    getMock.mockResolvedValue({ status: 200, data: view({ can_change: false }) })
    render(<AdminSoncoPaySettings />)
    await screen.findByTestId('soncopay-settings-form')
    expect(screen.getByText('You can view these settings. Only a Super Admin can change them.')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'SoncoPay enabled' })).toBeDisabled()
    expect(screen.getByLabelText('Test API key')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save Settings' })).toBeNull()
    expect(screen.queryByLabelText('Your current password')).toBeNull()
  })

  it('says so when the settings cannot be loaded', async () => {
    getMock.mockResolvedValue({ status: 403, data: { detail: { code: 'FORBIDDEN', message: 'A Super Admin or the manage_payment_settings permission is required.' } } })
    render(<AdminSoncoPaySettings />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/Super Admin/)
  })
})

describe('lib/soncopay-settings', () => {
  it('describes a credential without its value', () => {
    expect(describeCredential(credential('A', 'test', 'api_key', 'k', { ...saved, masked: '••••1a2b' }))).toBe('Configured (••••1a2b)')
    expect(describeCredential(credential('A', 'test', 'api_key', 'k', { saved: true, saved_readable: false }))).toMatch(/cannot be read/)
    expect(describeCredential(credential('A', 'test', 'api_key', 'k'))).toBe('Not configured')
  })

  it('finds URLs, spaces and short values in the secret fields, and sends nothing then', () => {
    const v = view() as any
    const draft = { ...draftFrom(v), testApiKey: 'https://example.test', testWebhookSecret: 'has space inside 1234', liveApiKey: 'short' }
    const problems = draftProblems(v, draft)
    expect(Object.keys(problems).sort()).toEqual(['liveApiKey', 'testApiKey', 'testWebhookSecret'])
    expect(settingsChanges(v, draft)).toBeNull()
    expect(settingsChanges(v, draftFrom(v))).toBeNull()
  })

  it('labels the changed settings', () => {
    expect(describeChanges(['SONCOPAY_ENABLED', 'LIVE_API_KEY'])).toBe('SoncoPay on/off, Live API key')
  })
})
