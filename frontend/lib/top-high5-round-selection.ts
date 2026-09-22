/**
 * Top High5 shows FINALIZED historical results (frozen `top_high5_results`
 * rows) -- a fundamentally different question from "which cohort's vote is
 * open right now" (see contest-round-tabs.ts's cohortRoundForVoteGeographyLevel
 * / resolveVoteCalendarAnchorRound, used by the live Vote page under
 * app/dashboard/contests). Reusing that vote-calendar math to auto-select a
 * Top High5 round picked whichever cohort is CURRENTLY voting at a level --
 * one cohort too recent, always empty, since a round that hasn't closed has
 * no frozen rows yet. See the 2026-09-16 empty Country/Regional
 * investigation for the full trace.
 *
 * The backend's own GET /api/v1/seasons/top-high5 already resolves the
 * correct round -- the latest one with actual finalized rows for the
 * requested level -- whenever `round_id` is omitted (it queries
 * top_high5_results directly, the single most authoritative "is this
 * finalized" signal there is, immune to calendar edge cases). So this
 * module does not duplicate any calendar/completion logic: it only decides
 * whether the frontend has an explicit, user-intended round to honor, or
 * should defer to that backend resolution entirely.
 */

import { formatDate } from "./date-utils"
import type { Language } from "./locale-registry"

export interface TopHigh5RoundSelectionInput {
  /** Raw round_id from the URL (deep link) or the user's round-id text input, if any. */
  explicitRoundId?: string | number | null
}

/**
 * The round_id to send with a Top High5 request, or `undefined` to let the
 * backend pick the latest round with finalized results for the requested
 * level. An explicit round (deep link or user-typed) is always honored
 * as-is -- never silently remapped or recomputed -- so a manually selected
 * historical round keeps working exactly as before.
 */
export function resolveTopHigh5RequestRoundId({
  explicitRoundId,
}: TopHigh5RoundSelectionInput): number | undefined {
  if (explicitRoundId === null || explicitRoundId === undefined || explicitRoundId === "") {
    return undefined
  }
  const parsed = Number(explicitRoundId)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
}

/**
 * The round_id to request right after the user switches Top High5 levels.
 * Always `undefined` (auto): a round finalized for one level is not
 * necessarily finalized for another (e.g. Country closed for round 27 does
 * not mean Regional has closed for round 27 too), so carrying the previous
 * level's round over would silently show a wrong or empty result. Every
 * level switch re-resolves fresh via the backend.
 */
export function nextRoundIdOnLevelChange(): undefined {
  return undefined
}

/**
 * Placeholder text for the optional round-id override input, showing the
 * exact month + year the CURRENTLY SELECTED level defaults to when the
 * field is left blank -- e.g. "Round id (optional — showing June 2026)"
 * on the Country tab, "...showing May 2026" on Regional, etc. Per the
 * 2026-09-23 calendar-month fix, each level now targets exactly one
 * calendar-derived month (current month minus a fixed per-level offset --
 * never "per contest", never mixed), returned by the backend as
 * `target_month` (an ISO date, always the 1st of that month) on every
 * response for that level.
 *
 * `targetMonth` must be the target_month from a response that actually
 * matches the currently active level (callers are responsible for that --
 * see page.tsx, which only passes it through when `data.level ===
 * activeLevel`) so this never shows a stale month left over from a
 * level the user has already switched away from. Falls back to a plain
 * label when no matching response has been fetched yet (e.g. right after
 * switching levels, before the new request resolves).
 */
export function topHigh5RoundIdPlaceholder(
  targetMonth: string | null | undefined,
  language: Language,
): string {
  const fallback = "Round id (optional)"
  if (!targetMonth) return fallback
  const parsed = new Date(targetMonth)
  if (Number.isNaN(parsed.getTime())) return fallback
  const monthYear = formatDate(parsed, language, { month: "long", year: "numeric" })
  return `Round id (optional — showing ${monthYear})`
}
