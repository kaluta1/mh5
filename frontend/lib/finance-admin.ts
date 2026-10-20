// Admin > Finance & Payments: types and wording.
// The backend decides and validates everything (/api/v1/admin/finance and
// /api/v1/admin/cashouts). Nothing here holds a secret: a credential is only
// ever reported as CONFIGURED / NOT CONFIGURED, and credential fields are
// write-only.

export const FINANCE_BASE = '/api/v1/admin/finance'
export const CASHOUTS_BASE = '/api/v1/admin/cashouts'

export const FINANCE_SECTIONS = [
  { slug: 'providers', label: 'Payment Providers' },
  { slug: 'nowpayments', label: 'NOWPayments Configuration' },
  { slug: 'soncopay', label: 'SoncoPay Configuration' },
  { slug: 'crypto-cashout', label: 'Crypto Cashout Settings' },
  { slug: 'usd-cashout', label: 'USD Cashout Settings' },
  { slug: 'payout-security', label: 'Payout Security' },
  { slug: 'transactions', label: 'Cashout Transactions' },
  { slug: 'reconciliation', label: 'Reconciliation & Audit Logs' },
] as const
export type FinanceSection = (typeof FINANCE_SECTIONS)[number]['slug']

export function isFinanceSection(value: string | undefined): value is FinanceSection {
  return FINANCE_SECTIONS.some((s) => s.slug === value)
}

export type SettingField = {
  name: string
  group: 'provider' | 'crypto' | 'security' | 'usd'
  kind: 'bool' | 'int' | 'money' | 'percent' | 'choice' | 'text' | 'account'
  label: string
  help: string
  value: string | number | boolean | null
  default: string | number | boolean | null
  minimum: string | null
  maximum: string | null
  choices: string[]
  unit: string
  max_length: number | null
  approval_note: string | null
  /** Choices that exist as stored values but can no longer be selected, with the reason. */
  disabled_choices?: { value: string; reason: string }[]
  /** A number that may be left empty (= not set). */
  optional?: boolean
}

/** One group of settings on the Crypto Cashout page (decided by the server). */
export type CryptoSection = { key: string; title: string; note: string; fields: string[] }

export type FinanceSettings = {
  version: number
  persisted: boolean
  updated_at: string | null
  fields: SettingField[]
  server_switches: {
    crypto_auto_payout: boolean
    usd_settlement: boolean
    environment: 'sandbox' | 'production'
    encryption_key_configured: boolean
  }
  effective: { automatic_crypto_payouts: boolean; usd_settlement: boolean }
  usd_fee_rule: string
  supported_payout_currencies: { code: string; currency: string; network: string }[]
  confirmations: Record<string, string>
  /** Why no crypto payout can be created (null = one can). */
  network_fee_gate?: { code: string; message: string } | null
  /** Set by the engine when a payout did not add up; lifted only by an explicit reactivation. */
  payout_suspension?: PayoutSuspension | null
  crypto_sections?: CryptoSection[]
  /** Which changes also need the activation permission. Absent from an older server. */
  activation?: ActivationRules | null
}

/**
 * Configuring and activating are two authorities. A change listed here needs
 * the activation permission in addition to manage_payment_settings. The server
 * decides and refuses; this only lets the page say so before the attempt.
 */
export type ActivationRules = {
  permission: string
  /** setting -> the value that activates */
  values: Record<string, string | boolean>
  automatic_payouts_on: boolean
  while_automatic_payouts_on: { fields: string[]; switches: string[]; credential_group: string }
}

/**
 * Everything that currently stops a crypto payout from being created, each
 * with what an administrator has to do about it. Built by the server from the
 * same rules the payout engine applies; this page only displays it.
 */
