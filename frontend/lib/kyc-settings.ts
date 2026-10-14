/**
 * Kaluta KYC settings in the Admin Panel (Admin > KYC).
 *
 * The API key and the webhook secret are WRITE-ONLY: the server never sends a
 * saved value back, only whether one is saved, readable and in use. A blank
 * field keeps what is saved. The server authorizes every change
 * (manage_kyc_settings + the administrator's current password).
 */

export const KYC_ADMIN_SETTINGS_URL = '/api/v1/kyc/admin/settings'
export const kycGrantSessionUrl = (verificationId: number) =>
  `/api/v1/kyc/admin/verification/${verificationId}/grant-session`

export type KycCredentialStatus = {
  name: 'API_KEY' | 'WEBHOOK_SECRET' | string
  label: string
  saved: boolean
  saved_readable: boolean | null
  saved_at: string | null
  environment_configured: boolean
  in_use: 'admin_panel' | 'environment' | null
  configured: boolean
}

export type KycAdminSettingsView = {
  provider: string
  enabled: boolean
  enabled_source: 'admin_panel' | 'environment'
  credentials: KycCredentialStatus[]
  ready_to_enable: boolean
  webhook_url: string | null
  redirect_url: string | null
  encryption_key_configured: boolean
  sessions_per_attempt: number
  version: number
  can_change: boolean
  permission: string
  last_change: { at: string | null; by_user_id: number | null; changed: string[] } | null
}

/** What the Admin Panel says about one key or secret. Never its value. */
export function describeCredential(c: KycCredentialStatus): string {
  if (c.saved && c.saved_readable === false) return 'Saved, but cannot be read on this server (check the encryption key)'
  if (c.in_use === 'admin_panel') return 'Saved in the Admin Panel (in use)'
  if (c.in_use === 'environment') return 'From the server environment (in use)'
  return 'Not configured'
}

export type KycSettingsDraft = { enabled: boolean; apiKey: string; webhookSecret: string }

/**
 * The request body for a save: only what changes. A blank secret is not sent
 * (the saved one is kept); null when there is nothing to save.
 */
export function settingsChanges(view: KycAdminSettingsView, draft: KycSettingsDraft):
  { enabled?: boolean; api_key?: string; webhook_secret?: string } | null {
  const out: { enabled?: boolean; api_key?: string; webhook_secret?: string } = {}
  if (draft.enabled !== view.enabled) out.enabled = draft.enabled
  if (draft.apiKey.trim()) out.api_key = draft.apiKey.trim()
  if (draft.webhookSecret.trim()) out.webhook_secret = draft.webhookSecret.trim()
  return Object.keys(out).length ? out : null
}

/** A value that is obviously the webhook URL pasted where the secret belongs. */
export function looksLikeUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim())
}
