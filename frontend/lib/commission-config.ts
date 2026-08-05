/**
 * Single source of truth for commission rates displayed across the frontend.
 * Must match backend/app/core/commission_config.py
 */
export const COMMISSION_CONFIG = {
  kyc: {
    priceCents: 100,
    platformRatePercent: 10,
    payoutCents: 90,
    currency: 'USD',
  },
  founding_membership: {
    priceCents: 10000,
    platformRatePercent: 10,
    payoutCents: 9000,
    currency: 'USD',
  },
  mfm_membership: {
    priceCents: 10000,
    platformRatePercent: 10,
    payoutCents: 9000,
    currency: 'USD',
  },
  annual_membership: {
    priceCents: 5000,
    platformRatePercent: 10,
    payoutCents: 4500,
    currency: 'USD',
  },
} as const

export type CommissionProductCode = keyof typeof COMMISSION_CONFIG

export function getCommissionDisplay(code: CommissionProductCode) {
  const cfg = COMMISSION_CONFIG[code]
  return {
    price: `$${(cfg.priceCents / 100).toFixed(2)}`,
    platformRate: `${cfg.platformRatePercent}%`,
    payout: `$${(cfg.payoutCents / 100).toFixed(2)}`,
  }
}

export const DIRECT_AFFILIATE_RATE = '10%'
export const INDIRECT_AFFILIATE_RATE = '1%'
