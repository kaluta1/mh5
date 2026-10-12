import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

const { getMock, postMock, putMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn(), putMock: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock, put: putMock }, apiService: {} }))
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => <a href={href} {...rest}>{children}</a>,
}))

import AdminFinance from './admin-finance'
import type { SettingField } from '@/lib/finance-admin'

// Synthetic values only. A credential typed in a test never comes back from the (mocked) API.
const SECRET = 'SYNTHETIC-payout-key-000111'
const PASSWORD = 'synthetic-admin-password'

const field = (over: Partial<SettingField> & { name: string; group: SettingField['group'] }): SettingField => ({
  kind: 'money', label: over.name, help: 'Help text.', value: '1.00', default: '1.00', minimum: '0.01', maximum: '100000',
  choices: [], unit: 'USD', max_length: null, approval_note: null, ...over,
})

const settings = (over: Record<string, unknown> = {}) => ({
  version: 3, persisted: true, updated_at: '2026-10-09T10:00:00',
  fields: [
    field({ name: 'provider_enabled', group: 'provider', kind: 'bool', label: 'Provider enabled', value: true, unit: '' }),
    field({ name: 'payout_credential_source', group: 'provider', kind: 'choice', label: 'Payout credential source',
      value: 'ENVIRONMENT', choices: ['ENVIRONMENT', 'DATABASE'], unit: '' }),
    field({ name: 'crypto_auto_payout_enabled', group: 'crypto', kind: 'bool', label: 'Automatic payouts', value: false, unit: '' }),
    field({ name: 'crypto_min_usd', group: 'crypto', label: 'Minimum crypto cashout', value: '1.00' }),
    field({ name: 'network_fee_policy', group: 'crypto', kind: 'choice', label: 'Network fee policy', value: 'MEMBER_PAYS',
      choices: ['COMPANY_PAYS', 'MEMBER_PAYS'], unit: '' }),
    field({ name: 'provider_fee_mode', group: 'crypto', kind: 'choice', label: 'Provider fee behaviour', value: 'UNVERIFIED',
      choices: ['UNVERIFIED', 'DEDUCTED_BY_PROVIDER', 'CHARGED_TO_BALANCE'], unit: '' }),
    field({ name: 'member_fee_cap_usd', group: 'crypto', label: 'Member network fee limit (amount)', value: '0.00',
      minimum: '0', approval_note: "Not set. Awaiting the business owner's decision." }),
    field({ name: 'fee_terms_approved', group: 'crypto', kind: 'bool', label: 'Network fee limits approved', value: false, unit: '' }),
    field({ name: 'usd_min_usd', group: 'usd', label: 'Minimum USD cashout', value: '100.00' }),
    field({ name: 'usd_settlement_enabled', group: 'usd', kind: 'bool', label: 'USD settlement', value: false, unit: '' }),
    field({ name: 'wallet_hold_hours', group: 'security', kind: 'int', label: 'Wallet security hold', value: 72,
      minimum: '0', maximum: '720', unit: 'hours' }),
  ],
  server_switches: { crypto_auto_payout: false, usd_settlement: false, environment: 'production', encryption_key_configured: true },
  effective: { automatic_crypto_payouts: false, usd_settlement: false },
  usd_fee_rule: '1% of the amount, minimum $20, maximum $1,000',
  supported_payout_currencies: [{ code: 'usdtbsc', currency: 'USDT', network: 'BSC (BEP20)' }],
  confirmations: { crypto_auto_payout_enabled: 'ENABLE AUTOMATIC PAYOUTS', usd_settlement_enabled: 'ENABLE USD SETTLEMENT',
    provider_fee_mode: 'PROVIDER FEE BEHAVIOUR VERIFIED', fee_terms_approved: 'APPROVE NETWORK FEE LIMITS' },
  ...over,
})

const credential = (name: string, label: string, group: string, stored: string) => ({
  name, label, group, source: 'ENVIRONMENT', stored, stored_readable: stored === 'CONFIGURED' ? true : null,
  stored_updated_at: null, environment: 'NOT CONFIGURED', in_use: 'NOT CONFIGURED',
})

const provider = (over: Record<string, unknown> = {}) => ({
  provider: 'nowpayments', display_name: 'NOWPayments', enabled: true, environment: 'production',
  payin_status: 'CONFIGURED', payout_status: 'NOT CONFIGURED', custody_status: 'NOT VERIFIED',
  payout_currency: 'USDT', payout_network: 'BSC (BEP20)', credential_sources: { payin: 'ENVIRONMENT', payout: 'ENVIRONMENT' },
  credentials: [
    credential('PAYIN_API_KEY', 'Pay-in API key', 'payin', 'NOT CONFIGURED'),
    credential('PAYOUT_API_KEY', 'Payout API key', 'payout', 'CONFIGURED'),
    credential('PAYOUT_PASSWORD', 'Payout login password', 'payout', 'NOT CONFIGURED'),
  ],
  encryption_key_configured: true,
  connection: { status: 'IP_NOT_WHITELISTED', message: "The provider refused this server's IP address.",
    tested_at: '2026-10-09T09:00:00', last_success_at: null,
    checks: [{ name: 'api_status', status: 'OK', message: 'Successful.' },
      { name: 'custody_balance', status: 'IP_NOT_WHITELISTED', message: "The provider refused this server's IP address." }],
    facts: {}, payout_login: 'NOT_TESTED' },
  last_configuration_update: '2026-10-09T10:00:00', configuration_version: 3, ...over,
})

