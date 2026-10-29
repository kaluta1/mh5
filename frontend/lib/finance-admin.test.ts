import { describe, expect, it } from 'vitest'

import {
  FINANCE_SECTIONS,
  activationChanges,
  activationLock,
  changedValues,
  credentialPayload,
  financeErrorText,
  isFinanceSection,
  readinessTone,
  expectedReceived,
  sameAmount,
  sectionFields,
  validMemberFee,
  validReviewNote,
  validNetworkFee,
  tone,
  type ActivationRules,
  type SettingField,
} from './finance-admin'

const field = (name: string, kind: SettingField['kind'], value: SettingField['value']): SettingField => ({
  name, group: 'usd', kind, label: name, help: '', value, default: value, minimum: null, maximum: null, choices: [],
  unit: '', max_length: null, approval_note: null,
})

describe('finance admin helpers', () => {
  it('has exactly the eight sections, in order', () => {
    expect(FINANCE_SECTIONS.map((s) => s.label)).toEqual([
      'Payment Providers', 'NOWPayments (discontinued)', 'SoncoPay Configuration', 'Crypto Cashout Settings', 'USD Cashout Settings',
      'Payout Security', 'Cashout Transactions', 'Reconciliation & Audit Logs'])
    expect(isFinanceSection('usd-cashout')).toBe(true)
    expect(isFinanceSection('manual-payout')).toBe(false)
    expect(isFinanceSection(undefined)).toBe(false)
  })

  it('submits only the settings that differ from the server values', () => {
    const fields = [field('usd_min_usd', 'money', '100.00'), field('usd_cashout_enabled', 'bool', true),
      field('usd_destination_note', 'text', null)]
    expect(changedValues(fields, { usd_min_usd: '100.00', usd_cashout_enabled: true, usd_destination_note: '' })).toEqual({})
    expect(changedValues(fields, { usd_min_usd: ' 150 ', usd_cashout_enabled: false, usd_destination_note: '' }))
      .toEqual({ usd_min_usd: ' 150 ', usd_cashout_enabled: false })
  })

  it('never sends a blank credential, so a blank field keeps the stored value', () => {
    expect(credentialPayload({ PAYIN_API_KEY: '', IPN_SECRET: '   ', PAYOUT_API_KEY: 'SYNTHETIC-KEY-1' }))
      .toEqual({ PAYOUT_API_KEY: 'SYNTHETIC-KEY-1' })
    expect(credentialPayload({})).toEqual({})
  })

  it('reports the server reason, and a clear message when it is a permission problem', () => {
    expect(financeErrorText({ status: 409, data: { detail: { code: 'UNSAFE_ACTIVATION', message: 'Run a connection test first.' } } }, 'x'))
      .toBe('Run a connection test first.')
    expect(financeErrorText({ status: 403, data: {} }, 'x')).toContain('permission')
    expect(financeErrorText({ status: 500 }, 'Could not save.')).toBe('Could not save.')
  })

  it('colours unknown and failed states as problems, never as success', () => {
    expect(tone('OK')).toBe('green')
    expect(tone('completed')).toBe('green')
    expect(tone('unknown')).toBe('red')
    expect(tone('IP_NOT_WHITELISTED')).toBe('red')
    expect(tone('NOT_VERIFIED')).toBe('amber')
    expect(tone('NOT CONFIGURED')).toBe('gray')
    // Readiness: only VERIFIED is shown as proven.
    expect(readinessTone('VERIFIED')).toBe('green')
    expect(readinessTone('CONFIGURED')).toBe('amber')
    expect(readinessTone('BLOCKED')).toBe('red')
    expect(readinessTone('UNVERIFIED')).toBe('gray')
    expect(readinessTone('DISABLED')).toBe('gray')
    expect(readinessTone(undefined)).toBe('gray')
  })
})

describe('validNetworkFee', () => {
  it('accepts only a plain non-negative amount no larger than the payout', () => {
    for (const ok of ['0', '0.02', '0.0234', '1.32765969', '5', '5.00']) expect(validNetworkFee(ok, 5)).toBe(true)
    for (const bad of ['', ' ', '-0.01', 'abc', '1e-2', '0.123456789', '5.01', '0,02', '.5', '5.']) {
      expect(validNetworkFee(bad, 5)).toBe(false)
    }
  })
})

