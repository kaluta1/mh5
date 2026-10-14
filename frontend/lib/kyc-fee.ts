/**
 * The Member KYC Verification Fee: what one new verification attempt costs a
 * member, set by an administrator on the server. 0 = free KYC.
 *
 * The server decides the fee and whether a payment is needed; the browser only
 * shows it. Nothing here knows what the KYC provider charges MyHigh5.
 */

export const KYC_FEE_URL = '/api/v1/kyc/fee'
export const KYC_ADMIN_FEE_URL = '/api/v1/kyc/admin/fee'
/** Shown only until the server's figure has arrived. */
export const KYC_FEE_FALLBACK_USD = 10

export type KycFeeView = { amount: string; currency: string; is_free: boolean; retry_policy: string }

export type KycAdminFeeView = KycFeeView & {
  max_amount: string
  can_change: boolean
  /** The permission a change needs (manage_kyc_settings). */
  permission?: string
  last_change: { at: string | null; by_user_id: number | null; old_amount: string | null; new_amount: string | null } | null
}

type FeeSource = { kyc_price?: number | string | null; kyc_currency?: string | null; kyc_is_free?: boolean | null } | null | undefined

/** The fee as a number, or null when the server has not said (0 is a real fee: free). */
export function kycFeeAmount(source: FeeSource): number | null {
  const raw = source?.kyc_price
  if (raw === null || raw === undefined || raw === '') return null
  const amount = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(amount) && amount >= 0 ? amount : null
}

export function isKycFree(source: FeeSource): boolean {
  return source?.kyc_is_free === true || kycFeeAmount(source) === 0
}

/** "Free", "7.50 USD", or the fallback while the fee is unknown. Never turns a fee of 0 into a price. */
export function formatKycFee(source: FeeSource, freeLabel = 'Free'): string {
  if (isKycFree(source)) return freeLabel
  const amount = kycFeeAmount(source) ?? KYC_FEE_FALLBACK_USD
  const text = Number.isInteger(amount) ? String(amount) : amount.toFixed(2)
  return `${text} ${(source?.kyc_currency || 'USD').toUpperCase()}`
}

/** What an administrator typed, as the string sent to the server; null when it is not an amount. */
export function parseKycFeeInput(value: string, maxAmount = 1000): string | null {
  const text = value.trim()
  if (!/^\d{1,6}(\.\d{1,2})?$/.test(text)) return null
  const amount = Number(text)
  if (!Number.isFinite(amount) || amount < 0 || amount > maxAmount) return null
  return amount.toFixed(2)
}