const overview = (over: Record<string, unknown> = {}) => ({
  permissions: { can_manage: true, can_process: true },
  providers: [
    { key: 'nowpayments', name: 'NOWPayments', role: 'Crypto pay-in and payout', enabled: true, environment: 'production',
      payin_status: 'CONFIGURED', payout_status: 'NOT CONFIGURED', custody_status: 'NOT VERIFIED', connection_status: 'NOT_TESTED' },
    { key: 'usd_manual', name: 'USD settlement (manual)', role: 'USD cashout', enabled: false, environment: null,
      payin_status: null, payout_status: 'NO PROVIDER CONFIGURED', custody_status: null, connection_status: null },
  ],
  server_switches: { crypto_auto_payout: false, usd_settlement: false, environment: 'production', encryption_key_configured: true },
  effective: { automatic_crypto_payouts: false, usd_settlement: false },
  engine: { enabled: false, missing: [], credential_source: 'ENVIRONMENT' },
  webhook_status: 'SIGNATURE_REJECTIONS', configuration_version: 3,
  warnings: [{ code: 'IPN_SIGNATURE_REJECTIONS', level: 'critical',
    message: 'Recent payment callbacks were rejected because their signature did not verify.' }],
  ...over,
})

const webhook = {
  callback_url: 'https://myhigh5.com/api/v1/webhooks/nowpayments', callback_url_secure: true, status: 'SIGNATURE_REJECTIONS',
  last_7_days: { ACCEPTED: 0, REJECTED_SIGNATURE: 4, UNKNOWN_ORDER: 0 }, last_accepted_at: null,
  last_signature_rejection_at: '2026-10-09T08:00:00', signature_verification: 'HMAC-SHA512 over the sorted JSON body.',
}

const cashout = (over: Record<string, unknown> = {}) => ({
  id: 7, user_id: 42, username: 'synthetic_member', method: 'USD', status: 'requested', gross_amount: 150, fee: 20,
  net_amount: 130, network_fee: null, network_fee_policy: null, destination: null, payout_currency: null, reference: null,
  requested_at: '2026-10-09T08:00:00', processed_at: null, provider_status: null, provider_batch_id: null,
  failure_code: null, reviewed_by: null, has_destination_details: true, ...over,
})

function setup({ o = overview(), p = provider(), s = settings(), rows = [cashout()] as any[] } = {}) {
  getMock.mockImplementation((url: string) => {
    if (url.endsWith('/finance/overview')) return Promise.resolve({ status: 200, data: o })
    if (url.endsWith('/finance/provider')) return Promise.resolve({ status: 200, data: p })
    if (url.endsWith('/finance/settings')) return Promise.resolve({ status: 200, data: s })
    if (url.endsWith('/finance/webhook')) return Promise.resolve({ status: 200, data: webhook })
    if (url.endsWith('/finance/reconciliation')) return Promise.resolve({ status: 200, data: {
      owed: { pending: 1, available: 2, reserved: 150 }, owed_total: 153, owed_to_crypto_cashout_members: 3,
      open_cashouts: { requested: 1 }, provider_balance_state: 'NOT_VERIFIED', provider_balance: null,
      provider_covers_crypto_members: null,
      last_24_hours: { crypto_payout_amount: 0, crypto_payout_count: 0, amount_limit: 5000, count_limit: 100 },
      discrepancies: [{ type: 'UNKNOWN_OUTCOME', severity: 'critical', message: 'Cashout #9: the provider outcome is unknown.' }],
    } })
    if (url.endsWith('/finance/audit')) return Promise.resolve({ status: 200, data: { total: 1, items: [
      { id: 1, version: 3, action: 'CREDENTIALS_STORED', actor_id: 5, created_at: '2026-10-09T10:00:00',
        changed_fields: ['credentials_added'], old_values: {}, new_values: { credentials_added: ['PAYOUT_API_KEY'] } }] } })
    if (url.endsWith('/finance/financial-audit')) return Promise.resolve({ status: 200, data: { total: 0, items: [] } })
    if (url.endsWith('/finance/wallet-history')) return Promise.resolve({ status: 200, data: { total: 0, items: [], pending: [] } })
    if (url.endsWith('/cashouts/7/destination')) return Promise.resolve({ status: 200, data: { destination: 'SYNTHETIC BANK DETAILS' } })
    if (/\/cashouts\/\d+$/.test(url)) {
      const row = rows.find((r) => url.endsWith(`/${r.id}`)) ?? rows[0]
      return Promise.resolve({ status: 200, data: {
        cashout: row, member: { id: 42, username: 'synthetic_member', cashout_method: row.method, wallet: '0xaaaa...aaaa', wallet_status: 'VERIFIED' },
        commissions: [{ id: 1, amount: row.gross_amount, status: 'APPROVED', level: 1, transaction_date: '2026-10-01T00:00:00' }],
        attempts: [row] } })
    }
    if (url.endsWith('/admin/cashouts')) return Promise.resolve({ status: 200, data: { total: rows.length, items: rows } })
    return Promise.resolve({ status: 404, data: {} })
  })
  putMock.mockResolvedValue({ status: 200, data: {} })
  postMock.mockResolvedValue({ status: 200, data: {} })
}

