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

// What the server says needs the activation permission (settings.activation).
const ACTIVATION = (on = false) => ({
  permission: 'activate_financial_operations',
  values: { crypto_auto_payout_enabled: true, usd_settlement_enabled: true, fee_terms_approved: true,
    provider_fee_mode: 'DEDUCTED_BY_PROVIDER' },
  automatic_payouts_on: on,
  while_automatic_payouts_on: { fields: ['crypto_min_usd', 'payout_credential_source'],
    switches: ['provider_enabled', 'crypto_cashout_enabled'], credential_group: 'payout' },
})
const MANAGE_ONLY = { permissions: { can_manage: true, can_process: false, can_activate: false }, warnings: [] }

// The administrator of most tests may configure, activate and process.
const overview = (over: Record<string, unknown> = {}) => ({
  permissions: { can_manage: true, can_process: true, can_activate: true },
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

function setup({ o = overview(), p = provider(), s = settings(), rows = [cashout()] as any[],
  status = null as any, exceptions = null as any, events = [] as any[] } = {}) {
  getMock.mockImplementation((url: string, options?: any) => {
    if (url.endsWith('/finance/payout-status')) return Promise.resolve(status ? { status: 200, data: status } : { status: 404, data: {} })
    if (url.endsWith('/cashouts/fee-exceptions')) {
      if (!exceptions) return Promise.resolve({ status: 404, data: {} })
      const wanted = options?.params?.state
      const items = exceptions.items.filter((i: any) => !wanted || i.review.state === wanted)
      return Promise.resolve({ status: 200, data: { ...exceptions, total: items.length, items } })
    }
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
        attempts: [row], fee_events: events } })
    }
    if (url.endsWith('/admin/cashouts')) return Promise.resolve({ status: 200, data: { total: rows.length, items: rows } })
    return Promise.resolve({ status: 404, data: {} })
  })
  putMock.mockResolvedValue({ status: 200, data: {} })
  postMock.mockResolvedValue({ status: 200, data: {} })
}

const SECTIONS = [
  { key: 'provider', title: 'A. Provider configuration', note: 'Where the provider takes its fee from.',
    fields: ['network_fee_policy', 'provider_fee_mode'] },
  { key: 'fee_limits', title: 'B. Network fee estimates and limits', note: 'Compared with the ESTIMATE.',
    fields: ['member_fee_cap_usd'] },
  { key: 'safety', title: 'C. Safety margin and recording gate', note: 'Margin and gate.', fields: [] },
  { key: 'activation', title: 'D. Approval and activation', note: 'Approve in a change of its own.',
    fields: ['fee_terms_approved', 'crypto_auto_payout_enabled'] },
  { key: 'limits', title: 'Payout limits and schedule', note: 'Amounts and intervals.', fields: ['crypto_min_usd'] },
]

const payoutStatus = (over: Record<string, unknown> = {}) => ({
  can_create_payouts: false, configuration_version: 3,
  blockers: [
    { code: 'SERVER_SWITCH_OFF', section: 'activation', temporary: false,
      message: 'The server master switch CRYPTO_AUTO_PAYOUT_ENABLED is off.',
      action: 'It is set on the server by the operator and cannot be changed here.' },
    { code: 'PROVIDER_FEE_MODE_UNVERIFIED', section: 'provider', temporary: false,
      message: 'The provider fee behaviour is not confirmed as DEDUCTED_BY_PROVIDER.',
      action: 'Confirm with the provider that it takes its network fee out of the amount sent.' },
    { code: 'FEE_LIMITS_NOT_CONFIGURED', section: 'fee_limits', temporary: false,
      message: 'No member network fee limit is set.',
      action: "Set at least one member network fee limit in section B. The value is the business owner's decision." },
  ],
  missing_settings: [{ field: 'provider_fee_mode', label: 'Provider fee behaviour', section: 'provider' },
    { field: 'member_fee_cap_usd', label: 'Member network fee limit (amount)', section: 'fee_limits' }],
  provider_semantics: { fee_mode: 'UNVERIFIED', fee_mode_confirmed: false, receiver_fee_values_confirmed: false,
    company_fee_values_confirmed: false, amount_meaning: null, automatic_verification: false },
  approval: { approved: false, can_approve: false,
    blocked_by: { code: 'PROVIDER_FEE_MODE_UNVERIFIED', message: 'The provider fee behaviour is not confirmed as DEDUCTED_BY_PROVIDER.' } },
  suspension: null,
  recording_gate: { limit: 0, in_flight: 0, completed_unreconciled: 0, total: 0, blocked: false },
  flagged_payouts: { pending_review: 0 },
  switches: { server: false, provider: true, crypto_cashout: true, automatic_payouts: false, credentials_ready: false },
  ...over,
})

