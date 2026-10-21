/**
 * SoncoPay customer payment collection settings (Finance & Payments >
 * SoncoPay Configuration).
 *
 * The database is their ONLY source. One form saves the on/off switch, the
 * Test/Live environment, the default checkout gateway and the API key and
 * webhook signing secret of each environment.
 *
 * Keys and secrets are WRITE-ONLY: the server never sends a saved value back,
 * only whether one is configured (and an API key's last four characters). A
 * blank field keeps what is saved. The server authorizes every change (a
 * Super Admin, plus the current password) and validates every value again.
 * Only a gateway that can take new payments may become the default (the
 * server refuses otherwise, whatever this form sends). The chosen default is
 * kept when that gateway is switched off: new payments are then unavailable
 * until it is on again or another ready gateway is chosen. Nothing is ever
 * chosen automatically. Nothing here touches NOWPayments checkout or the
 * NOWPayments payout engine.
 */

export const SONCOPAY_SETTINGS_URL = '/api/v1/admin/finance/soncopay'
export const SONCOPAY_CONNECTION_TEST_URL = '/api/v1/admin/finance/soncopay/connection-test'

export type CheckoutProvider = 'nowpayments' | 'soncopay'

/** One gateway as the server sees it now. "ready" = may take a NEW member payment (and be chosen as the default). */
export type GatewayStatus = {
  provider: CheckoutProvider
  label: string
  enabled: boolean
  ready: boolean
  /** Why it cannot take new payments (null when ready). */
  reason: string | null
  environment: string
  incoming: string
  outgoing: string
}

/** What the connection test answers (GET /v1/methods on SoncoPay, no side effect). Never a key. */
export type SoncoPayConnectionTest = {
  ok: boolean
  environment: SoncoPayEnvironment
  methods?: number
  error?: string
  code?: string | null
  status_code?: number | null
}

export type SoncoPayEnvironment = 'test' | 'live'

export type SoncoPayCredentialStatus = {
  name: 'TEST_API_KEY' | 'TEST_WEBHOOK_SECRET' | 'LIVE_API_KEY' | 'LIVE_WEBHOOK_SECRET' | string
  environment: SoncoPayEnvironment
  kind: 'api_key' | 'webhook_secret'
  label: string
  /** Saved AND readable on this server. */
  configured: boolean
  saved: boolean
  saved_readable: boolean | null
  saved_at: string | null
  /** An API key's last four characters ("••••1a2b"); never anything of a secret. */
  masked: string | null
}

export type SoncoPaySettingsView = {
  provider: 'soncopay'
  source: 'database'
  enabled: boolean
  environment: SoncoPayEnvironment
  environments: SoncoPayEnvironment[]
  /** The default a Super Admin chose (kept as it is). */
  default_provider: CheckoutProvider
  /** The gateway new payments use now: the chosen default while it is ready, otherwise 'none'. */
  default_provider_in_force: CheckoutProvider | 'none'
  default_unavailable_reason: string | null
  gateways: GatewayStatus[]
  checkout_providers: { provider: string; label: string; available: boolean; note?: string | null }[]
  credentials: SoncoPayCredentialStatus[]
  ready: Record<SoncoPayEnvironment, boolean>
  webhook_url: string | null
  webhook_operational: boolean
  connection_test: { available: boolean; reason: string | null }
  live_confirmation: string
  encryption_key_configured: boolean
  version: number
  can_change: boolean
  last_change: { at: string | null; by_user_id: number | null; changed: string[] } | null
}

export type SoncoPayDraft = {
  enabled: boolean
  environment: SoncoPayEnvironment
  defaultProvider: CheckoutProvider
  testApiKey: string
  testWebhookSecret: string
  liveApiKey: string
  liveWebhookSecret: string
  confirmation: string
}

export type SoncoPaySettingsBody = {
  enabled?: boolean
  environment?: SoncoPayEnvironment
  default_provider?: CheckoutProvider
  test_api_key?: string
  test_webhook_secret?: string
  live_api_key?: string
  live_webhook_secret?: string
  confirmation?: string
}

const SECRET_FIELDS = [
  ['testApiKey', 'test_api_key', 'API key'],
  ['testWebhookSecret', 'test_webhook_secret', 'webhook signing secret'],
  ['liveApiKey', 'live_api_key', 'API key'],
  ['liveWebhookSecret', 'live_webhook_secret', 'webhook signing secret'],
] as const

/** A Test key starts with sp_test_, a Live key with sp_live_ (the server checks it again). */
const KEY_PREFIX = { testApiKey: 'sp_test_', liveApiKey: 'sp_live_' } as const

/** What the Admin Panel says about one key or secret. Never its value. */
export function describeCredential(c: SoncoPayCredentialStatus): string {
  if (c.saved && c.saved_readable === false) return 'Saved, but cannot be read on this server (check the encryption key)'
  if (!c.configured) return 'Not configured'
  return c.masked ? `Configured (${c.masked})` : 'Configured'
}

/** The form's starting values: what is saved, with every secret field empty. */
export function draftFrom(view: SoncoPaySettingsView): SoncoPayDraft {
  return {
    enabled: view.enabled,
    environment: view.environment,
    defaultProvider: view.default_provider,
    testApiKey: '',
    testWebhookSecret: '',
    liveApiKey: '',
    liveWebhookSecret: '',
    confirmation: '',
  }
}

