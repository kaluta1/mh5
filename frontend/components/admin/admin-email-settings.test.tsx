import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, postMock, putMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn(), postMock: vi.fn(), putMock: vi.fn(), deleteMock: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: { get: getMock, post: postMock, put: putMock, delete: deleteMock },
  apiService: {},
}))

import AdminEmailSettings from './admin-email-settings'

const SECRET = 're_SYNTHETIC_fake_value_1234'

const overview = (over: Record<string, unknown> = {}) => ({
  status: 'active', email_enabled: true, emergency_stop: false,
  provider: { resend_enabled: true, configured: true, key_source: 'environment' },
  critical_events: [{ key: 'AUTH.PASSWORD_RESET', label: 'Password reset', enabled: true }],
  critical_email_active: true,
  stats: { queued: 3, processing: 0, sent_24h: 12, failed_24h: 2, suppressed_24h: 1 },
  warnings: [{ code: 'RECENT_FAILURES', level: 'warning', message: '2 email(s) failed in the last 24 hours.' }],
  can_manage: true, emergency_stop_phrase: 'STOP ALL EMAIL', ...over,
})

const provider = (over: Record<string, unknown> = {}) => ({
  resend_enabled: true, configured: true, key_source: 'admin_override', environment_key_configured: true,
  override_configured: true, override_readable: true, override_last4: '1234', override_updated_at: '2026-10-05T10:00:00',
  encryption_key_configured: true, from_name: null, from_address: null, effective_from_name: 'MyHigh5',
  effective_from_address: 'infos@myhigh5.com', reply_to: null, support_address: null,
  effective_support_address: 'infos@myhigh5.com', admin_alert_recipients: [], allowed_from_domains: ['myhigh5.com'], ...over,
})

const events = [
  { key: 'AUTH.PASSWORD_RESET', label: 'Password reset', category: 'AUTH', classification: 'security', recipient: 'User',
    critical: true, default_enabled: true, enabled: true, phase: 'IMPLEMENT_NOW', trigger_implemented: true,
    disable_warning: 'Members who forget their password will not receive a reset link.' },
  { key: 'CONTEST.NOMINATION_PUBLISHED', label: 'Nomination published', category: 'CONTEST', classification: 'transactional',
    recipient: 'Nominator', critical: false, default_enabled: true, enabled: true, phase: 'IMPLEMENT_NOW',
    trigger_implemented: false, disable_warning: null },
]

const deliveries = {
  total: 1, page: 1, limit: 25, items: [{
    id: 9, created_at: '2026-10-05T10:00:00', event_key: 'AUTH.PASSWORD_RESET', event_label: 'Password reset', category: 'AUTH',
    recipient: 'j***@e***.com', provider: 'resend', status: 'SENT', attempts: 1, provider_message_id: 'msg_1', failure_category: null,
  }],
}

function setup(o = overview(), p = provider()) {
  getMock.mockImplementation((url: string) => {
    if (url.endsWith('/overview')) return Promise.resolve({ status: 200, data: o })
    if (url.endsWith('/provider')) return Promise.resolve({ status: 200, data: p })
    if (url.endsWith('/events')) return Promise.resolve({ status: 200, data: { events, count: events.length } })
    if (url.endsWith('/deliveries')) return Promise.resolve({ status: 200, data: deliveries })
    return Promise.resolve({ status: 404, data: {} })
  })
  putMock.mockResolvedValue({ status: 200, data: {} })
  postMock.mockResolvedValue({ status: 200, data: { success: true, status: 'SENT', recipient: 'a***@e***.com' } })
  deleteMock.mockResolvedValue({ status: 200, data: {} })
}

const openTab = async (name: string) => fireEvent.click(await screen.findByRole('tab', { name }))

