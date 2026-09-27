import { describe, expect, it } from 'vitest'

import { apiErrorText, financialHoldMessage, isFinancialActionAvailable } from './financial-eligibility'

describe('financial eligibility (Phase 10)', () => {
  it('treats only ALLOWED (or a missing status from an older backend) as available', () => {
    expect(isFinancialActionAvailable('ALLOWED')).toBe(true)
    expect(isFinancialActionAvailable(undefined)).toBe(true)
    expect(isFinancialActionAvailable('HOLD')).toBe(false)
    expect(isFinancialActionAvailable('REVIEW_REQUIRED')).toBe(false)
  })

  it('explains the member own next step without any reason code', () => {
    expect(financialHoldMessage('HOLD', 'ADD_DATE_OF_BIRTH')).toMatch(/date of birth/i)
    expect(financialHoldMessage('HOLD', 'GUARDIAN_CONSENT')).toMatch(/guardian/i)
    const review = financialHoldMessage('REVIEW_REQUIRED', 'WAIT_FOR_REVIEW') ?? ''
    expect(review).toMatch(/review/i)
    expect(review).toMatch(/nothing has been paid/i)   // never claims a payout happened
    expect(financialHoldMessage('ALLOWED', null)).toBeNull()
    expect(financialHoldMessage('HOLD', 'SOMETHING_ELSE')).toMatch(/review/i)
  })

  it('renders the generic 403 object instead of [object Object]', () => {
    const detail = { code: 'FINANCIAL_ACTION_UNAVAILABLE', message: 'x', next_step: 'ADD_DATE_OF_BIRTH' }
    expect(apiErrorText(detail, 'fallback')).toMatch(/date of birth/i)
    expect(apiErrorText({ code: 'PENDING_SAFETY_REVIEW', next_step: 'WAIT_FOR_REVIEW' }, 'f')).toMatch(/review/i)
    expect(apiErrorText('plain text', 'f')).toBe('plain text')
    expect(apiErrorText({ message: 'm' }, 'f')).toBe('m')
    expect(apiErrorText(undefined, 'f')).toBe('f')
  })
})