export type CryptoPayoutStatus = {
  can_create_payouts: boolean
  configuration_version: number
  blockers: { code: string; section: string; message: string; action: string; temporary: boolean }[]
  missing_settings: { field: string; label: string; section: string }[]
  provider_semantics: {
    fee_mode: string
    fee_mode_confirmed: boolean
    receiver_fee_values_confirmed: boolean
    company_fee_values_confirmed: boolean
    amount_meaning: string | null
    automatic_verification: boolean
  }
  approval: { approved: boolean; can_approve: boolean; blocked_by: { code: string; message: string } | null }
  suspension: PayoutSuspension | null
  recording_gate: { limit: number; in_flight: number; completed_unreconciled: number; total: number; blocked: boolean }
  flagged_payouts: { pending_review: number }
  switches: { server: boolean; provider: boolean; crypto_cashout: boolean; automatic_payouts: boolean; credentials_ready: boolean }
}

/** The settings of one section, in the server's order. Unknown names are skipped. */
export function sectionFields(fields: SettingField[], section: CryptoSection): SettingField[] {
  return section.fields.map((name) => fields.find((f) => f.name === name)).filter((f): f is SettingField => !!f)
}

export type CredentialStatus = {
  name: string
  label: string
  group: 'payin' | 'payout'
  source: 'ENVIRONMENT' | 'DATABASE'
  stored: 'CONFIGURED' | 'NOT CONFIGURED'
  stored_readable: boolean | null
  stored_updated_at: string | null
  environment: 'CONFIGURED' | 'NOT CONFIGURED'
  in_use: 'CONFIGURED' | 'NOT CONFIGURED'
}

export type ConnectionResult = {
  status: string
  message: string
  tested_at: string | null
  last_success_at: string | null
  checks: { name: string; status: string; message: string }[]
  facts: Record<string, string>
  payout_login: string
}

/** One vocabulary for every provider capability (set by the server). */
export type ReadinessState = 'DISABLED' | 'UNVERIFIED' | 'CONFIGURED' | 'BLOCKED' | 'VERIFIED'

export type ProviderReadiness = {
  states: ReadinessState[]
  items: { key: string; label: string; state: ReadinessState; detail: string }[]
  outstanding: string[]
  last_test_at: string | null
  last_success_at: string | null
  last_error: { check: string; code: string; message: string; at: string | null } | null
}

export type ProviderView = {
  provider: string
  display_name: string
  enabled: boolean
  environment: 'sandbox' | 'production'
  payin_status: string
  payout_status: string
  custody_status: string
  payout_currency: string
  payout_network: string
  credential_sources: { payin: string; payout: string }
  credentials: CredentialStatus[]
  encryption_key_configured: boolean
  connection: ConnectionResult
  readiness?: ProviderReadiness
  last_configuration_update: string | null
  configuration_version: number
}

export type FinanceOverview = {
  /** can_activate is true only with BOTH manage_payment_settings and the activation permission. */
  permissions: { can_manage: boolean; can_process: boolean; can_activate?: boolean }
  providers: {
    key: string
    name: string
    role: string
    enabled: boolean
    environment: string | null
    payin_status: string | null
    payout_status: string | null
    custody_status: string | null
    connection_status: string | null
  }[]
  server_switches: FinanceSettings['server_switches']
  effective: FinanceSettings['effective']
  engine: { enabled: boolean; missing: string[]; credential_source: string }
  webhook_status: string
  configuration_version: number
  warnings: { code: string; level: 'critical' | 'warning'; message: string }[]
}

export type WebhookHealth = {
  callback_url: string
  callback_url_secure: boolean
  status: string
  last_7_days: Record<string, number>
  last_accepted_at: string | null
  last_verified_signature_at?: string | null
  last_signature_rejection_at: string | null
  payout_notices_7_days?: number
  signature_verification: string
}

export type AdminCashout = {
  id: number
  user_id: number
  username?: string | null
  method: 'CRYPTO' | 'USD'
  status: 'requested' | 'processing' | 'unknown' | 'completed' | 'failed' | 'cancelled'
  gross_amount: number
  fee: number
  net_amount: number
  network_fee: number | null
  network_fee_policy: string | null
  destination: string | null
  payout_currency: string | null
  reference: string | null
  requested_at: string | null
  processed_at: string | null
  provider_status: string | null
  provider_batch_id: string | null
  failure_code: string | null
  reviewed_by: number | null
  has_destination_details: boolean
  beneficiary_fee?: BeneficiaryFeeRecord
  fee_review?: FeeReview
}

