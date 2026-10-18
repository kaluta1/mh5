import { describe, expect, it } from 'vitest'

import {
  canCancel,
  canRequestUsd,
  cashoutStatusText,
  feeLimitText,
  formatExact,
  methodAvailable,
  methodLabel,
  needsAttention,
  networkFeeText,
  receivedText,
  recordStatusLabel,
  walletStatusLabel,
  type CashoutRecord,
  type CashoutSummary,
} from './cashout'

function summary(overrides: Partial<CashoutSummary> = {}): CashoutSummary {
  return {
    cashout_method: 'CRYPTO',
    status: 'BELOW_MINIMUM',
    balances: { total_earned: 0.7, pending: 0, available: 0.7, reserved: 0, paid: 0 },
    payable_amount: 0.7,
    minimum: 1,
    minimums: { CRYPTO: 1, USD: 100 },
    fees: {
      CRYPTO: { platform_fee: 0, note: '' },
      USD: { rule: '1% of the amount, minimum $20, maximum $1,000', fee: null, net_amount: null },
    },
    destination: {
      type: 'CRYPTO',
      wallet: '0xaaaa...aaaa',
      wallet_status: 'VERIFIED',
      payout_currency: 'usdtbsc',
      payable_from: null,
    },
    crypto_payouts_active: false,
    usd_settlement_active: false,
    active_cashout: null,
    ...overrides,
  }
}

function record(overrides: Partial<CashoutRecord> = {}): CashoutRecord {
  return { id: 1, method: 'USD', status: 'requested', gross_amount: 150, fee: 20, net_amount: 130, ...overrides }
}

describe('cashout status wording', () => {
  it('names the minimum of the chosen method', () => {
    expect(cashoutStatusText(summary())).toContain('$1.00 minimum for Crypto Cashout')
    expect(cashoutStatusText(summary({ cashout_method: 'USD', minimum: 100 }))).toContain(
      '$100.00 minimum for USD Cashout',
    )
  })

  it('never promises a payout while automatic crypto payouts are off', () => {
    const text = cashoutStatusText(summary({ status: 'AUTOMATIC_PAYOUT_NOT_ACTIVE' }))
    expect(text).toContain('not active yet')
    expect(text).toContain('kept in full')
  })

  it('tells an unverified wallet apart from a missing one', () => {
    const unverified = summary({ status: 'WALLET_REQUIRED' })
    unverified.destination.wallet_status = 'UNVERIFIED'
    expect(cashoutStatusText(unverified)).toContain('Confirm your payout wallet')
    const missing = summary({ status: 'WALLET_REQUIRED' })
    missing.destination.wallet_status = 'MISSING'
    expect(cashoutStatusText(missing)).toContain('Add a valid USDT BSC payout wallet')
  })

  it('asks for a choice before anything else', () => {
    expect(cashoutStatusText(summary({ cashout_method: null, status: 'METHOD_REQUIRED', minimum: null }))).toContain(
      'Choose how you want to be paid',
    )
    expect(methodLabel(null)).toBe('Not chosen')
  })
})

describe('network fee paid by the member', () => {
  const fee = (over = {}) => ({ applies: true, gross: '5.00', estimate: '0.3', actual: null, net_received: null,
    fee_cap: '0.5', status: 'NOT_RECORDED' as const, flag: null, ...over })

  it('asks for the fee terms before promising a payout', () => {
    const text = cashoutStatusText(summary({ status: 'FEE_TERMS_REQUIRED' }))
    expect(text).toContain('accept the network fee terms')
    expect(text).toContain('You pay the network fee and receive the remaining amount')
    expect(text).toContain('kept in full')
  })

  it('never words a pending payout as the full balance or a guaranteed fee', () => {
    const memberPays = summary({ status: 'AUTOMATIC_PAYOUT_PENDING', fees: {
      CRYPTO: { platform_fee: 0, note: '', network_fee_policy: 'MEMBER_PAYS' },
      USD: { rule: '', fee: null, net_amount: null } } })
    const text = cashoutStatusText(memberPays)
    expect(text).toContain('less the network fee')
    expect(text).toContain('estimated')
    expect(text).toContain('the actual fee may differ')
    for (const promise of ['guarantee', 'at most', 'never more', 'up to']) expect(text.toLowerCase()).not.toContain(promise)
  })

  it('states the limit exactly as it was configured, whichever kinds are set', () => {
    expect(feeLimitText({ cap_percent: '10', cap_usd: '1' })).toBe('10% of the payout or $1.00, whichever is lower')
    expect(feeLimitText({ cap_percent: '2.5', cap_usd: '0' })).toBe('2.5% of the payout')
    expect(feeLimitText({ cap_percent: '0', cap_usd: '0.75' })).toBe('$0.75')
    expect(feeLimitText({ cap_percent: '0', cap_usd: '0' })).toBe('')
  })

  it('never shows an estimate as the fee that was paid', () => {
    const sent = record({ method: 'CRYPTO', status: 'processing', gross_amount: 5, fee: 0, net_amount: 4.7,
      beneficiary_fee: fee() })
    expect(networkFeeText(sent)).toBe('about $0.30 network fee (estimate)')
    expect(receivedText(sent)).toBe('$4.70')                                               // what is expected, in cents
    const paid = record({ method: 'CRYPTO', status: 'completed', gross_amount: 5, fee: 0, net_amount: 4.7,
      beneficiary_fee: fee({ actual: '0.2874', net_received: '4.7126', status: 'RECORDED' }) })
    expect(networkFeeText(paid)).toBe('$0.2874 network fee')                               // exact, not rounded away
    expect(receivedText(paid)).toBe('$4.7126')
  })

  it('shows no network fee for a USD cashout or an earlier company-paid payout', () => {
    expect(networkFeeText(record())).toBeNull()
    expect(networkFeeText(record({ method: 'CRYPTO', beneficiary_fee: fee({ applies: false }) }))).toBeNull()
    expect(receivedText(record())).toBe('$130.00')
  })

  it('keeps an exact figure exact', () => {
    expect([formatExact('5'), formatExact('0.5'), formatExact('0.12345678'), formatExact(null)]).toEqual(
      ['$5.00', '$0.50', '$0.12345678', '-'])
  })
})

