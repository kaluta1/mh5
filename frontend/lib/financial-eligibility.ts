// Child/Teen Safety Phase 10: the member's OWN prize/financial eligibility.
// The backend is authoritative (every writer re-checks); this only explains a
// held/under-review state. No reason codes are ever received or shown.

export type FinancialEligibilityStatus = 'ALLOWED' | 'HOLD' | 'REVIEW_REQUIRED'

export type FinancialNextStep =
  | 'ADD_DATE_OF_BIRTH'
  | 'VERIFY_AGE'
  | 'GUARDIAN_CONSENT'
  | 'COMPLETE_KYC'
  | 'WAIT_FOR_REVIEW'

const NEXT_STEP_TEXT: Record<FinancialNextStep, string> = {
  ADD_DATE_OF_BIRTH: 'Add your date of birth in your profile to continue.',
  VERIFY_AGE: 'Stronger age verification is needed before this can continue.',
  GUARDIAN_CONSENT: 'A verified parent or guardian needs to give consent first.',
  COMPLETE_KYC: 'Complete identity verification to continue.',
  WAIT_FOR_REVIEW: 'This needs a safety review. Nothing has been paid or moved in the meantime.',
}

export function isFinancialActionAvailable(status?: string | null): boolean {
  // Older backends did not send a status: the server still enforces the rule.
  return !status || status === 'ALLOWED'
}

export function financialHoldMessage(status?: string | null, nextStep?: string | null): string | null {
  if (isFinancialActionAvailable(status)) return null
  const step = (nextStep || 'WAIT_FOR_REVIEW') as FinancialNextStep
  return NEXT_STEP_TEXT[step] ?? NEXT_STEP_TEXT.WAIT_FOR_REVIEW
}

/** Turns an API error `detail` (string or the generic Phase 10 object) into text. */
export function apiErrorText(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: unknown; next_step?: unknown; code?: unknown }
    if (d.code === 'FINANCIAL_ACTION_UNAVAILABLE' || d.code === 'PENDING_SAFETY_REVIEW') {
      const status = d.code === 'PENDING_SAFETY_REVIEW' ? 'REVIEW_REQUIRED' : 'HOLD'
      return financialHoldMessage(status, typeof d.next_step === 'string' ? d.next_step : null) ?? fallback
    }
    if (typeof d.message === 'string' && d.message) return d.message
  }
  return fallback
}