/** An administrator's review of a flagged payout. A record only: it changes nothing else. */
export type FeeReview = {
  state: 'NOT_REQUIRED' | 'PENDING' | 'REVIEWED'
  flag: string | null
  message: string | null
  reviewed_flag: string | null
  reviewed_by: number | null
  reviewed_at: string | null
  note: string | null
  /** An earlier review exists, but the payout has been flagged for something else since. */
  superseded: boolean
}

/** One flagged payout: what was expected, what happened, the evidence and its review. Exact figures, as text. */
export type FeeException = {
  cashout_id: number
  user_id: number
  username: string | null
  status: string
  processed_at: string | null
  payout_currency: string | null
  destination: string | null
  provider_batch_id: string | null
  provider_status: string | null
  flag: string
  flag_message: string
  flag_details: Record<string, string | null>
  caused_suspension: boolean
  gross: string
  provider_fee_mode: string | null
  expected: {
    amount_sent: string | null; network_fee_estimate: string | null; network_fee_estimate_adjusted: string | null
    fee_cap: string | null; received: string | null
  }
  actual: {
    network_fee: string | null; received: string | null; fee_above_estimate: string | null
    fee_above_cap: string | null; received_difference: string | null
  }
  evidence: { source: string | null; evidence: string | null; reconciliation: string | null; reconciled: boolean; recorded: boolean }
  review: FeeReview
}

export type FeeExceptionList = {
  total: number
  flagged_count: number
  pending_count: number
  reviewed_count: number
  payout_suspension: PayoutSuspension | null
  items: FeeException[]
}

export type FeeEvent = {
  id: number; action: string; actor_id: number | null; created_at: string | null
  old_values: Record<string, unknown>; new_values: Record<string, unknown>
}

export const REVIEW_NOTE_MIN = 20
export const REVIEW_NOTE_MAX = 500

/** A review note that says something: long enough, and not one character repeated. The server decides. */
export function validReviewNote(text: string): boolean {
  const note = text.trim().split(/s+/).join(' ')
  if (note.length < REVIEW_NOTE_MIN || note.length > REVIEW_NOTE_MAX) return false
  return new Set(note.toLowerCase().replace(/ /g, '')).size >= 5
}

export const FEE_EVENT_LABEL: Record<string, string> = {
  CASHOUT_RESERVED: 'Payout reserved (estimate and limit checked)',
  CASHOUT_COMPLETED: 'Payout completed',
  CASHOUT_PROVIDER_EVIDENCE: 'Provider report received',
  CASHOUT_FEE_FLAGGED: 'Flagged',
  CASHOUT_MEMBER_FEE_RECORDED: 'Actual network fee recorded',
  CASHOUT_FEE_EXCEPTION_REVIEWED: 'Reviewed by an administrator',
}

/** The network fee a beneficiary bore on one crypto payout. Exact figures, as text. */
export type BeneficiaryFeeRecord = {
  applies: boolean
  provider_fee_mode: string | null
  gross: string
  /** What was handed to the provider: the whole amount, because the provider takes its fee out of it. */
  amount_sent: string | null
  estimate: string | null
  /** The estimate raised by the safety margin: what was compared with the member's limit. Still an estimate. */
  estimate_adjusted?: string | null
  margin_percent?: string | null
  /** The provider's actual fee. Null until it is known; never an estimate. */
  actual: string | null
  /** How far the actual fee was verified. Only the two VERIFIED values count as a reconciliation. */
  reconciliation?: 'PROVIDER_VERIFIED' | 'ADMIN_VERIFIED' | 'PROVIDER_UNVERIFIED' | 'ADMIN_UNVERIFIED' | null
  evidence?: string | null
  reconciled?: boolean
  net_received: string | null
  /** The highest fee the member accepted for this payout. */
  fee_cap: string | null
  source: 'PROVIDER_REPORTED' | 'ADMIN_RECORDED' | null
  flag: string | null
  status: 'NOT_APPLICABLE' | 'NOT_RECORDED' | 'RECORDED'
}

