/**
 * Member checkout gateways: what the payment dialogs show for a NOWPayments
 * or a SoncoPay payment.
 *
 * The server decides the gateway of a NEW payment (GET /payments/checkout-gateway)
 * and every payment keeps its own gateway. A SoncoPay payment is paid on
 * SoncoPay's secure hosted page (crypto, mobile money or card); the browser only
 * ever opens that page and then asks OUR server for the status. Nothing is
 * credited from the browser: the server confirms with SoncoPay itself.
 */

export type CheckoutGateway = 'nowpayments' | 'soncopay'

/** What a NEW payment can use now: a gateway, or none (no silent fallback to a gateway that is off). */
export type CheckoutAvailability = CheckoutGateway | 'unavailable'

export const CHECKOUT_UNAVAILABLE_TEXT = 'Payments are temporarily unavailable. Please try again later.'

/** The server refused a NEW payment because no gateway can take one now (503 CHECKOUT_UNAVAILABLE). */
export class CheckoutUnavailableError extends Error {
  constructor(message: string = CHECKOUT_UNAVAILABLE_TEXT) {
    super(message)
    this.name = 'CheckoutUnavailableError'
  }
}

/**
 * Reads the server's /payments/checkout-gateway answer. Fails closed: a gateway only when the server says
 * available true AND names a known gateway; anything else (missing, malformed, 'none') is 'unavailable'.
 */
export function parseCheckoutGateway(data: unknown): CheckoutAvailability {
  if (!data || typeof data !== 'object') return 'unavailable'
  const { provider, available } = data as { provider?: unknown; available?: unknown }
  if (available !== true) return 'unavailable'
  return provider === 'soncopay' || provider === 'nowpayments' ? provider : 'unavailable'
}

/**
 * How a member pays through SoncoPay: only the methods the server lists for the account. A code is
 * usdt_bsc, usdt_trc20, card, or "mm:" + a mobile money method (one operator in one or more countries).
 */
export type SoncoPayMethodKind = 'crypto' | 'card' | 'mobile_money'
export type SoncoPayMethod = string

export interface SoncoPayMethodOption {
  code: SoncoPayMethod
  kind: SoncoPayMethodKind
  label: string
  countries: string[]
  currency: string | null
}

export const SONCOPAY_METHOD_LABELS: Record<string, string> = {
  usdt_bsc: 'USDT on BNB Smart Chain (BEP20)',
  usdt_trc20: 'USDT on Tron (TRC20)',
  card: 'Bank card',
}

const USDT_BSC_ONLY: SoncoPayMethodOption[] = [
  { code: 'usdt_bsc', kind: 'crypto', label: SONCOPAY_METHOD_LABELS.usdt_bsc, countries: [], currency: null },
]

function validCode(code: unknown, kind: unknown): boolean {
  if (typeof code !== 'string') return false
  if (kind === 'mobile_money') return /^mm:[a-z0-9_]{1,17}$/.test(code)
  return code === 'usdt_bsc' || code === 'usdt_trc20' || code === 'card'
}

/**
 * The SoncoPay methods in the server's /payments/checkout-gateway answer, in its order. Anything that is
 * not a known method is dropped; an answer without a list (an older server) means USDT on BSC only.
 */
export function parseSoncoPayMethods(data: unknown): SoncoPayMethodOption[] {
  const listed = data && typeof data === 'object' ? (data as { methods?: unknown }).methods : undefined
  if (!Array.isArray(listed)) return USDT_BSC_ONLY
  const seen = new Set<string>()
  const out: SoncoPayMethodOption[] = []
  for (const item of listed) {
    if (!item || typeof item !== 'object') continue
    const m = item as Record<string, unknown>
    const kind = m.kind === 'card' || m.kind === 'mobile_money' ? m.kind : 'crypto'
    if (!validCode(m.code, kind) || seen.has(m.code as string)) continue
    seen.add(m.code as string)
    out.push({
      code: m.code as string,
      kind: kind as SoncoPayMethodKind,
      label: typeof m.label === 'string' && m.label ? m.label : SONCOPAY_METHOD_LABELS[m.code as string] ?? (m.code as string),
      countries: Array.isArray(m.countries) ? m.countries.filter((c): c is string => typeof c === 'string') : [],
      currency: typeof m.currency === 'string' ? m.currency : null,
    })
  }
  return out.length ? out : USDT_BSC_ONLY
}

/** The label of a stored method code (a payment the server already holds). */
export function soncopayMethodLabel(code: string | null | undefined, options: SoncoPayMethodOption[] = []): string {
  const known = options.find((o) => o.code === code)
  if (known) return known.label
  if (code && SONCOPAY_METHOD_LABELS[code]) return SONCOPAY_METHOD_LABELS[code]
  if (code && code.startsWith('mm:')) return `Mobile money (${code.slice(3)})`
  return SONCOPAY_METHOD_LABELS.usdt_bsc
}

/** The member-facing state of a SoncoPay payment, as the server reports it. */
export type PaymentState = 'pending' | 'awaiting_confirmation' | 'paid' | 'expired' | 'failed' | 'partial' | 'refunded'

export function isSoncoPay(payment: { provider?: string | null } | null | undefined): boolean {
  return payment?.provider === 'soncopay'
}

/**
 * The hosted checkout page, or null. Only an https page on SoncoPay's own
 * domain is ever opened (never a value that could run script or leave for
 * another site).
 */
export function safeCheckoutUrl(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    const parsed = new URL(url)
    const host = parsed.hostname.toLowerCase()
    if (parsed.protocol !== 'https:') return null
    if (host !== 'soncopay.com' && !host.endsWith('.soncopay.com')) return null
    return parsed.toString()
  } catch {
    return null
  }
}

const STATE_TEXT: Record<PaymentState, string> = {
  pending: 'Waiting for your payment on the secure SoncoPay page.',
  awaiting_confirmation: 'Payment detected. Waiting for confirmation…',
  paid: 'Payment confirmed.',
  expired: 'This payment expired before it was paid. Start a new payment.',
  failed: 'The payment failed. Nothing was charged for this order. Start a new payment.',
  partial: 'Part of the amount arrived. Send the rest shown on the SoncoPay page before it expires.',
  refunded: 'This payment was refunded.',
}

/** One sentence for a SoncoPay payment state (pending when unknown). */
export function paymentStateText(state: string | null | undefined): string {
  return STATE_TEXT[(state as PaymentState) in STATE_TEXT ? (state as PaymentState) : 'pending']
}

/** A SoncoPay state after which nothing more will happen for this payment. */
export function isFinalState(state: string | null | undefined): boolean {
  return state === 'paid' || state === 'expired' || state === 'failed' || state === 'refunded'
}
