// Dual cashout (affiliate commissions): types and the wording of each state.
// The backend decides everything (GET /api/v1/wallet/cashout); this file only
// turns its answer into text. Nothing here moves money.

export type CashoutMethod = 'CRYPTO' | 'USD'

export type CashoutStatus =
  | 'METHOD_REQUIRED'
  | 'WALLET_REQUIRED'
  | 'WALLET_CONFIRMATION_PENDING'
  | 'WALLET_APPROVAL_PENDING'
  | 'WALLET_REJECTED'
  | 'WALLET_ON_HOLD'
  | 'FEE_TERMS_REQUIRED'
  | 'METHOD_UNAVAILABLE'
  | 'BELOW_MINIMUM'
  | 'AUTOMATIC_PAYOUT_PENDING'
  | 'AUTOMATIC_PAYOUT_NOT_ACTIVE'
  | 'READY_TO_REQUEST'
  | 'IN_PROGRESS'
  | 'ACCOUNT_HOLD'

/** The network fee of a crypto payout the member bears. Exact figures, sent as text. */
export type BeneficiaryFee = {
  applies: boolean
  gross: string
  estimate: string | null
  /** The estimate with the safety margin added: what was compared with the limit. Still an estimate. */
  estimate_adjusted?: string | null
  /** Known only once the provider has sent the payout. Never an estimate. */
  actual: string | null
  net_received: string | null
  fee_cap: string | null
  status: 'NOT_APPLICABLE' | 'NOT_RECORDED' | 'RECORDED'
  flag?: string | null
}

/** The network fee terms a member accepts before automatic crypto payouts. */
export type FeeTerms = {
  available: boolean
  version: number
  /** Highest fee as a share of the payout, in percent ("0" = this limit is not set). */
  cap_percent: string
  /** Highest fee as an amount per payout ("0" = this limit is not set). */
  cap_usd: string
  valid_days: number
  minimum_received: number
  /** Who deducts the fee (the payout provider's name). */
  provider?: string
  /** The limit is checked against the provider's estimate; the actual fee is not guaranteed. */
  limit_applies_to?: 'ESTIMATE'
  actual_fee_guaranteed?: boolean
  accepted: boolean
  accepted_at: string | null
  expires_at: string | null
}

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
  beneficiary_fee?: BeneficiaryFee | null
  destination?: string | null
  payout_currency?: string | null
  reference?: string | null
  requested_at?: string | null
  processed_at?: string | null
  /** Individual automatic payout: the ONE commission it pays, its blockchain transaction and explorer link. */
  commission_id?: number | null
  tx_hash?: string | null
  explorer_url?: string | null
}

/** The administrator's decision on the member's current payout wallet. */
export type WalletApproval = {
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED'
  wallet: string | null
  network: string
  submitted_at: string | null
  decided_at: string | null
  reason: string | null
}

export type CashoutSummary = {
  cashout_method: CashoutMethod | null
  status: CashoutStatus
  balances: {
    total_earned: number
    pending: number
    available: number
    reserved: number
    paid: number
    /** Historical commissions held for review: never available, never paid automatically. */
    held?: number
    /** Available and not yet paid (never a held row). */
    available_unpaid?: number
    /** The part of the unpaid balance waiting for the wallet's approval. */
    awaiting_wallet_approval?: number
    /** Handed to a payout that is not settled yet. */
    processing?: number
  }
  wallet_approval?: WalletApproval | null
  payable_amount: number
  minimum: number | null
  minimums: Record<CashoutMethod, number>
  /** Which methods the administrator currently offers, and what a USD request needs. */
  methods?: {
    CRYPTO: { available: boolean }
    USD: { available: boolean; destination_required: boolean; destination_note: string | null; cancellation_allowed: boolean }
  }
  fees: {
    CRYPTO: {
      platform_fee: number
      note: string
      network_fee_policy?: 'COMPANY_PAYS' | 'MEMBER_PAYS'
      terms?: FeeTerms
    }
    USD: { rule: string; fee: number | null; net_amount: number | null }
  }
  destination: {
    type: CashoutMethod | null
    wallet: string | null
    wallet_status: 'MISSING' | 'INVALID' | 'UNVERIFIED' | 'PENDING_APPROVAL' | 'REJECTED' | 'ON_HOLD' | 'VERIFIED'
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
    case 'WALLET_APPROVAL_PENDING':
      return 'Your payout wallet is waiting for approval by MyHigh5. Your commissions are kept in full and are paid automatically, each one separately, once it is approved.'
    case 'WALLET_REJECTED':
      return 'Your payout wallet was not approved. Submit a valid USDT BEP20 wallet in Settings. Your commissions are kept in full.'
    case 'METHOD_UNAVAILABLE':
      return 'This cashout method is not available at the moment. Your earnings are kept in full; you can choose the other method.'
    case 'WALLET_ON_HOLD':
      return `Your payout wallet was changed recently. For your security, payouts to it start on ${formatDate(
        summary.destination.payable_from,
      )}.`
    case 'FEE_TERMS_REQUIRED':
      return 'Read and accept the network fee terms below to receive automatic crypto payouts. You pay the network fee and receive the remaining amount. Your balance is kept in full until you accept.'
    case 'BELOW_MINIMUM':
      return `Your balance is below the ${minimum} minimum for ${methodLabel(summary.cashout_method)}.`
    case 'AUTOMATIC_PAYOUT_PENDING':
      return summary.fees.CRYPTO.network_fee_policy === 'MEMBER_PAYS'
        ? 'Each commission is sent to your approved wallet automatically, on its own, as soon as it is available, less the network fee. The fee is estimated before the payout; the actual fee may differ.'
        : 'Each commission is sent to your approved wallet automatically, on its own, as soon as it is available.'
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
      return 'Delayed - being verified'
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

/** An exact amount sent as text ("0.2874"), shown without rounding it away. */
export function formatExact(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-'
  const [whole, fraction = ''] = value.split('.')
  return `$${whole}.${fraction.padEnd(2, '0')}`
}

/** The limit the fee ESTIMATE is checked against, in words. Empty when none is set. It does not bound the actual fee. */
export function feeLimitText(terms: Pick<FeeTerms, 'cap_percent' | 'cap_usd'>): string {
  const percent = Number(terms.cap_percent) > 0 ? `${terms.cap_percent}% of the payout` : ''
  const amount = Number(terms.cap_usd) > 0 ? formatExact(terms.cap_usd) : ''
  if (percent && amount) return `${percent} or ${amount}, whichever is lower`
  return percent || amount
}

/** What the network fee column of a crypto payout shows. */
export function networkFeeText(record: CashoutRecord): string | null {
  const fee = record.beneficiary_fee
  if (!fee?.applies) return null
  if (fee.actual !== null) return `${formatExact(fee.actual)} network fee`
  if (fee.estimate !== null) return `about ${formatExact(fee.estimate)} network fee (estimate)`
  return null
}

/** What the member received, once the provider's actual fee is known; otherwise the expected amount. */
export function receivedText(record: CashoutRecord): string {
  const fee = record.beneficiary_fee
  if (fee?.applies && fee.net_received !== null) return formatExact(fee.net_received)
  return formatUsd(record.net_amount)
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
    case 'PENDING_APPROVAL':
      return 'Waiting for approval'
    case 'REJECTED':
      return 'Not approved'
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

/** A short transaction hash for tables: 0x1234...abcd. */
export function shortHash(hash: string | null | undefined): string {
  if (!hash) return '-'
  return hash.length > 16 ? `${hash.slice(0, 8)}...${hash.slice(-6)}` : hash
}