const feeException = (over: Record<string, unknown> = {}) => ({
  cashout_id: 12, user_id: 42, username: 'synthetic_member', status: 'completed', processed_at: '2026-10-11T09:00:00',
  payout_currency: 'usdtbsc', destination: '0xaaaa...aaaa', provider_batch_id: 'batch-12', provider_status: 'FINISHED',
  flag: 'FEE_CAP_EXCEEDED', flag_message: 'The network fee the provider took is higher than the limit the member accepted.',
  flag_details: {}, caused_suspension: true, gross: '5.00', provider_fee_mode: 'DEDUCTED_BY_PROVIDER',
  expected: { amount_sent: '5', network_fee_estimate: '0.02', network_fee_estimate_adjusted: '0.03', fee_cap: '0.5', received: '4.98' },
  actual: { network_fee: '0.75', received: '4.25', fee_above_estimate: '0.73', fee_above_cap: '0.25', received_difference: '-0.73' },
  evidence: { source: 'PROVIDER_REPORTED', evidence: 'PROVIDER_API', reconciliation: 'PROVIDER_UNVERIFIED', reconciled: false, recorded: true },
  review: { state: 'PENDING', flag: 'FEE_CAP_EXCEEDED', message: null, reviewed_flag: null, reviewed_by: null,
    reviewed_at: null, note: null, superseded: false },
  ...over,
})

const exceptionList = (items: any[], over: Record<string, unknown> = {}) => ({
  total: items.length, flagged_count: items.length,
  pending_count: items.filter((i) => i.review.state === 'PENDING').length,
  reviewed_count: items.filter((i) => i.review.state === 'REVIEWED').length,
  payout_suspension: null, items, ...over,
})

const NOTE = 'Compared payout batch-12 with the provider statement; the fee is above the limit.'

