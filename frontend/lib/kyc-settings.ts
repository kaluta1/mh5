/**
 * Kaluta KYC settings in the Admin Panel (Admin > KYC).
 *
 * The database is their ONLY source: the server environment is not used. One
 * form saves the on/off switch, the API key, the webhook secret, the member
 * fee and the sessions per attempt.
 *
 * The API key and the webhook secret are WRITE-ONLY: the server never sends a
 * saved value back, only whether one is configured. A blank field keeps what
 * is saved. The server authorizes every change (manage_kyc_settings or a
 * Super Admin, plus the administrator's current password) and validates every
 * value again.
 */
import { parseKycFeeInput } from './kyc-fee'

export const KYC_ADMIN_SETTINGS_URL = '/api/v1/kyc/admin/settings'
export const kycGrantSessionUrl = (verificationId: number) =>
  `/api/v1/kyc/admin/verification/${verificationId}/grant-session`

export type KycCredentialStatus = {
  name: 'API_KEY' | 'WEBHOOK_SECRET' | string
  label: string
  /** Saved AND readable on this server: the value in force. */
  configured: boolean
  saved: boolean
  saved_readable: boolean | null
  saved_at: string | null
}

export type KycAdminSettingsView = {
  source: 'database'
  provider: string
  enabled: boolean
  credentials: KycCredentialStatus[]
  ready_to_enable: boolean
  webhook_url: string | null
  redirect_url: string | null
  encryption_key_configured: boolean
  member_fee: {
    amount: string
    currency: string
    is_free: boolean
    max_amount: string
    product_configured: boolean
    last_change: { at: string | null; by_user_id: number | null; old_amount: string | null; new_amount: string | null } | null
  }
  sessions_per_attempt: number
  sessions_per_attempt_min: number
  sessions_per_attempt_max: number
  sessions_per_attempt_default: number
  version: number
  can_change: boolean
  permission: string
  last_change: { at: string | null; by_user_id: number | null; changed: string[] } | null
}

/** What the Admin Panel says about one key or secret. Never its value. */
export function describeCredential(c: KycCredentialStatus): string {
  if (c.saved && c.saved_readable === false) return 'Saved, but cannot be read on this server (check the encryption key)'
  return c.configured ? 'Configured' : 'Not configured'
}

export type KycSettingsDraft = {
  enabled: boolean
  apiKey: string
  webhookSecret: string
  fee: string
  sessions: string
}

export type KycSettingsBody = {
  enabled?: boolean
  api_key?: string
  webhook_secret?: string
  member_fee?: string
  sessions_per_attempt?: number
}

/** The form's starting values: what is saved, with the secret fields empty. */
export function draftFrom(view: KycAdminSettingsView): KycSettingsDraft {
  return {
    enabled: view.enabled,
    apiKey: '',
    webhookSecret: '',
    fee: view.member_fee.amount,
    sessions: String(view.sessions_per_attempt),
  }
}

/** Sessions per attempt as typed: a whole number within the server's range, else null. */
export function parseSessionsInput(value: string, min = 1, max = 10): number | null {
  const text = value.trim()
  if (!/^\d{1,3}$/.test(text)) return null
  const number = Number(text)
  return number >= min && number <= max ? number : null
}

/** What is wrong with the draft, field by field (empty when it can be sent). */
export function draftProblems(view: KycAdminSettingsView, draft: KycSettingsDraft): Partial<Record<keyof KycSettingsDraft, string>> {
  const out: Partial<Record<keyof KycSettingsDraft, string>> = {}
  if (looksLikeUrl(draft.apiKey)) out.apiKey = 'That looks like a URL. Paste the API key.'
  if (looksLikeUrl(draft.webhookSecret)) out.webhookSecret = 'That looks like a URL. Paste the signing secret, not the webhook URL.'
  if (/\s/.test(draft.apiKey.trim())) out.apiKey = 'The API key has no spaces.'
  if (/\s/.test(draft.webhookSecret.trim())) out.webhookSecret = 'The webhook secret has no spaces.'
  if (parseKycFeeInput(draft.fee, Number(view.member_fee.max_amount)) === null) {
    out.fee = `Enter an amount from 0 to ${view.member_fee.max_amount}, with at most two decimals.`
  }
  if (parseSessionsInput(draft.sessions, view.sessions_per_attempt_min, view.sessions_per_attempt_max) === null) {
    out.sessions = `Enter a whole number from ${view.sessions_per_attempt_min} to ${view.sessions_per_attempt_max}.`
  }
  return out
}

/**
 * The request body for a save: only what changes. A blank secret is not sent
 * (the saved one is kept); null when there is nothing to save or a value is
 * not valid.
 */
export function settingsChanges(view: KycAdminSettingsView, draft: KycSettingsDraft): KycSettingsBody | null {
  if (Object.keys(draftProblems(view, draft)).length) return null
  const out: KycSettingsBody = {}
  if (draft.enabled !== view.enabled) out.enabled = draft.enabled
  if (draft.apiKey.trim()) out.api_key = draft.apiKey.trim()
  if (draft.webhookSecret.trim()) out.webhook_secret = draft.webhookSecret.trim()
  const fee = parseKycFeeInput(draft.fee, Number(view.member_fee.max_amount))
  if (fee !== null && fee !== view.member_fee.amount) out.member_fee = fee
  const sessions = parseSessionsInput(draft.sessions, view.sessions_per_attempt_min, view.sessions_per_attempt_max)
  if (sessions !== null && sessions !== view.sessions_per_attempt) out.sessions_per_attempt = sessions
  return Object.keys(out).length ? out : null
}

/** A value that is obviously the webhook URL pasted where the secret belongs. */
export function looksLikeUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim())
}

const CHANGE_LABELS: Record<string, string> = {
  KALUTA_ENABLED: 'Kaluta KYC on/off',
  API_KEY: 'API key',
  WEBHOOK_SECRET: 'webhook secret',
  MEMBER_FEE: 'KYC fee',
  SESSIONS_PER_ATTEMPT: 'sessions per attempt',
}

/** "API key, KYC fee" for a success message. */
export function describeChanges(changed: string[] | undefined | null): string {
  return (changed || []).map((name) => CHANGE_LABELS[name] || name).join(', ')
}
