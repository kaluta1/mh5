/**
 * Display helpers for the guardian-consent pages. No eligibility or consent
 * logic lives here: the backend is authoritative.
 */

export const GUARDIAN_SCOPE_LABELS: Record<string, string> = {
  ACCOUNT_PARTICIPATION: 'Create and use a MyHigh5 account (required to approve)',
  PUBLIC_CREATIVE_DISPLAY: 'Show their creatives publicly',
  NAME_DISPLAY: 'Show their name publicly',
  CITY_COUNTRY_DISPLAY: 'Show their city and country publicly',
  CONTEST_ENTRY: 'Enter contests',
  STAGE_ADVANCEMENT: 'Advance to higher contest stages',
  MEDIA_USE: 'Use of their photos and videos',
  PUBLICITY: 'Publicity',
  PRIZE_ACCEPTANCE: 'Accept prizes',
  FINANCIAL_PAYMENT: 'Receive payments',
  PROMOTIONAL_CAMPAIGNS: 'Promotional campaigns',
}

/** Reads `token` from a URL fragment such as "#token=abc". */
export function readFragmentToken(hash: string): string {
  const params = new URLSearchParams((hash || '').replace(/^#/, ''))
  const token = params.get('token') || ''
  return /^[A-Za-z0-9_-]{10,200}$/.test(token) ? token : ''
}