describe('AdminFinance: Phase 3.3 Stage B', () => {
  beforeEach(() => { getMock.mockReset(); postMock.mockReset(); putMock.mockReset() })

  it('groups the Crypto Cashout settings into sections and says why no payout is created and what to do', async () => {
    setup({ s: settings({ crypto_sections: SECTIONS }), status: payoutStatus() })
    render(<AdminFinance section="crypto-cashout" />)
    const card = await screen.findByTestId('crypto-payout-status')
    expect(card).toHaveTextContent('No payout is created')
    expect(card).toHaveTextContent('Configuration version 3')
    expect(screen.getByTestId('status-fee-mode')).toHaveTextContent('Not confirmed')
    expect(screen.getByTestId('status-approval')).toHaveTextContent('Not approved')
    expect(screen.getByTestId('status-suspension')).toHaveTextContent('None')
    expect(screen.getByTestId('status-semantics-note')).toHaveTextContent('an administrator verifies each payout against evidence')
    // Every reason is listed, each with its action.
    expect(within(screen.getByTestId('payout-blockers')).getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByTestId('blocker-FEE_LIMITS_NOT_CONFIGURED')).toHaveTextContent("The value is the business owner's decision")
    expect(screen.getByTestId('payout-missing-settings')).toHaveTextContent('Provider fee behaviour; Member network fee limit (amount)')
    expect(screen.getByTestId('status-approval-note')).toHaveTextContent('They cannot be approved yet')
    expect(screen.queryByTestId('crypto-fee-gate')).toBeNull()                              // one explanation, not two
    for (const title of ['A. Provider configuration', 'B. Network fee estimates and limits',
      'C. Safety margin and recording gate', 'D. Approval and activation', 'E. Suspension and reactivation']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    }
    // Each section repeats the reasons that are resolved in it.
    expect(screen.getByTestId('crypto-provider-attention')).toHaveTextContent('not confirmed as DEDUCTED_BY_PROVIDER')
    expect(screen.getByTestId('crypto-fee_limits-attention')).toHaveTextContent('No member network fee limit is set')
    expect(screen.queryByTestId('crypto-safety-attention')).toBeNull()
    expect(screen.getByTestId('no-suspension')).toHaveTextContent('Crypto payouts are not suspended')
    expect(screen.queryByRole('button', { name: 'Reactivate crypto payouts' })).toBeNull()
  })

  it('shows unsupported company-paid choices as unavailable and cannot select them', async () => {
    const fields = settings().fields.map((f: SettingField) =>
      f.name === 'network_fee_policy' ? { ...f, disabled_choices: [{ value: 'COMPANY_PAYS', reason: 'Retired: the beneficiary bears the network fee.' }] }
        : f.name === 'provider_fee_mode' ? { ...f, disabled_choices: [{ value: 'CHARGED_TO_BALANCE', reason: 'Not available: under it MyHigh5 would bear the network fee.' }] }
          : f)
    setup({ s: settings({ fields, crypto_sections: SECTIONS }), status: payoutStatus() })
    render(<AdminFinance section="crypto-cashout" />)
    const policy = await screen.findByLabelText('Network fee policy') as HTMLSelectElement
    const company = within(policy).getByRole('option', { name: /Company pays/ }) as HTMLOptionElement
    expect(company.disabled).toBe(true)
    expect(company).toHaveTextContent('not available')
    expect((within(policy).getByRole('option', { name: 'Member pays' }) as HTMLOptionElement).disabled).toBe(false)
    const mode = screen.getByLabelText('Provider fee behaviour') as HTMLSelectElement
    expect((within(mode).getByRole('option', { name: /Charged to balance/ }) as HTMLOptionElement).disabled).toBe(true)
    expect(screen.getByTestId('unsupported-network_fee_policy-COMPANY_PAYS')).toHaveTextContent('Retired')
    expect(screen.getByTestId('unsupported-provider_fee_mode-CHARGED_TO_BALANCE')).toHaveTextContent('MyHigh5 would bear the network fee')
  })

  it('saves one section at a time and names the configuration version it was decided on', async () => {
    setup({ s: settings({ crypto_sections: SECTIONS }), status: payoutStatus() })
    putMock.mockResolvedValue({ status: 409, data: { detail: { code: 'STALE_CONFIGURATION',
      message: 'The configuration was changed by someone else since this page was loaded. Nothing was saved.' } } })
    render(<AdminFinance section="crypto-cashout" />)
    const heading = await screen.findByRole('heading', { name: 'B. Network fee estimates and limits' })
    const section = heading.parentElement as HTMLElement
    fireEvent.change(within(section).getByLabelText('Member network fee limit (amount)'), { target: { value: '0.75' } })
    fireEvent.change(within(section).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(within(section).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { member_fee_cap_usd: '0.75' }, current_password: PASSWORD, confirmation: undefined, expected_version: 3 }))
    expect(putMock).toHaveBeenCalledTimes(1)                                                // only that section's change
    expect(await screen.findByText(/changed by someone else since this page was loaded/)).toHaveAttribute('role', 'alert')
  })

  it('tells a suspension from the temporary hold and points to the review before a reactivation', async () => {
    const suspension = { reason: 'FEE_CAP_EXCEEDED', cashout_id: 12, since: '2026-10-11T09:00:00', rules_gate: null,
      message: 'The network fee the provider took from a payout is higher than the limit the member accepted.' }
    setup({
      s: settings({ crypto_sections: SECTIONS, payout_suspension: suspension,
        confirmations: { payout_reactivation: 'REACTIVATE CRYPTO PAYOUTS' } }),
      status: payoutStatus({
        suspension, flagged_payouts: { pending_review: 1 },
        recording_gate: { limit: 0, in_flight: 0, completed_unreconciled: 1, total: 1, blocked: true },
        blockers: [
          { code: 'PAYOUTS_SUSPENDED', section: 'suspension', temporary: false,
            message: 'Crypto payouts are suspended: the fee is above the limit.', action: 'Review the flagged payout, then reactivate explicitly in section E.' },
          { code: 'FEE_RECONCILIATION_PENDING', section: 'safety', temporary: true,
            message: "An earlier payout's actual network fee has not been verified yet.", action: 'No reactivation is needed.' },
        ] }),
    })
    render(<AdminFinance section="crypto-cashout" />)
    const card = await screen.findByTestId('crypto-payout-status')
    expect(card).toHaveTextContent('Suspended')
    expect(screen.getByTestId('status-suspension')).toHaveTextContent('Active')
    expect(screen.getByTestId('status-gate')).toHaveTextContent('1 outstanding, 0 allowed · new payouts on hold')
    expect(screen.getByTestId('blocker-FEE_RECONCILIATION_PENDING')).toHaveTextContent('Temporary: lifts by itself')
    expect(screen.getByTestId('blocker-PAYOUTS_SUSPENDED')).not.toHaveTextContent('Temporary')
    const suspended = screen.getByTestId('payout-suspension')
    expect(within(suspended).getByRole('heading', { name: 'E. Suspension and reactivation' })).toBeInTheDocument()
    expect(screen.getByTestId('suspension-pending-review')).toHaveTextContent('1 flagged payout has not been reviewed')
    expect(screen.getByTestId('suspension-pending-review')).toHaveTextContent('A review does not reactivate anything by itself')
    expect(screen.queryByTestId('no-suspension')).toBeNull()
  })

  it('shows a flagged payout with what was expected, what happened and why it was flagged', async () => {
    setup({ exceptions: exceptionList([feeException()], { payout_suspension: { reason: 'FEE_CAP_EXCEEDED', cashout_id: 12,
      since: null, rules_gate: null, message: 'Above the limit.' } }),
    events: [{ id: 1, action: 'CASHOUT_RESERVED', actor_id: 42, created_at: '2026-10-11T08:00:00', old_values: {}, new_values: {} },
      { id: 2, action: 'CASHOUT_MEMBER_FEE_RECORDED', actor_id: null, created_at: '2026-10-11T09:00:00', old_values: {}, new_values: {} }] })
    render(<AdminFinance section="reconciliation" />)
    const panel = await screen.findByTestId('flagged-payout-review')
    await waitFor(() => expect(screen.getByTestId('flagged-counts')).toHaveTextContent('1 to review'))
    expect(panel).toHaveTextContent('does not lift a suspension and does not allow a new payout')
    expect(screen.getByTestId('review-suspension')).toHaveTextContent('They stay suspended after a review')
    const row = screen.getByTestId('flagged-12')
    expect(row).toHaveTextContent('Cashout #12')
    expect(row).toHaveTextContent('Caused the suspension')
    expect(row).toHaveTextContent('Not reviewed')
    expect(screen.getByTestId('flagged-reason-12')).toHaveTextContent('The fee taken is above the limit the member accepted')
    fireEvent.click(within(row).getByRole('button', { name: 'Details' }))
    const detail = await screen.findByTestId('flagged-detail-12')
    expect(detail).toHaveTextContent("Provider's fee estimate")
    expect(detail).toHaveTextContent('0.02')
    expect(within(detail).getByTestId('actual-fee')).toHaveTextContent('0.75')
    expect(within(detail).getByTestId('actual-received')).toHaveTextContent('4.25')
    expect(detail).toHaveTextContent('0.25')                                                // above the member's limit
    expect(within(detail).getByTestId('exception-reconciliation')).toHaveTextContent('Reported by the provider, not verified · not reconciled')
    expect(within(detail).getByTestId('exception-unreconciled')).toHaveTextContent('A review does not change that')
    await waitFor(() => expect(within(detail).getByTestId('exception-events')).toHaveTextContent('Actual network fee recorded'))
    // No control here sends, releases or reactivates anything.
    for (const name of [/pay now/i, /send payout/i, /reactivate/i, /release/i, /clear/i]) {
      expect(within(panel).queryByRole('button', { name })).toBeNull()
    }
  })

  it('records a review only with a real note and the password, and says that nothing else changed', async () => {
    setup({ exceptions: exceptionList([feeException()]) })
    render(<AdminFinance section="reconciliation" />)
    const row = await screen.findByTestId('flagged-12')
    fireEvent.click(within(row).getByRole('button', { name: 'Details' }))
    const form = await screen.findByTestId('review-form')
    const button = within(form).getByRole('button', { name: 'Mark as reviewed' })
    const note = within(form).getByLabelText('What you checked and what you found')
    const password = within(form).getByLabelText('Your current password')
    expect(button).toBeDisabled()
    fireEvent.change(note, { target: { value: NOTE } })
    expect(button).toBeDisabled()                                                           // no password yet
    fireEvent.change(password, { target: { value: PASSWORD } })
    fireEvent.change(note, { target: { value: 'looks fine' } })
    expect(button).toBeDisabled()                                                           // not a review
    fireEvent.change(note, { target: { value: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaa' } })
    expect(button).toBeDisabled()                                                           // says nothing
    fireEvent.change(note, { target: { value: `  ${NOTE}  ` } })
    expect(button).not.toBeDisabled()
    fireEvent.click(button)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/cashouts/12/fee-review', {
      note: NOTE, current_password: PASSWORD }))
    expect(postMock).toHaveBeenCalledTimes(1)
    expect(putMock).not.toHaveBeenCalled()                                                  // no setting is touched
    expect(await screen.findByRole('status')).toHaveTextContent('Nothing else was changed')
  })

  it('shows the server refusal of a duplicate review and keeps the form', async () => {
    setup({ exceptions: exceptionList([feeException()]) })
    postMock.mockResolvedValue({ status: 409, data: { detail: { code: 'ALREADY_REVIEWED',
      message: 'This payout was already reviewed by administrator #5. A review is recorded once and is not replaced.' } } })
    render(<AdminFinance section="reconciliation" />)
    fireEvent.click(within(await screen.findByTestId('flagged-12')).getByRole('button', { name: 'Details' }))
    const form = await screen.findByTestId('review-form')
    fireEvent.change(within(form).getByLabelText('What you checked and what you found'), { target: { value: NOTE } })
    fireEvent.change(within(form).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(within(form).getByRole('button', { name: 'Mark as reviewed' }))
    expect(await screen.findByText(/already reviewed by administrator #5/)).toHaveAttribute('role', 'alert')
    expect(within(form).getByLabelText('Your current password')).toHaveValue('')            // the password is not kept
  })

  it('shows who reviewed a payout and offers no second review, and no review without the permission', async () => {
    const reviewed = feeException({ cashout_id: 13, review: { state: 'REVIEWED', flag: 'FEE_CAP_EXCEEDED', message: null,
      reviewed_flag: 'FEE_CAP_EXCEEDED', reviewed_by: 5, reviewed_at: '2026-10-12T10:00:00', note: NOTE, superseded: false } })
    const again = feeException({ cashout_id: 14, flag: 'PROVIDER_FEE_MODE_MISMATCH', review: { state: 'PENDING',
      flag: 'PROVIDER_FEE_MODE_MISMATCH', message: null, reviewed_flag: 'PROVIDER_AMOUNT_MISMATCH', reviewed_by: 5,
      reviewed_at: '2026-10-12T10:00:00', note: NOTE, superseded: true } })
    setup({ o: overview({ permissions: { can_manage: false, can_process: false }, warnings: [] }),
      exceptions: exceptionList([reviewed, again]) })
    render(<AdminFinance section="reconciliation" />)
    await screen.findByTestId('flagged-14')                                                  // "To review" is shown first
    expect(screen.queryByTestId('flagged-13')).toBeNull()
    expect(screen.getByTestId('flagged-superseded-14')).toHaveTextContent('needs a new review')
    fireEvent.click(within(screen.getByTestId('flagged-14')).getByRole('button', { name: 'Details' }))
    expect(await screen.findByTestId('flagged-detail-14')).toHaveTextContent('needs the process_cashouts permission')
    expect(screen.queryByTestId('review-form')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Reviewed' }))
    const done = await screen.findByTestId('flagged-13')
    expect(screen.getByTestId('flagged-review-13')).toHaveTextContent(`Reviewed by administrator #5`)
    expect(screen.getByTestId('flagged-review-13')).toHaveTextContent(NOTE)
    fireEvent.click(within(done).getByRole('button', { name: 'Details' }))
    await screen.findByTestId('flagged-detail-13')
    expect(screen.queryByRole('button', { name: 'Mark as reviewed' })).toBeNull()
    expect(postMock).not.toHaveBeenCalled()
  })

  it('says when no flagged payout is waiting and stays quiet when the list cannot be read', async () => {
    setup({ exceptions: exceptionList([]) })
    const { unmount } = render(<AdminFinance section="reconciliation" />)
    expect(await screen.findByTestId('flagged-empty')).toHaveTextContent('No flagged payout is waiting for a review')
    unmount()
    setup()                                                                                 // the endpoint answers 404
    render(<AdminFinance section="reconciliation" />)
    expect(await screen.findByText('The flagged payouts could not be loaded.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark as reviewed' })).toBeNull()
  })

  it('shows the review state of a flagged payout in its cashout details', async () => {
    const fee = { applies: true, provider_fee_mode: 'DEDUCTED_BY_PROVIDER', gross: '5.00', amount_sent: '5', estimate: '0.02',
      actual: '0.75', net_received: '4.25', fee_cap: '0.5', source: 'PROVIDER_REPORTED', flag: 'FEE_CAP_EXCEEDED',
      reconciliation: 'PROVIDER_VERIFIED', evidence: 'PROVIDER_API', reconciled: true, status: 'RECORDED' }
    setup({ rows: [cashout({ id: 12, method: 'CRYPTO', status: 'completed', gross_amount: 5, fee: 0, net_amount: 4.98,
      network_fee: 0.02, network_fee_policy: 'MEMBER_PAYS', payout_currency: 'usdtbsc', beneficiary_fee: fee,
      fee_review: { state: 'PENDING', flag: 'FEE_CAP_EXCEEDED', message: null, reviewed_flag: null, reviewed_by: null,
        reviewed_at: null, note: null, superseded: false } })] })
    render(<AdminFinance section="transactions" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
    const review = await screen.findByTestId('member-fee-review')
    expect(review).toHaveTextContent('Not reviewed yet: review it under Reconciliation & Audit Logs')
    expect(review).toHaveTextContent('a review does not clear the flag or lift a suspension')
  })
})

describe('AdminFinance', () => {
  beforeEach(() => { getMock.mockReset(); postMock.mockReset(); putMock.mockReset() })

  it('lists the eight sections and the providers with their real status', async () => {
    setup()
    render(<AdminFinance section="providers" />)
    expect(await screen.findByText('Crypto pay-in and payout')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Finance & Payments sections' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual([
      'Payment Providers', 'NOWPayments Configuration', 'SoncoPay Configuration', 'Crypto Cashout Settings', 'USD Cashout Settings',
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
      changes: { crypto_min_usd: '2.50' }, current_password: PASSWORD, confirmation: undefined, expected_version: 3 }))

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
      confirmation: 'PROVIDER FEE BEHAVIOUR VERIFIED', expected_version: 3 }))

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
    expect(card).toHaveTextContent('restoring the settings above does not lift it, and neither does recording a fee')
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

  it('says whether the administrator may activate financial operations', async () => {
    setup({ s: settings({ activation: ACTIVATION() }) })
    const { unmount } = render(<AdminFinance section="providers" />)
    expect(await screen.findByTestId('activation-status')).toHaveTextContent('may activate financial operations')
    unmount()
    setup({ o: overview(MANAGE_ONLY), s: settings({ activation: ACTIVATION() }) })
    render(<AdminFinance section="providers" />)
    const status = await screen.findByTestId('activation-status')
    expect(status).toHaveTextContent('cannot activate financial operations')
    expect(status).toHaveTextContent('activate_financial_operations')
    expect(status).toHaveTextContent('Switching any of them off does not')
  })

  it('keeps ordinary configuration open and the activation controls closed for a manage-only administrator', async () => {
    setup({ o: overview(MANAGE_ONLY), s: settings({ activation: ACTIVATION(), crypto_sections: SECTIONS }),
      status: payoutStatus() })
    render(<AdminFinance section="crypto-cashout" />)
    // Activation-only controls: disabled, each with the reason.
    expect(await screen.findByRole('switch', { name: 'Automatic payouts' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'Network fee limits approved' })).toBeDisabled()
    expect(screen.getByTestId('activation-lock-crypto_auto_payout_enabled')).toHaveTextContent('activate_financial_operations')
    expect(screen.getByTestId('activation-lock-fee_terms_approved')).toHaveTextContent('which your account does not have')
    // The provider fee behaviour: only the confirming value is unavailable.
    const mode = screen.getByLabelText('Provider fee behaviour') as HTMLSelectElement
    expect(mode).not.toBeDisabled()
    expect(within(mode).getByRole('option', { name: /Deducted by provider/ })).toBeDisabled()
    expect(screen.getByTestId('activation-lock-provider_fee_mode')).toHaveTextContent('activate_financial_operations')
    // Ordinary settings stay editable and can be saved.
    const cap = screen.getByLabelText('Member network fee limit (amount)')
    expect(cap).not.toBeDisabled()
    expect(screen.getByLabelText('Minimum crypto cashout')).not.toBeDisabled()               // payouts are off
    fireEvent.change(cap, { target: { value: '0.75' } })
    const card = cap.closest('.space-y-4') as HTMLElement
    fireEvent.change(within(card).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(within(card).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { member_fee_cap_usd: '0.75' }, current_password: PASSWORD, confirmation: undefined, expected_version: 3 }))
  })

  it('lets a manage-only administrator switch things off but not back on', async () => {
    const fields = settings().fields.map((f) => ['usd_settlement_enabled'].includes(f.name) ? { ...f, value: true } : f)
    setup({ o: overview(MANAGE_ONLY), s: settings({ fields, activation: ACTIVATION() }) })
    render(<AdminFinance section="usd-cashout" />)
    const toggle = await screen.findByRole('switch', { name: 'USD settlement' })
    expect(toggle).not.toBeDisabled()                                                       // it is on: off is allowed
    expect(screen.queryByTestId('activation-lock-usd_settlement_enabled')).toBeNull()
    fireEvent.click(toggle)
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    expect(screen.queryByTestId('usd-needs-activation')).toBeNull()
    expect(screen.queryByLabelText(/to confirm/)).toBeNull()                                 // no phrase to switch off
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { usd_settlement_enabled: false }, current_password: PASSWORD, confirmation: undefined, expected_version: 3 }))
  })

  it('closes the payout settings and credentials to a manage-only administrator while automatic payouts are on', async () => {
    const fields = settings().fields.map((f) => f.name === 'crypto_auto_payout_enabled' ? { ...f, value: true }
      : f.name === 'provider_enabled' ? { ...f, value: false } : f)
    setup({ o: overview(MANAGE_ONLY), s: settings({ fields, activation: ACTIVATION(true), crypto_sections: SECTIONS }),
      status: payoutStatus() })
    const { unmount } = render(<AdminFinance section="crypto-cashout" />)
    expect(await screen.findByLabelText('Minimum crypto cashout')).toBeDisabled()
    expect(screen.getByTestId('activation-lock-crypto_min_usd')).toHaveTextContent('Automatic payouts are on')
    expect(screen.getByRole('switch', { name: 'Automatic payouts' })).not.toBeDisabled()     // stopping stays possible
    expect(screen.getByLabelText('Member network fee limit (amount)')).not.toBeDisabled()    // a fee setting stops payouts
    unmount()

    render(<AdminFinance section="nowpayments" />)
    expect(await screen.findByLabelText('Payout credential source')).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'Provider enabled' })).toBeDisabled()          // off: resuming is an activation
    expect(screen.getByLabelText('Payout API key')).toBeDisabled()
    expect(screen.getByLabelText('Payout login password')).toBeDisabled()
    expect(screen.getByTestId('activation-lock-PAYOUT_API_KEY')).toHaveTextContent('activate_financial_operations')
    expect(screen.queryByRole('button', { name: /Delete stored payout api key/i })).toBeNull()
    expect(screen.getByLabelText('Pay-in API key')).not.toBeDisabled()                       // not what payouts are sent with
    expect(screen.getByRole('button', { name: 'Run connection test' })).not.toBeDisabled()
  })

  it('asks for the phrase before switching the provider back on while automatic payouts are on', async () => {
    const fields = settings().fields.map((f) => f.name === 'crypto_auto_payout_enabled' ? { ...f, value: true }
      : f.name === 'provider_enabled' ? { ...f, value: false } : f)
    setup({ s: settings({ fields, activation: ACTIVATION(true), crypto_sections: SECTIONS,
      confirmations: { ...settings().confirmations, provider_enabled: 'RESUME NOWPAYMENTS PAYOUTS' } }) })
    putMock.mockResolvedValue({ status: 200, data: {} })
    render(<AdminFinance section="nowpayments" />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Provider enabled' }))
    // The provider settings form (the page has other forms with their own password field).
    fireEvent.change(document.getElementById('provider-password') as HTMLElement, { target: { value: PASSWORD } })
    const phrase = document.getElementById('provider-confirmation') as HTMLElement
    expect(phrase).not.toBeNull()
    const save = within(phrase.closest('.space-y-4') as HTMLElement).getByRole('button', { name: 'Save changes' })
    expect(save).toBeDisabled()
    fireEvent.change(phrase, { target: { value: 'resume' } })
    expect(save).toBeDisabled()
    fireEvent.change(phrase, { target: { value: 'RESUME NOWPAYMENTS PAYOUTS' } })
    fireEvent.click(save)
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { provider_enabled: true }, current_password: PASSWORD, confirmation: 'RESUME NOWPAYMENTS PAYOUTS',
      expected_version: 3 }))
  })

  it('offers no reactivation to a manage-only administrator and says why', async () => {
    setup({ o: overview(MANAGE_ONLY), s: settings({ activation: ACTIVATION(),
      payout_suspension: { reason: 'PROVIDER_FEE_MODE_MISMATCH', cashout_id: 12, since: '2026-10-11T09:00:00',
        rules_gate: null, message: 'The provider charged a network fee to the MyHigh5 balance.' },
      confirmations: { payout_reactivation: 'REACTIVATE CRYPTO PAYOUTS' } }) })
    render(<AdminFinance section="crypto-cashout" />)
    const card = await screen.findByTestId('payout-suspension')
    expect(within(card).getByTestId('reactivation-needs-activation')).toHaveTextContent('activate_financial_operations')
    expect(within(card).queryByRole('button', { name: 'Reactivate crypto payouts' })).toBeNull()
    expect(postMock).not.toHaveBeenCalled()
  })

  it('shows the server refusal when an activation is attempted without the permission', async () => {
    // An older page, or rules the page was not told about: the server still refuses, and its message is shown.
    setup({ o: overview(MANAGE_ONLY) })
    putMock.mockResolvedValue({ status: 403, data: { detail: { code: 'ACTIVATION_PERMISSION_REQUIRED',
      field: 'usd_settlement_enabled', message: 'The activate_financial_operations permission is required, in addition '
        + 'to manage_payment_settings, to switch USD settlement on. Nothing was changed.' } } })
    render(<AdminFinance section="usd-cashout" />)
    fireEvent.click(await screen.findByRole('switch', { name: 'USD settlement' }))
    fireEvent.change(screen.getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'ENABLE USD SETTLEMENT' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(/activate_financial_operations permission is required/)).toHaveAttribute('role', 'alert')
  })
})