export type BeneficiaryFeeSummary = {
  completed_count: number
  gross_total: string
  recorded_count: number
  fee_total: string
  received_total: string
  not_recorded_count: number
  not_recorded: { cashout_id: number; user_id: number; estimate: string | null }[]
  flagged: { cashout_id: number; user_id: number; flag: string; actual: string | null; fee_cap: string | null; review?: string }[]
  flagged_unreviewed_count?: number
  automatic_recording: boolean
  /** Payouts whose actual fee is not verified: still on their way, or completed without it. */
  exposure?: { in_flight: number; completed_unreconciled: number; total: number }
  verified_count?: number
  not_verified?: { cashout_id: number; user_id: number; reconciliation: string | null; actual: string | null }[]
  amount_meaning_confirmed?: boolean
}

export const FEE_FLAG_LABEL: Record<string, string> = {
  PROVIDER_FEE_MODE_MISMATCH: 'The provider charged the fee to the MyHigh5 balance, not to the payout',
  PROVIDER_AMOUNT_MISMATCH: 'The provider reports a larger amount than it was asked to send',
  FEE_CAP_EXCEEDED: 'The fee taken is above the limit the member accepted',
}

/** Where the provider took the network fee of a beneficiary-paid payout from. */
export const FEE_CHARGED_TO = [
  { value: 'PAYOUT_AMOUNT', label: 'Taken out of the payout (the member received less)' },
  { value: 'PROVIDER_BALANCE', label: 'Charged to the MyHigh5 provider balance (not expected)' },
] as const

/** Where an administrator read the figures. "Other" is recorded but can never verify a payout. */
export const FEE_EVIDENCE = [
  { value: 'PROVIDER_STATEMENT', label: "The provider's statement or dashboard for this payout", verifies: true },
  { value: 'BLOCKCHAIN_EXPLORER', label: 'A blockchain explorer (the transaction itself)', verifies: true },
  { value: 'PROVIDER_SUPPORT', label: "A written answer from the provider's support", verifies: true },
  { value: 'OTHER', label: 'Other (cannot be marked verified)', verifies: false },
] as const

export const RECONCILIATION_LABEL: Record<string, string> = {
  PROVIDER_VERIFIED: 'Verified from the provider report',
  ADMIN_VERIFIED: 'Verified by an administrator against evidence',
  PROVIDER_UNVERIFIED: 'Reported by the provider, not verified',
  ADMIN_UNVERIFIED: 'Entered by an administrator, not verified',
}

/** Why crypto payouts are suspended, and what must be resolved before they can be reactivated. */
export type PayoutSuspension = {
  reason: string
  message: string
  since: string | null
  cashout_id: number | null
  /** The network fee rule that is not in force (null = the rules are in force again). */
  rules_gate: string | null
}

/** The amount received that a verified record must state: the payout less the fee, or all of it. */
export function expectedReceived(gross: number, fee: string, chargedTo: string): string | null {
  const value = fee.trim()
  if (!/^\d+(\.\d{1,8})?$/.test(value)) return null
  // Integer arithmetic at 8 decimals: never a floating-point subtraction of money.
  const units = (text: string) => {
    const [whole, fraction = ''] = text.split('.')
    return BigInt(whole) * BigInt(100000000) + BigInt(fraction.padEnd(8, '0'))
  }
  const net = chargedTo === 'PROVIDER_BALANCE' ? units(gross.toFixed(2)) : units(gross.toFixed(2)) - units(value)
  if (net <= BigInt(0)) return null
  const text = net.toString().padStart(9, '0')
  const fraction = text.slice(-8).replace(/0+$/, '')
  return fraction ? `${text.slice(0, -8)}.${fraction}` : text.slice(0, -8)
}

/** Two amounts typed as text are the same number ("4.98" and "4.980"). */
export function sameAmount(a: string, b: string | null): boolean {
  if (b === null || !/^\d+(\.\d{1,8})?$/.test(a.trim())) return false
  const norm = (text: string) => {
    const [whole, fraction = ''] = text.trim().split('.')
    return `${BigInt(whole)}.${fraction.padEnd(8, '0')}`
  }
  return norm(a) === norm(b)
}

