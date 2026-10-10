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
}

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
  permissions: { can_manage: boolean; can_process: boolean }
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

/** Credential fields are write-only: a blank field is not sent, so it keeps the stored value. */
export function credentialPayload(draft: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(draft).filter(([, value]) => value.trim() !== ''))
}