describe('AdminEmailSettings', () => {
  beforeEach(() => { getMock.mockReset(); postMock.mockReset(); putMock.mockReset(); deleteMock.mockReset() })

  it('shows the system status, delivery health and warnings on the overview', async () => {
    setup()
    render(<AdminEmailSettings />)
    expect(await screen.findAllByText('Active')).toHaveLength(2)   // system status + security-critical email
    expect(screen.getByText('Configured')).toBeInTheDocument()
    expect(screen.getByTestId('stat-queued')).toHaveTextContent('3')
    expect(screen.getByTestId('stat-failed')).toHaveTextContent('2')
    expect(screen.getByText(/2 email\(s\) failed/)).toBeInTheDocument()
  })

  it('shows "Configuration required" when the server has no email encryption key', async () => {
    setup(overview({
      status: 'configuration_required', critical_email_active: false,
      warnings: [{ code: 'ENCRYPTION_KEY_MISSING', level: 'critical',
        message: 'Configuration required: EMAIL_SETTINGS_ENCRYPTION_KEY is not set on the server.' }],
    }), provider({ encryption_key_configured: false, override_configured: false, key_source: 'environment' }))
    render(<AdminEmailSettings />)
    expect(await screen.findByText('Configuration required')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('EMAIL_SETTINGS_ENCRYPTION_KEY is not set')
    await openTab('Provider')
    expect(await screen.findByLabelText('Set API key override')).toBeDisabled()
  })

  it('switches the normal email system through the API', async () => {
    setup()
    render(<AdminEmailSettings />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Email System' }))
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/email-settings/master', { enabled: false }))
  })

  it('requires the typed phrase before an emergency stop', async () => {
    setup()
    render(<AdminEmailSettings />)
    fireEvent.click(await screen.findByRole('button', { name: /Stop all email/ }))
    const confirm = screen.getByRole('button', { name: 'Confirm emergency stop' })
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'stop' } })
    expect(confirm).toBeDisabled()
    expect(putMock).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'STOP ALL EMAIL' } })
    fireEvent.click(confirm)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith(
      '/api/v1/admin/email-settings/emergency-stop', { active: true, confirmation: 'STOP ALL EMAIL' }))
  })

  it('disables every control for an admin without manage_email_settings', async () => {
    setup(overview({ can_manage: false }))
    render(<AdminEmailSettings />)
    expect(await screen.findByRole('switch', { name: 'Email System' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Stop all email/ })).toBeDisabled()
    expect(screen.getByText(/Changing them needs the/)).toBeInTheDocument()
    await openTab('Provider')
    expect(await screen.findByRole('button', { name: 'Save API key' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Send test email' })).toBeDisabled()
    await openTab('Events')
    expect(await screen.findByRole('switch', { name: 'Password reset' })).toBeDisabled()
  })

  it('never shows a stored key, only its source and last four characters', async () => {
    setup()
    const { container } = render(<AdminEmailSettings />)
    await openTab('Provider')
    expect(await screen.findByTestId('key-source')).toHaveTextContent('Admin override')
    expect(screen.getByText(/ends in 1234/)).toBeInTheDocument()
    expect((screen.getByLabelText('Replace API key override') as HTMLInputElement).value).toBe('')
    expect(container.innerHTML).not.toContain('re_')
  })

  it('sends a new key once and clears the field', async () => {
    setup()
    const { container } = render(<AdminEmailSettings />)
    await openTab('Provider')
    const input = (await screen.findByLabelText('Replace API key override')) as HTMLInputElement
    expect(input.type).toBe('password')
    fireEvent.change(input, { target: { value: SECRET } })
    fireEvent.click(screen.getByRole('button', { name: 'Save API key' }))
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/email-settings/provider/api-key', { api_key: SECRET }))
    await waitFor(() => expect(input.value).toBe(''))
    expect(container.innerHTML).not.toContain(SECRET)
  })

  it('sends a test email to exactly one address', async () => {
    setup()
    render(<AdminEmailSettings />)
    await openTab('Provider')
    const recipient = await screen.findByLabelText('Test recipient')
    const send = screen.getByRole('button', { name: 'Send test email' })
    fireEvent.change(recipient, { target: { value: 'a@example.com, b@example.com' } })
    expect(send).toBeDisabled()
    fireEvent.change(recipient, { target: { value: 'a@example.com' } })
    fireEvent.click(send)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/email-settings/test', { recipient: 'a@example.com' }))
    expect(await screen.findByText(/Test email sent to/)).toBeInTheDocument()
  })

  it('asks for confirmation, with the consequence, before disabling a critical email', async () => {
    setup()
    render(<AdminEmailSettings />)
    await openTab('Events')
    fireEvent.click(await screen.findByRole('switch', { name: 'Password reset' }))
    expect(putMock).not.toHaveBeenCalled()
    expect(screen.getByText(/will not receive a reset link/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Disable this security email' }))
    await waitFor(() => expect(putMock).toHaveBeenCalledWith(
      '/api/v1/admin/email-settings/events/AUTH.PASSWORD_RESET', { enabled: false, confirm_critical: true }))
  })

  it('marks events the application does not emit yet', async () => {
    setup()
    render(<AdminEmailSettings />)
    await openTab('Events')
    expect(await screen.findByText('Nomination published')).toBeInTheDocument()
    expect(screen.getAllByText('Trigger not implemented')).toHaveLength(1)
    expect(screen.getAllByText('Critical')).toHaveLength(1)
  })

  it('lists deliveries with a masked recipient and passes the filters', async () => {
    setup()
    render(<AdminEmailSettings />)
    await openTab('Delivery Logs')
    expect(await screen.findByText('j***@e***.com')).toBeInTheDocument()
    expect(screen.getByText('msg_1')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'FAILED' } })
    await waitFor(() => expect(getMock).toHaveBeenCalledWith(
      '/api/v1/admin/email-settings/deliveries', { params: { page: 1, limit: 25, status: 'FAILED' } }))
    expect(screen.queryByRole('button', { name: /retry|resend/i })).toBeNull()
  })
})
