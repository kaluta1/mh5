import { describe, expect, it } from 'vitest'

import { isFinalState, isSoncoPay, parseCheckoutGateway, paymentStateText, safeCheckoutUrl } from './payment-gateway'

describe('lib/payment-gateway', () => {
  it('reads a gateway only from an explicit available answer', () => {
    expect(parseCheckoutGateway({ provider: 'nowpayments', available: true })).toBe('nowpayments')
    expect(parseCheckoutGateway({ provider: 'soncopay', available: true })).toBe('soncopay')
    for (const bad of [null, undefined, '', 'soncopay', 0, [], {}, { provider: 'nowpayments' },
      { provider: 'nowpayments', available: false }, { provider: 'none', available: false },
      { provider: 'none', available: true }, { provider: 'NOWPAYMENTS', available: true },
      { provider: 'soncopay', available: 'yes' }]) {
      expect(parseCheckoutGateway(bad)).toBe('unavailable')
    }
  })

  it('opens only an https page on SoncoPay', () => {
    expect(safeCheckoutUrl('https://soncopay.com/pay/pay_3f9a5c0d21e4b7a6c8d1'))
      .toBe('https://soncopay.com/pay/pay_3f9a5c0d21e4b7a6c8d1')
    expect(safeCheckoutUrl('https://checkout.soncopay.com/pay/x')).toBe('https://checkout.soncopay.com/pay/x')
    for (const bad of ['http://soncopay.com/pay/x', 'javascript:alert(1)', 'https://soncopay.com.evil.test/pay',
      'https://evil.test/?u=https://soncopay.com', 'data:text/html,hi', '', null, undefined, 'not a url']) {
      expect(safeCheckoutUrl(bad as string)).toBeNull()
    }
  })

  it('says something for every state, and pending when unknown', () => {
    for (const state of ['pending', 'awaiting_confirmation', 'paid', 'expired', 'failed', 'partial', 'refunded']) {
      expect(paymentStateText(state)).toBeTruthy()
    }
    expect(paymentStateText('something-new')).toBe(paymentStateText('pending'))
    expect(paymentStateText(undefined)).toBe(paymentStateText('pending'))
  })

  it('knows the final states and the gateway', () => {
    expect(['paid', 'expired', 'failed', 'refunded'].every(isFinalState)).toBe(true)
    expect(['pending', 'awaiting_confirmation', 'partial', undefined].some(isFinalState)).toBe(false)
    expect(isSoncoPay({ provider: 'soncopay' })).toBe(true)
    expect(isSoncoPay({ provider: 'nowpayments' })).toBe(false)
    expect(isSoncoPay(null)).toBe(false)
  })
})