describe('AdminFinance: payout credential source', () => {
  beforeEach(() => vi.clearAllMocks())

  // A real server answers every reload with new objects; the shared fixtures would hide a reset of the form.
  const freshReloads = () => {
    const served = getMock.getMockImplementation()!
    getMock.mockImplementation(async (url: string, options?: any) => {
      const res = await served(url, options)
      return { ...res, data: JSON.parse(JSON.stringify(res.data)) }
    })
  }
  const providerCard = () => screen.getByRole('heading', { name: 'Provider settings' }).closest('div') as HTMLElement

  it('keeps an unsaved credential source when credentials are stored in the card below', async () => {
    setup()
    freshReloads()
    render(<AdminFinance section="nowpayments" />)
    const source = await screen.findByLabelText('Payout credential source') as HTMLSelectElement
    fireEvent.change(source, { target: { value: 'DATABASE' } })

    fireEvent.change(screen.getByLabelText('Payout login password'), { target: { value: SECRET } })
    const passwords = screen.getAllByLabelText('Your current password')
    fireEvent.change(passwords[passwords.length - 1], { target: { value: PASSWORD } })
    fireEvent.click(screen.getByRole('button', { name: 'Store credentials' }))
    expect(await screen.findByText(/Credentials stored encrypted/)).toBeInTheDocument()

    expect((screen.getByLabelText('Payout credential source') as HTMLSelectElement).value).toBe('DATABASE')
    expect(document.body.innerHTML).not.toContain(SECRET)
  })

  it('shows a refused switch next to the form and keeps the choice so it can be retried', async () => {
    setup()
    putMock.mockResolvedValue({ status: 409, data: { detail: { code: 'CREDENTIALS_INCOMPLETE', field: 'payout_credential_source',
      message: 'Store every payout credential before switching its source to the database. Missing or unreadable: '
        + 'Payout authenticator (TOTP) secret.' } } })
    render(<AdminFinance section="nowpayments" />)
    fireEvent.change(await screen.findByLabelText('Payout credential source'), { target: { value: 'DATABASE' } })
    fireEvent.change(within(providerCard()).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(within(providerCard()).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/settings', {
      changes: { payout_credential_source: 'DATABASE' }, current_password: PASSWORD, confirmation: undefined,
      expected_version: 3 }))
    expect(await within(providerCard()).findByTestId('provider-save-error'))
      .toHaveTextContent('Missing or unreadable: Payout authenticator (TOTP) secret.')
    expect(within(providerCard()).getByText(/Not saved/)).toBeInTheDocument()
    expect((screen.getByLabelText('Payout credential source') as HTMLSelectElement).value).toBe('DATABASE')
  })

  const credentialsCard = () => screen.getByRole('heading', { name: 'API credentials' }).closest('div') as HTMLElement

  it('shows a refused credential beside its field, keeps what was typed and sends nothing else', async () => {
    setup()
    putMock.mockResolvedValue({ status: 422, data: { detail: { code: 'INVALID_VALUE', field: 'PAYOUT_PASSWORD',
      message: 'Payout login password: the value is too short or too long.' } } })
    render(<AdminFinance section="nowpayments" />)
    // An unsaved choice in Provider settings is not part of the credentials request.
    fireEvent.change(await screen.findByLabelText('Payout credential source'), { target: { value: 'DATABASE' } })
    fireEvent.change(screen.getByLabelText('Payout API key'), { target: { value: SECRET } })
    fireEvent.change(screen.getByLabelText('Payout login password'), { target: { value: 'x' } })
    fireEvent.change(within(credentialsCard()).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(screen.getByRole('button', { name: 'Store credentials' }))

    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/credentials', {
      values: { PAYOUT_API_KEY: SECRET, PAYOUT_PASSWORD: 'x' }, current_password: PASSWORD }))
    expect(await within(credentialsCard()).findByTestId('credentials-save-error')).toHaveTextContent('Nothing was stored')
    expect(screen.getByTestId('credential-error-PAYOUT_PASSWORD')).toHaveTextContent('too short or too long')
    expect(screen.getByLabelText('Payout login password')).toHaveAttribute('aria-invalid', 'true')
    expect((screen.getByLabelText('Payout API key') as HTMLInputElement).value).toBe(SECRET)        // kept, to correct
    expect((within(credentialsCard()).getByLabelText('Your current password') as HTMLInputElement).value).toBe('')
    expect((screen.getByLabelText('Payout credential source') as HTMLSelectElement).value).toBe('DATABASE')
    expect(document.body.innerHTML).not.toContain(SECRET.slice(0, 10) + '<')                      // never rendered as text

    putMock.mockResolvedValue({ status: 200, data: {} })
    fireEvent.change(screen.getByLabelText('Payout login password'), { target: { value: 'long enough now' } })
    fireEvent.change(within(credentialsCard()).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(screen.getByRole('button', { name: 'Store credentials' }))
    expect(await screen.findByText(/Credentials stored encrypted/)).toBeInTheDocument()
    expect(screen.queryByTestId('credentials-save-error')).toBeNull()
    expect((screen.getByLabelText('Payout API key') as HTMLInputElement).value).toBe('')            // cleared once stored
    expect((screen.getByLabelText('Payout login password') as HTMLInputElement).value).toBe('')
  })

  it('sends exactly the four payout fields that were typed and then shows them stored', async () => {
    const payout = [['PAYOUT_API_KEY', 'Payout API key'], ['PAYOUT_EMAIL', 'Payout login email'],
      ['PAYOUT_PASSWORD', 'Payout login password'], ['PAYOUT_TOTP_SECRET', 'Payout authenticator (TOTP) secret']]
    const all = (stored: string) => [credential('PAYIN_API_KEY', 'Pay-in API key', 'payin', 'NOT CONFIGURED'),
      credential('IPN_SECRET', 'IPN secret', 'payin', 'NOT CONFIGURED'),
      ...payout.map(([n, l]) => credential(n, l, 'payout', stored))]
    let stored = false
    setup({ p: provider({ credentials: all('NOT CONFIGURED') }) })
    const served = getMock.getMockImplementation()!
    getMock.mockImplementation(async (url: string, options?: any) => url.endsWith('/finance/provider') && stored
      ? { status: 200, data: provider({ credentials: all('CONFIGURED') }) } : served(url, options))
    putMock.mockImplementation(async () => { stored = true; return { status: 200, data: {} } })
    render(<AdminFinance section="nowpayments" />)

    const typed: Record<string, string> = { PAYOUT_API_KEY: 'SYNTHETIC-KEY-0001', PAYOUT_EMAIL: 'treasury@example.com',
      PAYOUT_PASSWORD: 'synthetic pass 0002', PAYOUT_TOTP_SECRET: 'JBSWY3DPEHPK3PXP' }
    for (const [name, label] of payout) fireEvent.change(await screen.findByLabelText(label), { target: { value: typed[name] } })
    expect(screen.getByLabelText('Payout login email')).toHaveAttribute('type', 'email')       // visible while typed
    for (const label of ['Payout API key', 'Payout login password', 'Payout authenticator (TOTP) secret', 'Pay-in API key', 'IPN secret']) {
      expect(screen.getByLabelText(label)).toHaveAttribute('type', 'password')
      expect(screen.getByLabelText(label)).toHaveAttribute('data-1p-ignore', 'true')         // no password-manager fill
    }
    expect(screen.getByTestId('credentials-to-store')).toHaveTextContent(
      'Will be stored: Payout API key, Payout login email, Payout login password, Payout authenticator (TOTP) secret.')
    const store = screen.getByRole('button', { name: 'Store credentials' })
    expect(store).toBeDisabled()                                                              // no admin password yet
    fireEvent.change(within(credentialsCard()).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(store)

    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/finance/credentials',
      { values: typed, current_password: PASSWORD }))                                        // pay-in fields not sent
    expect(await screen.findByText(/Credentials stored encrypted/)).toBeInTheDocument()
    for (const [name] of payout) {
      await waitFor(() => expect(screen.getByTestId(`credential-status-${name}`)).toHaveTextContent('Stored: Configured'))
    }
    expect(screen.getByTestId('credential-status-PAYIN_API_KEY')).toHaveTextContent('Stored: Not configured')
    for (const value of Object.values(typed)) expect(document.body.innerHTML).not.toContain(value)
  })

  it('reloads the saved source from the server after a successful save', async () => {
    setup()
    let saved = false
    const served = getMock.getMockImplementation()!
    getMock.mockImplementation(async (url: string, options?: any) => {
      if (saved && url.endsWith('/finance/settings')) {
        const s = settings({ version: 4 })
        s.fields = s.fields.map((f: SettingField) => f.name === 'payout_credential_source' ? { ...f, value: 'DATABASE' } : f)
        return { status: 200, data: s }
      }
      return served(url, options)
    })
    putMock.mockImplementation(async () => { saved = true; return { status: 200, data: {} } })
    render(<AdminFinance section="nowpayments" />)
    fireEvent.change(await screen.findByLabelText('Payout credential source'), { target: { value: 'DATABASE' } })
    fireEvent.change(within(providerCard()).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(within(providerCard()).getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(/Provider settings saved/)).toBeInTheDocument()
    expect((screen.getByLabelText('Payout credential source') as HTMLSelectElement).value).toBe('DATABASE')
    expect(within(providerCard()).getByRole('button', { name: 'Save changes' })).toBeDisabled()   // nothing left to save
  })
})
