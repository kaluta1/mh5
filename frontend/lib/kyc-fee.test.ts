import { describe, expect, it } from 'vitest'

import { formatKycFee, isKycFree, kycFeeAmount, parseKycFeeInput } from './kyc-fee'

describe('the member KYC fee shown to a member', () => {
  it('shows the amount the server sent', () => {
    expect(formatKycFee({ kyc_price: 7.5, kyc_currency: 'USD' })).toBe('7.50 USD')
    expect(formatKycFee({ kyc_price: 10, kyc_currency: 'usd' })).toBe('10 USD')
    expect(formatKycFee({ kyc_price: 5, kyc_currency: 'USD' })).toBe('5 USD')
    expect(formatKycFee({ kyc_price: '25.00' })).toBe('25 USD')
  })

  it('shows a fee of 0 as free, never as a price', () => {
    expect(formatKycFee({ kyc_price: 0, kyc_currency: 'USD' })).toBe('Free')
    expect(formatKycFee({ kyc_price: 0, kyc_is_free: true }, 'Gratuit')).toBe('Gratuit')
    expect(isKycFree({ kyc_price: 0 })).toBe(true)
    expect(isKycFree({ kyc_is_free: true })).toBe(true)
    expect(isKycFree({ kyc_price: 10 })).toBe(false)
  })

  it('never shows an assumed price while the fee is unknown', () => {
    for (const unknown of [null, undefined, {}, { kyc_price: null }, { kyc_price: 'abc' }, { kyc_price: -1 }]) {
      expect(isKycFree(unknown as any)).toBe(false)
      expect(kycFeeAmount(unknown as any)).toBeNull()
      expect(formatKycFee(unknown as any)).toBe('…')
      expect(formatKycFee(unknown as any)).not.toMatch(/10/)
    }
  })
})

describe('the fee an administrator types', () => {
  it('accepts 0 and amounts with at most two decimals', () => {
    expect(parseKycFeeInput('0')).toBe('0.00')
    expect(parseKycFeeInput(' 7.5 ')).toBe('7.50')
    expect(parseKycFeeInput('1000')).toBe('1000.00')
  })

  it('refuses anything else', () => {
    for (const bad of ['', '-1', '1.999', 'abc', '1e3', '1000.01', '10 USD', '1,50', '.5']) {
      expect(parseKycFeeInput(bad)).toBeNull()
    }
  })
})
