/**
 * MyHigh5 Chart of Accounts — shared codes and distribution math (mirrors backend
 * `app/accounting/distribution_formulas.py`). Use for admin UI previews and validation.
 */

const round2 = (n: number) => Math.round(n * 100) / 100

export const COA = {
  ASSETS: {
    ROOT: '1000',
    PLATFORM_WALLET: '1001',
    ACCOUNTS_RECEIVABLE: '1200',
  },
  LIABILITIES: {
    ROOT: '2000',
    COMMISSIONS_PAYABLE_L1: '2001',
    COMMISSIONS_PAYABLE_L2_10: '2002',
    SERVICE_FEES_PAYABLE_KYC: '2003',
    USER_FUNDS_PAYABLE: '2100',
    FOUNDING_MEMBERS_POOL_PAYABLE: '2104',
    DEFERRED_REVENUE_ANNUAL: '2110',
    DEFERRED_REVENUE_FOUNDING: '2111',
    DEFERRED_PLATFORM_FEE_CLUB: '2112',
    CLUB_OWNER_SUBSCRIPTION_PAYABLE: '2120',
    MEMBER_AD_REVENUE_SHARE_PAYABLE: '2130',
    GST_PAYABLE_SG: '2200',
  },
  EQUITY: {
    ROOT: '3000',
    RETAINED_EARNINGS: '3001',
  },
  REVENUE: {
    ROOT: '4000',
    KYC: '4001',
    MEMBERSHIP: '4002',
    PLATFORM_NET: '4003',
    AD_PLATFORM_RETAINED: '4004',
    CASHOUT_FEE: '4005',
    CLUB_PLATFORM_SERVICE_FEE: '4006',
  },
  EXPENSE: {
    ROOT: '5000',
    COMMISSION: '5001',
    KYC_PROVIDER: '5002',
    AD_SHARE_TO_MEMBERS: '5003',
  },
} as const

export type DistributionLabel =
  | 'level_1_sponsor'
  | 'level_2_to_10_sponsors'
  | 'founding_members_pool'
  | 'shufti_kyc_payable'
  | 'platform_revenue_net'
  | 'participant_share'
  | 'nominator_share'

export interface DistributionLine {
  label: DistributionLabel | string
  amount: number
}

/** Annual membership: L1 10%; L2–10 1% each; pool 10%; Shufti fixed; remainder platform. */
export function annualMembershipSplit(
  gross: number,
  shuftiFixed = 2,
  levels2to10Filled = 9
): DistributionLine[] {
  const g = round2(gross)
  const l1 = round2(g * 0.1)
  const per = round2(g * 0.01)
  const filled = Math.max(0, Math.min(9, levels2to10Filled))
  const l210 = round2(per * filled)
  const pool = round2(g * 0.1)
  const shufti = round2(shuftiFixed)
  const platform = round2(g - l1 - l210 - pool - shufti)
  return [
    { label: 'level_1_sponsor', amount: l1 },
    { label: 'level_2_to_10_sponsors', amount: l210 },
    { label: 'founding_members_pool', amount: pool },
    { label: 'shufti_kyc_payable', amount: shufti },
    { label: 'platform_revenue_net', amount: platform },
  ]
}

export function foundingMembershipSplit(gross: number, levels2to10Filled = 9): DistributionLine[] {
  const g = round2(gross)
  const l1 = round2(g * 0.1)
  const per = round2(g * 0.01)
  const filled = Math.max(0, Math.min(9, levels2to10Filled))
  const l210 = round2(per * filled)
  const pool = round2(g * 0.1)
  const platform = round2(g - l1 - l210 - pool)
  return [
    { label: 'level_1_sponsor', amount: l1 },
    { label: 'level_2_to_10_sponsors', amount: l210 },
    { label: 'founding_members_pool', amount: pool },
    { label: 'platform_revenue_net', amount: platform },
  ]
}

export function adRevenueParticipantSplit(gross: number, levels2to10Filled = 9): DistributionLine[] {
  const g = round2(gross)
  const member = round2(g * 0.4)
  const l1 = round2(g * 0.05)
  const per = round2(g * 0.01)
  const filled = Math.max(0, Math.min(9, levels2to10Filled))
  const l210 = round2(per * filled)
  const pool = round2(g * 0.1)
  const platform = round2(g - member - l1 - l210 - pool)
  return [
    { label: 'participant_share', amount: member },
    { label: 'level_1_sponsor', amount: l1 },
    { label: 'level_2_to_10_sponsors', amount: l210 },
    { label: 'founding_members_pool', amount: pool },
    { label: 'platform_revenue_net', amount: platform },
  ]
}

export function adRevenueNominatorSplit(gross: number, levels2to10Filled = 9): DistributionLine[] {
  const g = round2(gross)
  const nom = round2(g * 0.1)
  const l1 = round2(g * 0.025)
  const per = round2(g * 0.01)
  const filled = Math.max(0, Math.min(9, levels2to10Filled))
  const l210 = round2(per * filled)
  const pool = round2(g * 0.1)
  const platform = round2(g - nom - l1 - l210 - pool)
  return [
    { label: 'nominator_share', amount: nom },
    { label: 'level_1_sponsor', amount: l1 },
    { label: 'level_2_to_10_sponsors', amount: l210 },
    { label: 'founding_members_pool', amount: pool },
    { label: 'platform_revenue_net', amount: platform },
  ]
}

export interface ClubMarkupSplit {
  grossCharge: number
  baseToOwner: number
  markup: number
  level1Sponsor: number
  level2to10: number
  foundingPool: number
  platformNet: number
}

/** Charge = base × 1.2; splits on 20% markup only. */
export function clubMarkupSplit(
  baseSubscription: number,
  markupRate = 0.2,
  levels2to10Filled = 9
): ClubMarkupSplit {
  const base = round2(baseSubscription)
  const markup = round2(base * markupRate)
  const l1 = round2(markup * 0.1)
  const per = round2(markup * 0.01)
  const filled = Math.max(0, Math.min(9, levels2to10Filled))
  const l210 = round2(per * filled)
  const pool = round2(markup * 0.1)
  const platform = round2(markup - l1 - l210 - pool)
  return {
    grossCharge: round2(base + markup),
    baseToOwner: base,
    markup,
    level1Sponsor: l1,
    level2to10: l210,
    foundingPool: pool,
    platformNet: platform,
  }
}

/** 1% of request, min 20, max 1000. */
export function cashoutFeeAndNet(requested: number): { fee: number; net: number } {
  const req = round2(requested)
  const raw = round2(req * 0.01)
  const fee = round2(Math.max(20, Math.min(raw, 1000)))
  return { fee, net: round2(req - fee) }
}