/** An actual fee of a beneficiary-paid payout: a plain number smaller than the payout itself. */
export function validMemberFee(text: string, gross: number): boolean {
  const value = text.trim()
  if (!/^\d+(\.\d{1,8})?$/.test(value)) return false
  return Number(value) < gross
}

/** What the books say about the network fee MyHigh5 paid for one crypto payout. */
export type NetworkFeeRecord = {
  status: 'POSTED' | 'NONE' | 'NOT_RECORDED' | 'NOT_APPLICABLE'
  amount: string | null
  source: 'PROVIDER_REPORTED' | 'ADMIN_RECORDED' | null
  reported: string | null
  estimate: string | null
}

export type NetworkFeeSummary = {
  expense_account: string
  posted_count: number
  posted_total: number
  /** Exact fees as reported, before rounding to cents, and their difference from the ledger total. */
  reported_total: string
  rounding_difference: string
  confirmed_none_count: number
  not_recorded_count: number
  not_recorded: { cashout_id: number; user_id: number; estimate: number | null }[]
  automatic_posting: boolean
}

export const NETWORK_FEE_LABEL: Record<NetworkFeeRecord['status'], string> = {
  POSTED: 'Recorded as an expense',
  NONE: 'Confirmed: no fee to record',
  NOT_RECORDED: 'Not recorded yet',
  NOT_APPLICABLE: 'Not applicable',
}

/** A fee typed by an administrator: a plain non-negative number, never larger than the payout. */
export function validNetworkFee(text: string, gross: number): boolean {
  const value = text.trim()
  if (!/^\d+(\.\d{1,8})?$/.test(value)) return false
  return Number(value) <= gross
}

export type Reconciliation = {
  owed: { pending: number; available: number; reserved: number }
  owed_total: number
  owed_to_crypto_cashout_members: number
  open_cashouts: Record<string, number>
  provider_balance_state: 'NOT_VERIFIED' | 'READ' | 'UNAVAILABLE'
  provider_balance: number | null
  provider_covers_crypto_members: boolean | null
  last_24_hours: { crypto_payout_amount: number; crypto_payout_count: number; amount_limit: number; count_limit: number }
  discrepancies: { type: string; severity: 'critical' | 'warning'; message: string; cashout_id?: number; user_id?: number }[]
  network_fees?: NetworkFeeSummary
  beneficiary_fees?: BeneficiaryFeeSummary
  /** Why no crypto payout can be created under the network fee rules (null = one can). */
  network_fee_gate?: { code: string; message: string } | null
  payout_suspension?: PayoutSuspension | null
  /** No further payout while more than `limit` are outstanding without a verified actual fee. */
  recording_gate?: { limit: number; in_flight: number; completed_unreconciled: number; total: number; blocked: boolean }
}

export const CASHOUT_STATUS_LABEL: Record<AdminCashout['status'], string> = {
  requested: 'Requested',
  processing: 'Processing',
  unknown: 'Unknown outcome - review required',
  completed: 'Completed',
  failed: 'Failed - released',
  cancelled: 'Cancelled - released',
}

const WEBHOOK_STATUS_LABEL: Record<string, string> = {
  HEALTHY: 'Healthy',
  SIGNATURE_REJECTIONS: 'Signature rejections',
  NO_CALLBACKS_RECORDED: 'No callbacks recorded yet',
  ATTENTION: 'Needs attention',
}

const CHECK_LABEL: Record<string, string> = {
  api_status: 'Provider reachable',
  payin_api_key: 'Pay-in API key',
  custody_balance: 'Custody balance (payout key)',
  payout_minimum: 'Provider payout minimum',
  payout_network_fee: 'Network fee estimate',
  payout_login: 'Payout login',
}

/**
 * VERIFIED is the only state shown as proven. CONFIGURED means the credentials
 * are present and nothing has proven that they work, so it is never green.
 */
