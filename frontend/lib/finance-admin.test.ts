import { describe, expect, it } from 'vitest'

import {
  FINANCE_SECTIONS,
  changedValues,
  credentialPayload,
  financeErrorText,
  isFinanceSection,
  readinessTone,
  tone,
  type SettingField,
} from './finance-admin'

const field = (name: string, kind: SettingField['kind'], value: SettingField['value']): SettingField => ({
  name, group: 'usd', kind, label: name, help: '', value, default: value, minimum: null, maximum: null, choices: [],
  unit: '', max_length: null, approval_note: null,
})

describe('finance admin helpers', () => {
  it('has exactly the seven sections, in order', () => {
    expect(FINANCE_SECTIONS.map((s) => s.label)).toEqual([
      'Payment Providers', 'NOWPayments Configuration', 'Crypto Cashout Settings', 'USD Cashout Settings',
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