describe('AdminFinance', () => {
  beforeEach(() => { getMock.mockReset(); postMock.mockReset(); putMock.mockReset() })

  it('lists the seven sections and the providers with their real status', async () => {
    setup()
    render(<AdminFinance section="providers" />)
    expect(await screen.findByText('Crypto pay-in and payout')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Finance & Payments sections' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual([
      'Payment Providers', 'NOWPayments Configuration', 'Crypto Cashout Settings', 'USD Cashout Settings',
      'Payout Security', 'Cashout Transactions', 'Reconciliation & Audit Logs'])
    expect(within(nav).getByRole('link', { name: 'Payment Providers' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('USD settlement (manual)')).toBeInTheDocument()
    expect(screen.getByText('No provider configured')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('signature did not verify')        // the open IPN blocker is visible
    expect(screen.getAllByText('Off').length).toBeGreaterThanOrEqual(4)                     // nothing that moves money is on
  })

  it('never shows a stored credential and sends only the fields that were typed', async () => {
    setup()
    render(<AdminFinance section="nowpayments" />)
    const payoutKey = await screen.findByLabelText('Payout API key') as HTMLInputElement
    expect(payoutKey.value).toBe('')                                                        // write-only: never pre-filled
    expect(payoutKey).toHaveAttribute('type', 'password')
    expect(payoutKey).toHaveAttribute('placeholder', 'Leave blank to keep the stored value')
    expect(screen.getByTestId('credential-status-PAYOUT_API_KEY')).toHaveTextContent('Stored: Configured')
    expect(screen.getByTestId('credential-status-PAYIN_API_KEY')).toHaveTextContent('Stored: Not configured')

    const store = screen.getByRole('button', { name: 'Store credentials' })
    expect(store).toBeDisabled()                                                            // nothing typed, no password
    fireEvent.change(screen.getByLabelText('Payout login password'), { target: { value: SECRET } })
    expect(store).toBeDisabled()                                                            // still no admin password
    const passwords = screen.getAllByLabelText('Your current password')
    fireEvent.change(passwords[passwords.length - 1], { target: { value: PASSWORD } })
    fireEvent.click(store)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/credentials', {
      values: { PAYOUT_PASSWORD: SECRET }, current_password: PASSWORD }))                   // blank fields are not sent
    await waitFor(() => expect((screen.getByLabelText('Payout login password') as HTMLInputElement).value).toBe(''))
    expect(document.body.innerHTML).not.toContain(SECRET)
    expect(document.body.innerHTML).not.toContain(PASSWORD)
  })

  it('deletes a stored credential only through its own confirmed action', async () => {
    setup()
    render(<AdminFinance section="nowpayments" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete stored payout api key' }))
    const confirm = screen.getByRole('button', { name: 'Confirm delete' })
    expect(confirm).toBeDisabled()
    expect(postMock).not.toHaveBeenCalled()
    const passwords = screen.getAllByLabelText('Your current password')
    fireEvent.change(passwords[passwords.length - 1], { target: { value: PASSWORD } })
    fireEvent.click(confirm)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/finance/credentials/PAYOUT_API_KEY/delete',
      { current_password: PASSWORD }))
  })

  it('shows what is verified, configured or blocked without calling a present credential verified', async () => {
    const readiness = {
      states: ['DISABLED', 'UNVERIFIED', 'CONFIGURED', 'BLOCKED', 'VERIFIED'],
      items: [
        { key: 'api_authentication', label: 'API authentication (pay-in key)', state: 'VERIFIED', detail: 'Successful.' },
        { key: 'custody', label: 'Custody balance access', state: 'BLOCKED', detail: "The provider refused this server's IP address." },
        { key: 'payout_2fa', label: 'Payout second factor (authenticator)', state: 'CONFIGURED', detail: 'It can be proven only by confirming a real payout.' },
        { key: 'automatic_payouts', label: 'Automatic crypto payouts', state: 'DISABLED', detail: 'The server master switch is off.' },
      ],
      outstanding: ["Whitelist this server's IPv4 and IPv6 addresses in the provider dashboard (Settings > Whitelist)."],
      last_test_at: '2026-10-09T09:00:00', last_success_at: null,
      last_error: { check: 'custody_balance', code: 'IP_NOT_WHITELISTED', message: "The provider refused this server's IP address.", at: '2026-10-09T09:00:00' },
    }
    setup({ p: provider({ readiness }) })
    render(<AdminFinance section="nowpayments" />)
    const pill = async (key: string) => (await screen.findByTestId(`readiness-${key}`)).querySelector('span.inline-block')!
    expect(await pill('api_authentication')).toHaveTextContent('Verified')
    expect((await pill('api_authentication')).className).toContain('green')
    expect(await pill('custody')).toHaveTextContent('Blocked')
    expect((await pill('custody')).className).toContain('red')
    expect(await pill('payout_2fa')).toHaveTextContent('Configured')
    expect((await pill('payout_2fa')).className).not.toContain('green')                     // present is not proven
    expect(await pill('automatic_payouts')).toHaveTextContent('Disabled')
    expect(screen.getByTestId('provider-last-error')).toHaveTextContent("refused this server's IP address")
    expect(screen.getByTestId('provider-outstanding')).toHaveTextContent('Whitelist this server')
    const card = screen.getByTestId('provider-readiness').closest('div')!
    expect(card.querySelector('button')).toBeNull()                                         // a status, never an action
    expect(postMock).not.toHaveBeenCalled()
  })

  it('explains a failed connection test and runs a new one without sending anything else', async () => {
    setup()
    render(<AdminFinance section="nowpayments" />)
    expect(await screen.findByTestId('connection-message')).toHaveTextContent("refused this server's IP address")
    expect(screen.getByText(/creates no payment, starts no payout and moves no funds/)).toBeInTheDocument()
    expect(screen.getByTestId('callback-url')).toHaveTextContent('https://myhigh5.com/api/v1/webhooks/nowpayments')
    expect(screen.queryByLabelText(/callback url/i)).toBeNull()                             // not editable
    fireEvent.click(screen.getByRole('button', { name: 'Run connection test' }))
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/finance/connection-test', {}))
    expect(postMock).toHaveBeenCalledTimes(1)
  })

  it('saves only changed settings, with the password, and asks for a phrase before activating payouts', async () => {
    setup()
    render(<AdminFinance section="crypto-cashout" />)
    const save = await screen.findByRole('button', { name: 'Save changes' })
    expect(save).toBeDisabled()
    // The member fee limit is not a decided policy yet, and the screen says so.
    expect(screen.getByTestId('approval-member_fee_cap_usd')).toHaveTextContent("Awaiting the business owner's decision")
    expect(screen.queryByTestId('approval-network_fee_policy')).toBeNull()                 // decided: the beneficiary pays
    expect(screen.getByText(/Server master switch: Off/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Minimum crypto cashout'), { target: { value: '2.50' } })
    expect(save).toBeDisabled()                                                             // no password yet
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(save)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { crypto_min_usd: '2.50' }, current_password: PASSWORD, confirmation: undefined }))

    fireEvent.click(screen.getByRole('switch', { name: 'Automatic payouts' }))
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    const phrase = screen.getByLabelText(/to confirm/)
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    fireEvent.change(phrase, { target: { value: 'enable' } })
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    fireEvent.change(phrase, { target: { value: 'ENABLE AUTOMATIC PAYOUTS' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(putMock).toHaveBeenLastCalledWith('/api/v1/admin/finance/settings', expect.objectContaining({
      changes: expect.objectContaining({ crypto_auto_payout_enabled: true }), confirmation: 'ENABLE AUTOMATIC PAYOUTS' })))
  })

  it('asks for a phrase before the provider fee behaviour is declared confirmed, and before the limits are approved', async () => {
    setup()
    render(<AdminFinance section="crypto-cashout" />)
    const save = await screen.findByRole('button', { name: 'Save changes' })
    fireEvent.change(screen.getByLabelText('Provider fee behaviour'), { target: { value: 'DEDUCTED_BY_PROVIDER' } })
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    const phrase = screen.getByLabelText(/to confirm/)
    expect(save).toBeDisabled()
    fireEvent.change(phrase, { target: { value: 'PROVIDER FEE BEHAVIOUR VERIFIED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(putMock).toHaveBeenLastCalledWith('/api/v1/admin/finance/settings', {
      changes: { provider_fee_mode: 'DEDUCTED_BY_PROVIDER' }, current_password: PASSWORD,
      confirmation: 'PROVIDER FEE BEHAVIOUR VERIFIED' }))

    fireEvent.click(screen.getByRole('switch', { name: 'Network fee limits approved' }))
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'APPROVE NETWORK FEE LIMITS' } })
    expect(screen.getByRole('button', { name: 'Save changes' })).not.toBeDisabled()
  })

  it('shows a payout suspension and reactivates only with a review note, the phrase and the password', async () => {
    setup({ s: settings({
      network_fee_gate: { code: 'PAYOUTS_SUSPENDED', message: 'Crypto payouts are suspended.' },
      payout_suspension: { reason: 'PROVIDER_FEE_MODE_MISMATCH', cashout_id: 12, since: '2026-10-11T09:00:00',
        rules_gate: 'PROVIDER_FEE_MODE_UNVERIFIED',
        message: 'The provider charged a network fee to the MyHigh5 balance instead of taking it out of the payout.' },
      confirmations: { payout_reactivation: 'REACTIVATE CRYPTO PAYOUTS', crypto_auto_payout_enabled: 'ENABLE AUTOMATIC PAYOUTS' },
    }) })
    render(<AdminFinance section="crypto-cashout" />)
    const card = await screen.findByTestId('payout-suspension')
    expect(card).toHaveTextContent('charged a network fee to the MyHigh5 balance')
    expect(card).toHaveTextContent('Cashout #12')
    expect(card).toHaveTextContent('This is a suspension, not the ordinary wait')
    expect(card).toHaveTextContent('restoring the settings below does not lift it, and neither does recording a fee')
    expect(card).toHaveTextContent('do not guarantee the actual network fee of any payout, including the first one')
    expect(screen.getByTestId('suspension-rules-gate')).toHaveTextContent('Provider fee mode unverified')
    expect(screen.queryByTestId('crypto-fee-gate')).toBeNull()                              // one message, not two
    const button = within(card).getByRole('button', { name: 'Reactivate crypto payouts' })
    const note = within(card).getByLabelText(/What was reviewed/)
    const phrase = within(card).getByLabelText(/to confirm/)
    const password = within(card).getByLabelText('Your current password')
    expect(button).toBeDisabled()
    fireEvent.change(password, { target: { value: PASSWORD } })
    fireEvent.change(phrase, { target: { value: 'REACTIVATE CRYPTO PAYOUTS' } })
    fireEvent.change(note, { target: { value: 'looks fine' } })
    expect(button).toBeDisabled()                                                           // not a review
    fireEvent.change(note, { target: { value: 'Checked payout 12 against the provider statement.' } })
    fireEvent.change(phrase, { target: { value: 'ENABLE AUTOMATIC PAYOUTS' } })
    expect(button).toBeDisabled()                                                           // another switch's phrase
    fireEvent.change(phrase, { target: { value: 'REACTIVATE CRYPTO PAYOUTS' } })
    fireEvent.click(button)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/finance/payouts/reactivate', {
      current_password: PASSWORD, confirmation: 'REACTIVATE CRYPTO PAYOUTS',
      note: 'Checked payout 12 against the provider statement.' }))
    expect(putMock).not.toHaveBeenCalled()                                                  // not a settings change
  })

  it('says why no payout can be created when nothing is suspended, and offers no reactivation', async () => {
    setup({ s: settings({ network_fee_gate: { code: 'FEE_SAFETY_MARGIN_NOT_SET',
      message: 'The safety margin on the network fee estimate is not set.' }, payout_suspension: null }) })
    render(<AdminFinance section="crypto-cashout" />)
    expect(await screen.findByTestId('crypto-fee-gate')).toHaveTextContent('safety margin on the network fee estimate is not set')
    expect(screen.queryByTestId('payout-suspension')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Reactivate crypto payouts' })).toBeNull()
  })

  it('shows the server refusal of an unsafe or invalid change', async () => {
    setup()
    putMock.mockResolvedValue({ status: 422, data: { detail: { code: 'INVALID_VALUE', field: 'usd_min_usd',
      message: 'At the minimum USD cashout ($10.00) the fee ($20.00) would leave nothing for the member.' } } })
    render(<AdminFinance section="usd-cashout" />)
    expect(await screen.findByTestId('usd-fee-rule')).toHaveTextContent('1% of the amount, minimum $20, maximum $1,000')
    fireEvent.change(screen.getByLabelText('Minimum USD cashout'), { target: { value: '10' } })
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(/would leave nothing for the member/)).toHaveAttribute('role', 'alert')
  })

  it('is read-only for an administrator without the permission', async () => {
    setup({ o: overview({ permissions: { can_manage: false, can_process: false }, warnings: [] }) })
    render(<AdminFinance section="payout-security" />)
    expect(await screen.findByLabelText('Wallet security hold')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save changes' })).toBeNull()
    expect(screen.getByText(/manage_payment_settings/)).toBeInTheDocument()
  })

  it('records a USD settlement with a reference and offers no way to send a payout by hand', async () => {
    setup()
    render(<AdminFinance section="transactions" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
    const detail = await screen.findByTestId('cashout-detail')
    expect(within(detail).getByText('$150.00')).toBeInTheDocument()                         // gross
    expect(within(detail).getByText('$20.00')).toBeInTheDocument()                          // fee
    expect(within(detail).getAllByText(/\$130\.00/).length).toBeGreaterThan(0)              // net
    expect(screen.queryByRole('button', { name: /pay now|send payout|retry/i })).toBeNull()

    const settle = within(detail).getByRole('button', { name: 'Record USD settlement' })
    expect(settle).toBeDisabled()
    fireEvent.change(within(detail).getByLabelText('External payment reference'), { target: { value: 'WIRE-2026-0001' } })
    fireEvent.click(settle)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/cashouts/7/settle-usd', { reference: 'WIRE-2026-0001' }))

    expect(screen.queryByTestId('usd-destination')).toBeNull()                              // hidden until asked for
    fireEvent.click(within(detail).getByRole('button', { name: /Show payout destination/ }))
    expect(await screen.findByTestId('usd-destination')).toHaveTextContent('SYNTHETIC BANK DETAILS')
  })

  it('filters transactions and lets an unknown crypto outcome be settled either way', async () => {
    const unknown = cashout({ id: 9, method: 'CRYPTO', status: 'unknown', gross_amount: 5, fee: 0, net_amount: 5,
      network_fee: 0.02, network_fee_policy: 'COMPANY_PAYS', destination: '0xaaaa...aaaa', failure_code: 'PROVIDER_OUTCOME_UNKNOWN',
      has_destination_details: false })
    setup({ rows: [unknown] })
    render(<AdminFinance section="transactions" />)
    await screen.findByRole('button', { name: 'Details' })
    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'CRYPTO' } })
    fireEvent.click(screen.getByRole('button', { name: 'Unknown outcomes' }))
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/api/v1/admin/cashouts',
      { params: { skip: 0, limit: 25, status: 'unknown' } }))
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    const detail = await screen.findByTestId('cashout-detail')
    expect(within(detail).getByText(/never sent again automatically/)).toBeInTheDocument()
    fireEvent.click(within(detail).getByRole('button', { name: 'It was not sent' }))
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/cashouts/9/resolve', { outcome: 'NOT_SENT' }))
  })

  it('records the actual network fee of a completed crypto payout and never offers the estimate', async () => {
    const row = cashout({ id: 11, method: 'CRYPTO', status: 'completed', gross_amount: 5, fee: 0, net_amount: 5,
      network_fee: 0.02, network_fee_policy: 'COMPANY_PAYS', payout_currency: 'usdtbsc', provider_batch_id: '5000000713' })
    setup({ rows: [row] })
    getMock.mockImplementation(((original) => (url: string, config?: unknown) => {
      if (/\/cashouts\/11$/.test(url)) {
        return Promise.resolve({ status: 200, data: {
          cashout: row, network_fee_record: { status: 'NOT_RECORDED', amount: null, source: null, reported: null, estimate: '0.02' },
          member: { id: 42, username: 'synthetic_member', cashout_method: 'CRYPTO', wallet: '0xaaaa...aaaa', wallet_status: 'VERIFIED' },
          commissions: [], attempts: [row] } })
      }
      return original(url, config)
    })(getMock.getMockImplementation()!))
    render(<AdminFinance section="transactions" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
    const form = await screen.findByTestId('network-fee-form')
    expect(screen.getByTestId('network-fee-record')).toHaveTextContent('Not recorded yet')
    const button = within(form).getByRole('button', { name: 'Record network fee' })
    const amount = within(form).getByLabelText(/Actual network fee/) as HTMLInputElement
    expect(amount.value).toBe('')                                                           // the estimate is not pre-filled
    expect(button).toBeDisabled()
    fireEvent.change(within(form).getByLabelText(/Where it was read/), { target: { value: 'payout 5000000713' } })
    for (const bad of ['-1', 'abc', '5.01', '0.123456789', '']) {
      fireEvent.change(amount, { target: { value: bad } })
      expect(button).toBeDisabled()
    }
    fireEvent.change(amount, { target: { value: '0.0234' } })
    expect(button).not.toBeDisabled()
    fireEvent.click(button)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/cashouts/11/network-fee',
      { amount: '0.0234', reference: 'payout 5000000713' }))
    expect(postMock).toHaveBeenCalledTimes(1)
  })

  it('hides every cashout action from an administrator who may not process cashouts', async () => {
    setup({ o: overview({ permissions: { can_manage: false, can_process: false }, warnings: [] }) })
    render(<AdminFinance section="transactions" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
    const detail = await screen.findByTestId('cashout-detail')
    expect(within(detail).queryByRole('button', { name: 'Record USD settlement' })).toBeNull()
    expect(within(detail).queryByRole('button', { name: 'Cancel request' })).toBeNull()
    expect(within(detail).getByText(/process_cashouts/)).toBeInTheDocument()
  })

  const memberFee = (over: Record<string, unknown> = {}) => ({
    applies: true, provider_fee_mode: 'DEDUCTED_BY_PROVIDER', gross: '5.00', amount_sent: '5', estimate: '0.02',
    estimate_adjusted: '0.025', margin_percent: '25', actual: null, net_received: null, fee_cap: '0.5', source: null,
    flag: null, reconciliation: null, evidence: null, reconciled: false, status: 'NOT_RECORDED', ...over })

  const openMemberPaid = async (fee: Record<string, unknown> = {}) => {
    const row = cashout({ id: 12, method: 'CRYPTO', status: 'completed', gross_amount: 5, fee: 0, net_amount: 4.98,
      network_fee: 0.02, network_fee_policy: 'MEMBER_PAYS', payout_currency: 'usdtbsc', provider_batch_id: '5000000714',
      beneficiary_fee: memberFee(fee) })
    setup({ rows: [row] })
    getMock.mockImplementation(((original) => (url: string, config?: unknown) => {
      if (/\/cashouts\/12$/.test(url)) {
        return Promise.resolve({ status: 200, data: {
          cashout: row, network_fee_record: { status: 'NOT_APPLICABLE', amount: null, source: null, reported: null, estimate: '0.02' },
          member: { id: 42, username: 'synthetic_member', cashout_method: 'CRYPTO', wallet: '0xaaaa...aaaa', wallet_status: 'VERIFIED' },
          commissions: [], attempts: [row] } })
      }
      return original(url, config)
    })(getMock.getMockImplementation()!))
    render(<AdminFinance section="transactions" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
    return screen.findByTestId('member-fee-form')
  }

  it('records an actual fee as NOT verified unless the administrator vouches for it, and never offers an estimate', async () => {
    const form = await openMemberPaid()
    expect(screen.queryByTestId('network-fee-form')).toBeNull()                             // no expense form: 5005 is not used
    expect(screen.queryByTestId('network-fee-record')).toBeNull()
    expect(screen.getByTestId('member-fee-sent')).toHaveTextContent('5 (Deducted by provider)')   // the whole amount was sent
    // Three different figures: the estimate, the estimate with the margin, and the actual fee.
    expect(screen.getByTestId('member-fee-adjusted')).toHaveTextContent('0.025 (margin 25%)')
    expect(screen.getByTestId('member-fee-actual')).toHaveTextContent('Not recorded yet')
    expect(screen.getByTestId('member-fee-reconciliation')).toHaveTextContent('does not count as reconciled')
    const button = within(form).getByRole('button', { name: 'Record actual fee (not verified)' })
    const amount = within(form).getByLabelText(/Actual network fee/) as HTMLInputElement
    expect(amount.value).toBe('')                                                           // no estimate is pre-filled
    fireEvent.change(within(form).getByLabelText(/Reference/), { target: { value: 'payout 5000000714' } })
    fireEvent.change(amount, { target: { value: '0.0234' } })
    expect(button).toBeDisabled()                                                           // who bore it is required
    fireEvent.change(within(form).getByLabelText(/Where the provider took it from/), { target: { value: 'PROVIDER_BALANCE' } })
    expect(screen.getByTestId('member-fee-mismatch-warning')).toHaveTextContent('a confirmed inconsistency')
    expect(screen.getByTestId('member-fee-mismatch-warning')).toHaveTextContent('suspends all crypto payouts')
    fireEvent.change(within(form).getByLabelText(/Where the provider took it from/), { target: { value: 'PAYOUT_AMOUNT' } })
    expect(screen.queryByTestId('member-fee-mismatch-warning')).toBeNull()
    expect(button).toBeDisabled()                                                           // and so is the evidence
    fireEvent.change(within(form).getByLabelText(/Evidence/), { target: { value: 'PROVIDER_STATEMENT' } })
    for (const bad of ['-1', 'abc', '5', '5.01', '0.123456789', '']) {                      // never the whole payout
      fireEvent.change(amount, { target: { value: bad } })
      expect(button).toBeDisabled()
    }
    fireEvent.change(amount, { target: { value: '0.0234' } })
    fireEvent.click(button)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/cashouts/12/network-fee',
      { amount: '0.0234', reference: 'payout 5000000714', charged_to: 'PAYOUT_AMOUNT', evidence: 'PROVIDER_STATEMENT',
        verified: false }))
    expect(postMock).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/recorded as NOT verified/)).toBeInTheDocument()
  })

  it('records a verified fee only with real evidence and an amount received that adds up', async () => {
    const form = await openMemberPaid()
    fireEvent.change(within(form).getByLabelText(/Actual network fee/), { target: { value: '0.0234' } })
    fireEvent.change(within(form).getByLabelText(/Where the provider took it from/), { target: { value: 'PAYOUT_AMOUNT' } })
    fireEvent.change(within(form).getByLabelText(/Reference/), { target: { value: 'payout 5000000714' } })
    fireEvent.change(within(form).getByLabelText(/Evidence/), { target: { value: 'OTHER' } })
    fireEvent.click(within(form).getByRole('checkbox'))
    const button = within(form).getByRole('button', { name: 'Record verified actual fee' })
    const received = within(form).getByLabelText(/Amount the member received/)
    fireEvent.change(received, { target: { value: '4.9766' } })
    expect(screen.getByTestId('member-fee-evidence-warning')).toHaveTextContent('cannot verify a payout')
    expect(button).toBeDisabled()                                                           // "other" verifies nothing
    fireEvent.change(within(form).getByLabelText(/Evidence/), { target: { value: 'BLOCKCHAIN_EXPLORER' } })
    for (const wrong of ['', '4.98', '5', '4.9765', 'abc']) {
      fireEvent.change(received, { target: { value: wrong } })
      expect(button).toBeDisabled()                                                         // 5.00 - 0.0234 = 4.9766
    }
    fireEvent.change(received, { target: { value: '4.98' } })
    expect(screen.getByTestId('member-fee-sum-warning')).toHaveTextContent('4.9766')
    fireEvent.change(received, { target: { value: '4.97660' } })                            // the same number
    expect(screen.queryByTestId('member-fee-sum-warning')).toBeNull()
    fireEvent.click(button)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/cashouts/12/network-fee',
      { amount: '0.0234', reference: 'payout 5000000714', charged_to: 'PAYOUT_AMOUNT', evidence: 'BLOCKCHAIN_EXPLORER',
        verified: true, received: '4.97660' }))
  })

  it('lets an unverified figure be replaced only by a verified one', async () => {
    const form = await openMemberPaid({ actual: '0.05', net_received: '4.95', source: 'ADMIN_RECORDED',
      reconciliation: 'ADMIN_UNVERIFIED', evidence: 'PROVIDER_STATEMENT', status: 'RECORDED' })
    expect(screen.getByTestId('member-fee-reconciliation')).toHaveTextContent('Entered by an administrator, not verified')
    expect(screen.getByTestId('member-fee-reconciliation')).toHaveTextContent('does not count as reconciled')
    expect(within(form).getByTestId('member-fee-replacing')).toHaveTextContent('0.05')
    expect(within(form).getByRole('checkbox')).toBeChecked()
    expect(within(form).getByRole('checkbox')).toBeDisabled()                               // no second unverified guess
    expect(within(form).queryByRole('button', { name: 'Record actual fee (not verified)' })).toBeNull()
    expect(within(form).getByRole('button', { name: 'Record verified actual fee' })).toBeDisabled()
  })

  it('shows a recorded beneficiary fee, what was received and a flag that needs attention', async () => {
    const row = cashout({ id: 13, method: 'CRYPTO', status: 'completed', gross_amount: 5, fee: 0, net_amount: 4.6,
      network_fee: 0.4, network_fee_policy: 'MEMBER_PAYS', payout_currency: 'usdtbsc',
      beneficiary_fee: { applies: true, provider_fee_mode: 'DEDUCTED_BY_PROVIDER', gross: '5.00', amount_sent: '5',
        estimate: '0.4', estimate_adjusted: '0.4', margin_percent: '0', actual: '0.75', net_received: '4.25',
        fee_cap: '0.5', source: 'PROVIDER_REPORTED', flag: 'FEE_CAP_EXCEEDED', reconciliation: 'PROVIDER_VERIFIED',
        evidence: 'PROVIDER_API', reconciled: true, status: 'RECORDED' } })
    setup({ rows: [row] })
    render(<AdminFinance section="transactions" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
    await screen.findByTestId('cashout-detail')
    expect(screen.getByTestId('member-fee-actual')).toHaveTextContent('0.75 (Provider reported)')
    expect(screen.getByTestId('member-fee-received')).toHaveTextContent('4.25')
    expect(screen.getByTestId('member-fee-flag')).toHaveTextContent('above the limit the member accepted')
    expect(screen.getByTestId('member-fee-reconciliation')).toHaveTextContent('Verified from the provider report')
    expect(screen.queryByTestId('member-fee-form')).toBeNull()                              // verified: never changed
  })

  it('reports beneficiary-paid fees apart from the ledger and says why no payout can be created', async () => {
    setup()
    getMock.mockImplementation(((original) => (url: string, config?: unknown) => {
      if (url.endsWith('/finance/reconciliation')) {
        return Promise.resolve({ status: 200, data: {
          owed: { pending: 0, available: 0, reserved: 0 }, owed_total: 0, owed_to_crypto_cashout_members: 0,
          open_cashouts: {}, provider_balance_state: 'NOT_VERIFIED', provider_balance: null,
          provider_covers_crypto_members: null,
          last_24_hours: { crypto_payout_amount: 0, crypto_payout_count: 0, amount_limit: 5000, count_limit: 100 },
          discrepancies: [{ type: 'MEMBER_FEE_NOT_RECORDED', severity: 'warning', cashout_id: 12,
            message: 'Cashout #12 is completed but the network fee the provider took from it is not recorded.' }],
          network_fee_gate: { code: 'PAYOUTS_SUSPENDED',
            message: 'Crypto payouts are suspended and need an administrator\'s review and an explicit reactivation.' },
          payout_suspension: { reason: 'FEE_CAP_EXCEEDED', cashout_id: 12, since: '2026-10-11T09:00:00', rules_gate: null,
            message: 'The network fee the provider took from a payout is higher than the limit the member accepted.' },
          recording_gate: { limit: 0, in_flight: 0, completed_unreconciled: 1, total: 1, blocked: true },
          beneficiary_fees: { completed_count: 2, gross_total: '12.00', recorded_count: 1, fee_total: '0.0234',
            received_total: '4.9766', not_recorded_count: 1, not_recorded: [{ cashout_id: 12, user_id: 42, estimate: '0.03' }],
            flagged: [], automatic_recording: false },
        } })
      }
      return original(url, config)
    })(getMock.getMockImplementation()!))
    render(<AdminFinance section="reconciliation" />)
    const fees = await screen.findByTestId('beneficiary-fees')
    expect(fees).toHaveTextContent('no ledger entry')
    expect(fees).toHaveTextContent('0.0234 · 1 payouts')
    expect(fees).toHaveTextContent('4.9766')
    expect(fees).toHaveTextContent('cashout #12')
    expect(fees).toHaveTextContent('not recorded automatically')
    expect(screen.getByTestId('network-fee-gate')).toHaveTextContent('explicit reactivation')
    expect(screen.getByTestId('reconciliation-suspension')).toHaveTextContent('cashout #12')
    expect(screen.getByTestId('reconciliation-suspension')).toHaveTextContent('until an administrator reactivates them')
    expect(screen.getByTestId('reconciliation-suspension')).toHaveTextContent('confirmed inconsistency')
    expect(screen.getByTestId('reconciliation-suspension')).toHaveTextContent('recording a fee does not lift it')
    // The temporary hold is worded as something else entirely.
    const gate = screen.getByTestId('recording-gate')
    expect(gate).toHaveTextContent('temporary hold')
    expect(gate).toHaveTextContent('On hold until these are verified, then released automatically')
    expect(gate).toHaveTextContent('This hold is not a suspension')
    expect(gate).toHaveTextContent('no reactivation is needed')
    expect(gate).toHaveTextContent('never taken to be zero')
    expect(gate).toHaveTextContent('does not guarantee the actual fee')
    expect(screen.getByTestId('discrepancies')).toHaveTextContent('Cashout #12')
  })

  it('shows what is owed, the discrepancies and the configuration history without claiming provider funds', async () => {
    setup()
    render(<AdminFinance section="reconciliation" />)
    expect(await screen.findByTestId('discrepancies')).toHaveTextContent('Cashout #9: the provider outcome is unknown.')
    expect(screen.getByText('$153.00')).toBeInTheDocument()
    expect(screen.getByText('Not verified')).toBeInTheDocument()                            // custody balance
    expect(screen.getByText(/not proof of the funds held by the provider/)).toBeInTheDocument()
    expect(await screen.findByText('Credentials stored')).toBeInTheDocument()
    expect(screen.getByText(/credentials_added: PAYOUT_API_KEY/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Read provider balance/ }))
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/api/v1/admin/finance/reconciliation',
      { params: { read_provider: true } }))
    expect(postMock).not.toHaveBeenCalled()
  })
})