export function readinessTone(state: string | null | undefined): 'green' | 'amber' | 'red' | 'gray' {
  const value = (state ?? '').toUpperCase()
  if (value === 'VERIFIED') return 'green'
  if (value === 'CONFIGURED') return 'amber'
  if (value === 'BLOCKED') return 'red'
  return 'gray'
}

export const webhookStatusLabel = (status: string) => WEBHOOK_STATUS_LABEL[status] ?? status
export const checkLabel = (name: string) => CHECK_LABEL[name] ?? name
export const humanize = (code: string | null | undefined) =>
  (code ?? '').replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())

export function usd(amount: number | string | null | undefined): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(amount ?? 0))
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return '-'
  // The API sends UTC timestamps without a zone suffix.
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function tone(status: string | null | undefined): 'green' | 'amber' | 'red' | 'gray' {
  const value = (status ?? '').toUpperCase()
  if (['OK', 'CONFIGURED', 'VERIFIED', 'HEALTHY', 'COMPLETED', 'READ'].includes(value)) return 'green'
  if (['PARTIAL', 'NOT_TESTED', 'NOT VERIFIED', 'NOT_VERIFIED', 'REQUESTED', 'PROCESSING', 'NO_CALLBACKS_RECORDED'].includes(value)) return 'amber'
  if (['NOT CONFIGURED', 'CANCELLED', 'NO PROVIDER CONFIGURED'].includes(value)) return 'gray'
  return 'red'
}

/** The server's reason for refusing a change, in words an administrator can act on. */
export function financeErrorText(res: { status: number; data?: any }, fallback: string): string {
  const detail = res.data?.detail
  if (detail?.message) return detail.message
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  if (res.status === 403) return 'You do not have the permission required for this action.'
  return fallback
}

/** Only the values that differ from what the server sent: a form never resubmits everything. */
export function changedValues(fields: SettingField[], draft: Record<string, string | boolean>): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {}
  for (const field of fields) {
    if (!(field.name in draft)) continue
    const next = draft[field.name]
    const current = field.kind === 'bool' ? Boolean(field.value) : String(field.value ?? '')
    if (field.kind === 'bool' ? next !== current : String(next).trim() !== current) out[field.name] = next
  }
  return out
}

/**
 * The settings in a set of changes that also need the activation permission.
 * Switching something off never does. Mirrors the server's rule; the server
 * remains the one that decides.
 */
export function activationChanges(rules: ActivationRules | null | undefined,
  changes: Record<string, string | boolean>): string[] {
  if (!rules) return []
  const out = Object.keys(changes).filter((name) => name in rules.values && changes[name] === rules.values[name])
  // Automatic payouts are on and this change does not switch them off.
  if (rules.automatic_payouts_on && changes.crypto_auto_payout_enabled !== false) {
    const live = rules.while_automatic_payouts_on
    out.push(...live.fields.filter((name) => name in changes))
    out.push(...live.switches.filter((name) => changes[name] === true))
  }
  return out
}

/**
 * Why an administrator who may configure but not activate cannot use a
 * control as it stands, or null when they can. A switch that is ON stays
 * usable: switching off is always allowed.
 */
export function activationLock(rules: ActivationRules | null | undefined, field: SettingField): string | null {
  if (!rules) return null
  const live = rules.while_automatic_payouts_on
  if (field.kind === 'bool') {
    const activates = rules.values[field.name] === true
      || (rules.automatic_payouts_on && live.switches.includes(field.name))
    if (!activates || field.value) return null
    return `Switching this on needs the ${rules.permission} permission, which your account does not have.`
  }
  if (rules.automatic_payouts_on && live.fields.includes(field.name)) {
    return `Automatic payouts are on: changing this needs the ${rules.permission} permission, which your account `
      + 'does not have. Switching automatic payouts off does not.'
  }
  return null
}

/** Credential fields are write-only: a blank field is not sent, so it keeps the stored value. */
export function credentialPayload(draft: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(draft).filter(([, value]) => value.trim() !== ''))
}
