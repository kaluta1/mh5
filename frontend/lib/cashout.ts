// Dual cashout (affiliate commissions): types and the wording of each state.
// The backend decides everything (GET /api/v1/wallet/cashout); this file only
// turns its answer into text. Nothing here moves money.

export type CashoutMethod = 'CRYPTO' | 'USD'

export type CashoutStatus =
  | 'METHOD_REQUIRED'
  | 'WALLET_REQUIRED'
  | 'WALLET_CONFIRMATION_PENDING'
  | 'WALLET_ON_HOLD'
  | 'METHOD_UNAVAILABLE'
  | 'BELOW_MINIMUM'
  | 'AUTOMATIC_PAYOUT_PENDING'
  | 'AUTOMATIC_PAYOUT_NOT_ACTIVE'
  | 'READY_TO_REQUEST'
  | 'IN_PROGRESS'
  | 'ACCOUNT_HOLD'

export type CashoutRecord = {
  id: number
  method: CashoutMethod
  status: 'requested' | 'processing' | 'unknown' | 'completed' | 'failed' | 'cancelled'
  gross_amount: number
  fee: number
  net_amount: number
  /** Crypto: the network fee estimate, and who bears it. */
  network_fee?: number | null
  network_fee_policy?: 'COMPANY_PAYS' | 'MEMBER_PAYS' | null
  destination?: string | null
  payout_currency?: string | null
  reference?: string | null
  requested_at?: string | null
  processed_at?: string | null
}

export type CashoutSummary = {
  cashout_method: CashoutMethod | null
  status: CashoutStatus
  balances: { total_earned: number; pending: number; available: number; reserved: number; paid: number }
  payable_amount: number
  minimum: number | null
  minimums: Record<CashoutMethod, number>
  /** Which methods the administrator currently offers, and what a USD request needs. */
  methods?: {
    CRYPTO: { available: boolean }
    USD: { available: boolean; destination_required: boolean; destination_note: string | null; cancellation_allowed: boolean }
  }
  fees: {
    CRYPTO: { platform_fee: number; note: string; network_fee_policy?: 'COMPANY_PAYS' | 'MEMBER_PAYS' }
    USD: { rule: string; fee: number | null; net_amount: number | null }
  }
  destination: {
    type: CashoutMethod | null
    wallet: string | null
    wallet_status: 'MISSING' | 'INVALID' | 'UNVERIFIED' | 'ON_HOLD' | 'VERIFIED'
    payout_currency: string
    payable_from: string | null
    network?: string
    hold_hours?: number
    email_verification_required?: boolean
    /** A wallet change waiting for the emailed confirmation link (masked). */
    pending_wallet?: { wallet: string; payout_currency: string; network: string; expires_at: string } | null
  }
  crypto_payouts_active: boolean
  usd_settlement_active: boolean
  eligibility_status?: string | null
  eligibility_next_step?: string | null
  active_cashout: CashoutRecord | null
}

export function formatUsd(amount: number | null | undefined): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount ?? 0)
}

/** One sentence telling the member where their cashout stands. */
export function cashoutStatusText(summary: CashoutSummary): string {
  const minimum = formatUsd(summary.minimum ?? 0)
  switch (summary.status) {
    case 'METHOD_REQUIRED':
      return 'Choose how you want to be paid: Crypto Cashout or USD Cashout.'
    case 'WALLET_REQUIRED':
      return summary.destination.wallet_status === 'UNVERIFIED'
        ? 'Confirm your payout wallet in Settings (save it again with your password, then open the link we email you) to receive crypto payouts.'
        : 'Add a valid USDT BSC payout wallet in Settings to receive crypto payouts.'
    case 'WALLET_CONFIRMATION_PENDING':
      return 'Open the confirmation link we sent to your email address to confirm your payout wallet.'
    case 'METHOD_UNAVAILABLE':
      return 'This cashout method is not available at the moment. Your earnings are kept in full; you can choose the other method.'
    case 'WALLET_ON_HOLD':
      return `Your payout wallet was changed recently. For your security, payouts to it start on ${formatDate(
        summary.destination.payable_from,
      )}.`
    case 'BELOW_MINIMUM':
      return `Your balance is below the ${minimum} minimum for ${methodLabel(summary.cashout_method)}.`
    case 'AUTOMATIC_PAYOUT_PENDING':
      return 'Your balance will be sent to your wallet automatically in the next payout run.'
    case 'AUTOMATIC_PAYOUT_NOT_ACTIVE':
      return 'Automatic crypto payouts are not active yet. Your balance is kept in full and will be paid once they start.'
    case 'READY_TO_REQUEST':
      return 'You can request a USD Cashout of your whole available balance.'
    case 'IN_PROGRESS':
      return 'You have a cashout in progress. New earnings wait until it has finished.'
    case 'ACCOUNT_HOLD':
      return 'Cashouts are not available for your account yet. Your earnings are kept in full.'
    default:
      return ''
  }
}

export function methodLabel(method: CashoutMethod | null | undefined): string {
  if (method === 'CRYPTO') return 'Crypto Cashout'
  if (method === 'USD') return 'USD Cashout'
  return 'Not chosen'
}

export function recordStatusLabel(status: CashoutRecord['status']): string {
  switch (status) {
    case 'requested':
      return 'Requested'
    case 'processing':
      return 'Processing'
    case 'unknown':
      return 'Being verified'
    case 'completed':
      return 'Paid'
    case 'failed':
      return 'Not paid - returned to balance'
    case 'cancelled':
      return 'Cancelled - returned to balance'
    default:
      return status
  }
}

export function methodAvailable(summary: CashoutSummary, method: CashoutMethod): boolean {
  return summary.methods?.[method]?.available !== false
}

export function walletStatusLabel(status: CashoutSummary['destination']['wallet_status']): string {
  switch (status) {
    case 'VERIFIED':
      return 'Verified'
    case 'ON_HOLD':
      return 'Verified - security hold'
    case 'UNVERIFIED':
      return 'Not confirmed'
    case 'INVALID':
      return 'Not valid for the payout network'
    default:
      return 'Not set'
  }
}

/** Records the member should look at: not paid, or still being checked. */
export function needsAttention(record: CashoutRecord): boolean {
  return record.status === 'failed' || record.status === 'unknown'
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  // The API sends UTC timestamps without a zone suffix.
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleDateString(undefined, { dateStyle: 'medium' })
}

/** Only a USD request that nobody has processed yet can be cancelled by the member. */
export function canCancel(record: CashoutRecord, summary?: CashoutSummary | null): boolean {
  if (summary?.methods?.USD.cancellation_allowed === false) return false
  return record.status === 'requested' && record.method === 'USD'
}

export function canRequestUsd(summary: CashoutSummary): boolean {
  return summary.cashout_method === 'USD' && summary.status === 'READY_TO_REQUEST'
}
