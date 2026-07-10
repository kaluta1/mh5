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
    priceCents: 49900,
    platformRatePercent: 10,
    payoutCents: 44910,
    currency: 'USD',
  },
  mfm_membership: {
    priceCents: 49900,
    platformRatePercent: 10,
    payoutCents: 44910,
    currency: 'USD',
  },
  annual_membership: {
    priceCents: 9900,
    platformRatePercent: 10,
    payoutCents: 8910,
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