/** A value that is obviously a URL pasted where a key or secret belongs. */
export function looksLikeUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim())
}

/** What is wrong with the draft, field by field (empty when it can be sent). */
export function draftProblems(view: SoncoPaySettingsView, draft: SoncoPayDraft): Partial<Record<keyof SoncoPayDraft, string>> {
  const out: Partial<Record<keyof SoncoPayDraft, string>> = {}
  for (const [field, , what] of SECRET_FIELDS) {
    const value = draft[field].trim()
    if (!value) continue
    if (looksLikeUrl(value)) out[field] = `That looks like a URL. Paste the ${what}.`
    else if (/\s/.test(value)) out[field] = `The ${what} has no spaces.`
    else if (value.length < 16) out[field] = `The ${what} is too short.`
    else if (field in KEY_PREFIX && !value.startsWith(KEY_PREFIX[field as keyof typeof KEY_PREFIX])) {
      out[field] = `This ${what} starts with ${KEY_PREFIX[field as keyof typeof KEY_PREFIX]}.`
    }
  }
  if (draft.defaultProvider === 'nowpayments' && view.default_provider !== 'nowpayments') {
    const nowpayments = view.checkout_providers.find((p) => p.provider === 'nowpayments')
    if (!nowpayments?.available) {
      out.defaultProvider = `NOWPayments cannot take new payments${nowpayments?.note ? `: ${nowpayments.note}` : '.'}`
    }
  }
  if (draft.defaultProvider === 'soncopay' && view.default_provider !== 'soncopay') {
    const soncopay = view.checkout_providers.find((p) => p.provider === 'soncopay')
    if (!soncopay?.available) out.defaultProvider = 'SoncoPay checkout is not available.'
    else if (!draft.enabled) out.defaultProvider = 'Switch SoncoPay on first.'
    else if (!view.ready[draft.environment]) {
      out.defaultProvider = `Save the ${draft.environment === 'live' ? 'Live' : 'Test'} API key and signing secret first.`
    }
  }
  if (draft.environment === 'live' && view.environment !== 'live' && draft.confirmation.trim() !== view.live_confirmation) {
    out.confirmation = `Type ${view.live_confirmation} to switch to Live.`
  }
  return out
}

/**
 * What the administrator should know before saving (never blocks the save): switching off
 * the gateway that is the default makes new payments unavailable, and nothing replaces it.
 */
export function draftWarnings(view: SoncoPaySettingsView, draft: SoncoPayDraft): string[] {
  const out: string[] = []
  if (!draft.enabled && view.enabled && draft.defaultProvider === 'soncopay') {
    out.push('SoncoPay is the default gateway. After this change no new member payment is possible until SoncoPay '
      + 'is on again or another ready gateway is chosen. Nothing is chosen automatically.')
  }
  return out
}

/** One line for the default in force. */
export function describeDefaultInForce(view: SoncoPaySettingsView): string {
  if (view.default_provider_in_force === 'none') {
    return `New member payments are unavailable. ${view.default_unavailable_reason ?? ''}`.trim()
  }
  const label = view.default_provider_in_force === 'soncopay'
    ? `SoncoPay (${view.environment === 'live' ? 'Live' : 'Test'})` : 'NOWPayments'
  return `New member payments use ${label}.`
}

/**
 * The request body for a save: only what changes. A blank secret is not sent
 * (the saved one is kept); null when there is nothing to save or a value is
 * not valid.
 */
export function settingsChanges(view: SoncoPaySettingsView, draft: SoncoPayDraft): SoncoPaySettingsBody | null {
  if (Object.keys(draftProblems(view, draft)).length) return null
  const out: SoncoPaySettingsBody = {}
  if (draft.enabled !== view.enabled) out.enabled = draft.enabled
  if (draft.environment !== view.environment) {
    out.environment = draft.environment
    if (draft.environment === 'live') out.confirmation = draft.confirmation.trim()
  }
  if (draft.defaultProvider !== view.default_provider) out.default_provider = draft.defaultProvider
  for (const [field, key] of SECRET_FIELDS) {
    const value = draft[field].trim()
    if (value) out[key] = value
  }
  return Object.keys(out).length ? out : null
}

const CHANGE_LABELS: Record<string, string> = {
  SONCOPAY_ENABLED: 'SoncoPay on/off',
  SONCOPAY_ENVIRONMENT: 'environment',
  DEFAULT_CHECKOUT_PROVIDER: 'default checkout',
  TEST_API_KEY: 'Test API key',
  TEST_WEBHOOK_SECRET: 'Test webhook secret',
  LIVE_API_KEY: 'Live API key',
  LIVE_WEBHOOK_SECRET: 'Live webhook secret',
}

/** "Test API key, environment" for a success message. */
export function describeChanges(changed: string[] | undefined | null): string {
  return (changed || []).map((name) => CHANGE_LABELS[name] || name).join(', ')
}

/** One line for the connection test result. */
export function describeConnectionTest(result: SoncoPayConnectionTest): string {
  const where = result.environment === 'live' ? 'Live' : 'Test'
  if (result.ok) {
    const n = result.methods ?? 0
    return `${where} connection OK: SoncoPay accepted the key (${n} payment method${n === 1 ? '' : 's'} open).`
  }
  return `${where} connection failed: ${result.error || 'SoncoPay did not accept the request.'}`
}