describe('payout wallet wording', () => {
  it('explains the email confirmation and a method the administrator switched off', () => {
    expect(cashoutStatusText(summary({ status: 'WALLET_CONFIRMATION_PENDING' }))).toContain('confirmation link')
    const unavailable = cashoutStatusText(summary({ status: 'METHOD_UNAVAILABLE' }))
    expect(unavailable).toContain('not available')
    expect(unavailable).toContain('kept in full')
  })

  it('names every wallet state without calling an unconfirmed wallet verified', () => {
    expect(walletStatusLabel('VERIFIED')).toBe('Verified')
    expect(walletStatusLabel('ON_HOLD')).toContain('security hold')
    expect(walletStatusLabel('UNVERIFIED')).toBe('Not confirmed')
    expect(walletStatusLabel('MISSING')).toBe('Not set')
  })

  it('treats a method as offered unless the server says otherwise', () => {
    expect(methodAvailable(summary(), 'CRYPTO')).toBe(true)                    // older API answer without `methods`
    const methods = {
      CRYPTO: { available: false },
      USD: { available: true, destination_required: false, destination_note: null, cancellation_allowed: true },
    }
    expect(methodAvailable(summary({ methods }), 'CRYPTO')).toBe(false)
    expect(methodAvailable(summary({ methods }), 'USD')).toBe(true)
  })
})

describe('cashout actions', () => {
  it('offers a USD request only when the server says it is ready', () => {
    expect(canRequestUsd(summary({ cashout_method: 'USD', status: 'READY_TO_REQUEST' }))).toBe(true)
    expect(canRequestUsd(summary({ cashout_method: 'USD', status: 'BELOW_MINIMUM' }))).toBe(false)
    expect(canRequestUsd(summary({ cashout_method: 'CRYPTO', status: 'AUTOMATIC_PAYOUT_PENDING' }))).toBe(false)
    expect(canRequestUsd(summary({ cashout_method: 'USD', status: 'IN_PROGRESS' }))).toBe(false)
  })

  it('lets the member cancel only an unprocessed USD request', () => {
    expect(canCancel(record())).toBe(true)
    expect(canCancel(record({ status: 'completed' }))).toBe(false)
    expect(canCancel(record({ method: 'CRYPTO', status: 'processing' }))).toBe(false)
    expect(canCancel(record({ method: 'CRYPTO', status: 'requested' }))).toBe(false)
  })

  it('respects the administrator rule on member cancellation', () => {
    const methods = {
      CRYPTO: { available: true },
      USD: { available: true, destination_required: false, destination_note: null, cancellation_allowed: false },
    }
    expect(canCancel(record(), summary({ methods }))).toBe(false)
    methods.USD.cancellation_allowed = true
    expect(canCancel(record(), summary({ methods }))).toBe(true)
  })

  it('flags the records that were not paid or are still being verified', () => {
    expect(needsAttention(record({ status: 'failed' }))).toBe(true)
    expect(needsAttention(record({ status: 'unknown' }))).toBe(true)
    expect(needsAttention(record({ status: 'completed' }))).toBe(false)
    expect(needsAttention(record({ status: 'requested' }))).toBe(false)
  })

  it('says where the money is for every record state', () => {
    expect(recordStatusLabel('completed')).toBe('Paid')
    expect(recordStatusLabel('failed')).toContain('returned to balance')
    expect(recordStatusLabel('cancelled')).toContain('returned to balance')
    expect(recordStatusLabel('unknown')).toBe('Delayed - being verified')
  })
})
