/**
 * Advertising placement rules (2026-11-01).
 *
 * - Ads only on an ALLOWLIST of public content routes; sensitive areas are excluded first
 *   (messages, settings, admin, wallet/withdrawals, payments/checkout, KYC/verification, nominee
 *   claim, auth, seller registration, the Annual Ads sponsor page).
 * - In-feed: one ad after every 5 organic items, at most 5 per page view (also across infinite-scroll
 *   batches: the position depends only on the organic index). Lists with fewer than 5 items show none;
 *   two ads are never adjacent and there are never more ads than organic items.
 * - Desktop: one sidebar banner where the layout has a sidebar. Mobile: no sidebar (in-feed only).
 */

export const IN_FEED_EVERY = 5
export const MAX_IN_FEED_PER_PAGE = 5

export type AdPageType =
  | 'CONTEST_LISTING'
  | 'CONTEST_ENTRY'
  | 'FEED'
  | 'POST'
  | 'DISCOVERY'
  | 'PROFILE'
  | 'MARKETPLACE'
export type AdSlotKind = 'SIDEBAR' | 'IN_FEED' | 'IN_CONTENT'

const EXCLUDED: RegExp[] = [
  /^\/dashboard\/messages(\/|$)/,
  /^\/dashboard\/settings(\/|$)/,
  /^\/dashboard\/admin(\/|$)/,
  /^\/admin(\/|$)/,
  /^\/dashboard\/wallet(\/|$)/,
  /^\/payout-wallet(\/|$)/,
  /^\/dashboard\/commissions(\/|$)/,
  /^\/dashboard\/ad-earnings(\/|$)/,
  /^\/dashboard\/advertise(\/|$)/,
  /^\/dashboard\/kyc(\/|$)/,
  /^\/kyc(\/|$)/,
  /^\/nominations\/claim(\/|$)/,
  /^\/dashboard\/sponsored(\/|$)/,
  /^\/(login|register|signup|forgot-password|reset-password|verify-email|auth)(\/|$)/,
  /(^|\/)(checkout|payment|payments|pay|cashout|withdraw|withdrawals)(\/|$)/,
  /^\/dashboard\/marketplace\/(seller|orders|checkout)/,
]

const ALLOWED: RegExp[] = [
  /^\/contests\/?$/,
  /^\/contests\/[^/]+\/entry\/[^/]+\/?$/,
  /^\/contestants\/[^/]+\/?$/,
  /^\/dashboard\/contests(\/[^/]+)?\/?$/,
  /^\/dashboard\/feed(\/[^/]+)?\/?$/,
  /^\/feed\/[^/]+\/?$/,
  /^\/dashboard\/groups\/?$/,
  /^\/clubs\/?$/,
  /^\/dashboard\/search\/?$/,
  /^\/dashboard\/leaders\/?$/,
  /^\/dashboard\/top-high5\/?$/,
  /^\/profile\/[^/]+\/?$/,
  /^\/dashboard\/marketplace\/?$/,
]

/** Is advertising allowed on this route at all? (Exclusions win.) */
export function isAdRoute(pathname: string | null | undefined): boolean {
  if (!pathname) return false
  const path = pathname.split('?')[0].split('#')[0] || '/'
  if (EXCLUDED.some((re) => re.test(path))) return false
  return ALLOWED.some((re) => re.test(path))
}

export type InterleavedItem<T> =
  | { kind: 'item'; item: T; index: number }
  | { kind: 'ad'; adIndex: number; key: string }

/** Number of in-feed ads for a list of n organic items. */
export function inFeedAdCount(n: number, every = IN_FEED_EVERY, max = MAX_IN_FEED_PER_PAGE): number {
  if (!Number.isFinite(n) || n < every) return 0
  return Math.min(max, Math.floor(n / every))
}

/** Organic items with an ad after items 5, 10, ... (max 5). Deterministic: depends only on the index. */
export function interleave<T>(items: T[], every = IN_FEED_EVERY, max = MAX_IN_FEED_PER_PAGE): InterleavedItem<T>[] {
  const out: InterleavedItem<T>[] = []
  const ads = inFeedAdCount(items.length, every, max)
  let placed = 0
  items.forEach((item, index) => {
    out.push({ kind: 'item', item, index })
    if (placed < ads && (index + 1) % every === 0) {
      out.push({ kind: 'ad', adIndex: placed, key: `ad-${placed}` })
      placed += 1
    }
  })
  return out
}