describe('verifying an actual network fee', () => {
  it('works out the amount received exactly, never with floating-point subtraction', () => {
    expect(expectedReceived(5, '0.0234', 'PAYOUT_AMOUNT')).toBe('4.9766')
    expect(expectedReceived(5, '0.1', 'PAYOUT_AMOUNT')).toBe('4.9')
    expect(expectedReceived(0.3, '0.1', 'PAYOUT_AMOUNT')).toBe('0.2')                     // 0.3 - 0.1 is not 0.2 in binary
    expect(expectedReceived(1234.56, '0.00000001', 'PAYOUT_AMOUNT')).toBe('1234.55999999')
    expect(expectedReceived(5, '0', 'PAYOUT_AMOUNT')).toBe('5')
    expect(expectedReceived(5, '0.25', 'PROVIDER_BALANCE')).toBe('5')                     // the member received all of it
  })

  it('has no expected amount for a fee that is not a usable number or leaves nothing', () => {
    for (const bad of ['', 'abc', '-1', '0.123456789', '1e-2', '5', '5.01']) {
      expect(expectedReceived(5, bad, 'PAYOUT_AMOUNT')).toBeNull()
    }
  })

  it('compares amounts as numbers, not as text', () => {
    expect(sameAmount('4.9766', '4.9766')).toBe(true)
    expect(sameAmount('4.97660', '4.9766')).toBe(true)
    expect(sameAmount('04.9766', '4.9766')).toBe(true)
    expect(sameAmount('5.00', '5')).toBe(true)
    for (const [typed, expected] of [['4.98', '4.9766'], ['4.9765', '4.9766'], ['', '4.9766'], ['abc', '4.9766']]) {
      expect(sameAmount(typed, expected)).toBe(false)
    }
    expect(sameAmount('4.98', null)).toBe(false)
  })

  it('never accepts a fee as large as the payout itself', () => {
    for (const ok of ['0', '0.02', '4.99999999']) expect(validMemberFee(ok, 5)).toBe(true)
    for (const bad of ['5', '5.00', '5.01', '-0.01', 'abc', '', '0.123456789']) expect(validMemberFee(bad, 5)).toBe(false)
  })

  it('accepts a review note only when it says something', () => {
    expect(validReviewNote('Compared the payout with the provider statement.')).toBe(true)
    expect(validReviewNote('  Compared   the payout\nwith the statement.  ')).toBe(true)
    for (const bad of ['', 'ok', 'looked at it', '                              ', 'a'.repeat(40), 'ab '.repeat(30),
      'x'.repeat(501)]) {
      expect(validReviewNote(bad)).toBe(false)
    }
  })

  it('lays a section out in the order the server gives and skips names it does not know', () => {
    const fields = [field('member_fee_cap_usd', 'money', '0.00'), field('provider_fee_mode', 'choice', 'UNVERIFIED'),
      field('crypto_min_usd', 'money', '1.00')]
    const section = { key: 'provider', title: 'A', note: '', fields: ['provider_fee_mode', 'not_a_setting', 'member_fee_cap_usd'] }
    expect(sectionFields(fields, section).map((f) => f.name)).toEqual(['provider_fee_mode', 'member_fee_cap_usd'])
  })

  const rules = (on: boolean): ActivationRules => ({
    permission: 'activate_financial_operations',
    values: { crypto_auto_payout_enabled: true, usd_settlement_enabled: true, fee_terms_approved: true,
      provider_fee_mode: 'DEDUCTED_BY_PROVIDER' },
    automatic_payouts_on: on,
    while_automatic_payouts_on: { fields: ['max_single_payout_usd', 'crypto_payout_currency'],
      switches: ['provider_enabled'], credential_group: 'payout' },
  })

  it('names the changes that need the activation permission and never a switch-off', () => {
    expect(activationChanges(null, { crypto_auto_payout_enabled: true })).toEqual([])        // an older server: it decides
    expect(activationChanges(rules(false), { crypto_auto_payout_enabled: true, usd_min_usd: '150' }))
      .toEqual(['crypto_auto_payout_enabled'])
    expect(activationChanges(rules(false), { provider_fee_mode: 'DEDUCTED_BY_PROVIDER', fee_terms_approved: true }))
      .toEqual(['provider_fee_mode', 'fee_terms_approved'])
    for (const off of [{ crypto_auto_payout_enabled: false }, { usd_settlement_enabled: false },
      { fee_terms_approved: false }, { provider_fee_mode: 'UNVERIFIED' }, { provider_enabled: false }]) {
      expect(activationChanges(rules(true), off)).toEqual([])
    }
    // Payout settings: ordinary while payouts are off, an activation while they are on ...
    expect(activationChanges(rules(false), { max_single_payout_usd: '500', provider_enabled: true })).toEqual([])
    expect(activationChanges(rules(true), { max_single_payout_usd: '500', provider_enabled: true, usd_min_usd: '150' }))
      .toEqual(['max_single_payout_usd', 'provider_enabled'])
    // ... unless the same change switches them off.
    expect(activationChanges(rules(true), { max_single_payout_usd: '500', crypto_auto_payout_enabled: false })).toEqual([])
  })

  it('locks a control only where using it would activate something', () => {
    const lock = (on: boolean, f: SettingField) => activationLock(rules(on), f)
    expect(activationLock(null, field('crypto_auto_payout_enabled', 'bool', false))).toBeNull()
    expect(lock(false, field('crypto_auto_payout_enabled', 'bool', false))).toContain('activate_financial_operations')
    expect(lock(false, field('crypto_auto_payout_enabled', 'bool', true))).toBeNull()        // on: it can be switched off
    expect(lock(false, field('usd_min_usd', 'money', '100.00'))).toBeNull()
    expect(lock(false, field('max_single_payout_usd', 'money', '1000.00'))).toBeNull()
    expect(lock(true, field('max_single_payout_usd', 'money', '1000.00'))).toContain('Automatic payouts are on')
    expect(lock(true, field('provider_enabled', 'bool', false))).toContain('activate_financial_operations')
    expect(lock(true, field('provider_enabled', 'bool', true))).toBeNull()
    expect(lock(false, field('provider_enabled', 'bool', false))).toBeNull()
    expect(lock(true, field('provider_fee_mode', 'choice', 'UNVERIFIED'))).toBeNull()        // one value of it, not the field
  })
})
