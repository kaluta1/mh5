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
