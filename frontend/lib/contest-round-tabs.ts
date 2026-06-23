import type { Round } from "@/lib/api-service"
import { isRoundVotingLive } from "@/lib/is-round-voting-live"

export type RoundTabKind = "nominate" | "vote"

export type DisplayRoundTab = {
  round: Round
  pill: string
  kind: RoundTabKind
  /** Unique pill id — `${kind}:${roundId}` so Submit and Vote stay separate even for the same round row. */
  tabKey: string
}

export function roundTabKey(kind: RoundTabKind, roundId: number): string {
  return `${kind}:${roundId}`
}

/** Geography chip under the Vote pill → which nomination cohort month (M), not the vote month V. */
export type VoteGeographyLevel = "country" | "regional" | "continental" | "global"

/** Official nomination launch — cohorts before this month are ignored in Vote UI. */
export const OFFICIAL_NOMINATION_START = new Date(2026, 2, 1) // 1 March 2026

/**
 * Vote month V shows cohort M where M + phaseOffset = V (backend nomination calendar).
 *   Country vote for cohort M opens M+1  → offset 1
 *   Regional for M opens M+2             → offset 2
 *   Continental for M opens M+3        → offset 3
 *   Global for M opens M+4               → offset 4
 *
 * Example: Vote anchor June 2026 → Country=May, Regional=April, Continental=March; Global from July.
 */
const VOTE_LEVEL_SUBMISSION_MONTH_OFFSET: Record<VoteGeographyLevel, number> = {
  country: 1,
  regional: 2,
  continental: 3,
  global: 4,
}

function addCalendarMonths(d: Date, deltaMonths: number): Date {
  const out = new Date(d.getFullYear(), d.getMonth(), 1)
  out.setMonth(out.getMonth() - deltaMonths)
  return out
}

export function cohortAnchorDate(round: Round): Date | null {
  const sub = parseDay(round.submission_start_date)
  if (sub) return new Date(sub.getFullYear(), sub.getMonth(), 1)
  const name = String(round.name || "")
    .toLowerCase()
    .replace(/^\s*(round|season)\s*#?\d*\s*[:-–—]?\s*/i, "")
    .trim()
  const m = name.match(
    /(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})/i,
  )
  if (!m) return null
  const months: Record<string, number> = {
    january: 0,
    february: 1,
    march: 2,
    april: 3,
    may: 4,
    june: 5,
    july: 6,
    august: 7,
    september: 8,
    october: 9,
    november: 10,
    december: 11,
  }
  const mo = months[m[1].toLowerCase()]
  if (mo === undefined) return null
  return new Date(parseInt(m[2], 10), mo, 1)
}

function roundMatchesMonthYear(round: Round, target: Date): boolean {
  const anchor = cohortAnchorDate(round)
  if (!anchor) return false
  return anchor.getFullYear() === target.getFullYear() && anchor.getMonth() === target.getMonth()
}

function monthStart(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

/**
 * Vote geography anchor V = **current calendar month** when a round exists (June in June 2026).
 * Cohort chips then resolve correctly:
 *   Country → May, Regional → April, Continental → March, Global hidden until July.
 * Falls back to the live DB vote round only when no current-month round exists.
 */
export function resolveVoteCalendarAnchorRound(
  rounds: Round[],
  now: Date = new Date(),
): Round | undefined {
  const currentMonth = monthStart(now)
  const matches = rounds.filter((r) => {
    const anchor = cohortAnchorDate(r)
    return anchor && monthStart(anchor).getTime() === currentMonth.getTime()
  })
  if (matches.length) {
    return [...matches].sort((a, b) => Number(b.id) - Number(a.id))[0]
  }
  return rounds.find((r) => isRoundVotingLive(r, rounds))
}

/** @deprecated alias — use resolveVoteCalendarAnchorRound for cohort math */
export function voteCalendarAnchorRound(
  rounds: Round[],
  now?: Date,
): Round | undefined {
  return resolveVoteCalendarAnchorRound(rounds, now)
}

/** Nomination cohort month (M) for a vote-round month V and geography chip. */
export function cohortMonthForVoteGeographyLevel(
  voteRound: Round | undefined,
  level: VoteGeographyLevel,
): Date | null {
  if (!voteRound) return null
  const anchor = cohortAnchorDate(voteRound)
  if (!anchor) return null
  const offset = VOTE_LEVEL_SUBMISSION_MONTH_OFFSET[level]
  return addCalendarMonths(anchor, offset)
}

/**
 * True when this Vote chip should appear: cohort on/after March 2026 and a matching round exists.
 * Global for the March cohort first opens in July (M+4) — hidden in May/June.
 */
export function isVoteGeographyLevelAvailable(
  voteRound: Round | undefined,
  level: VoteGeographyLevel,
  rounds: Round[],
): boolean {
  const cohortMonth = cohortMonthForVoteGeographyLevel(voteRound, level)
  if (!cohortMonth) return false
  if (cohortMonth < OFFICIAL_NOMINATION_START) return false
  const hasRound = rounds.some((r) => roundMatchesMonthYear(r, cohortMonth))
  if (!hasRound) return false
  const voteMonth = cohortAnchorDate(voteRound!)
  if (!voteMonth) return false
  // Country vote for M opens in M+1 = vote month when offset is 1, etc.
  const phaseOpenMonth = addCalendarMonths(cohortMonth, VOTE_LEVEL_SUBMISSION_MONTH_OFFSET[level])
  return monthStart(voteMonth).getTime() >= monthStart(phaseOpenMonth).getTime()
}

/**
 * Under **Vote**, each level chip is a different nomination cohort month, not the same round id.
 * Vote anchor is the current calendar month (e.g. June); Country uses May cohort, Regional April, …
 */
export function cohortRoundForVoteGeographyLevel(
  voteRound: Round | undefined,
  level: VoteGeographyLevel | "all",
  rounds: Round[],
): Round | undefined {
  if (!voteRound || !rounds.length) return voteRound
  if (!level || level === "all") return voteRound
  if (!isVoteGeographyLevelAvailable(voteRound, level, rounds)) return undefined

  const cohortMonth = cohortMonthForVoteGeographyLevel(voteRound, level)
  if (!cohortMonth) return undefined
  return rounds.find((r) => roundMatchesMonthYear(r, cohortMonth))
}

export function voteLevelCohortHint(
  voteRound: Round | undefined,
  level: VoteGeographyLevel,
  rounds: Round[],
): string | null {
  const r = cohortRoundForVoteGeographyLevel(voteRound, level, rounds)
  if (!r?.name) return null
  return r.name.replace(/^\s*round\s*/i, "").trim()
}

function isSubmissionWindowOpen(round: Round): boolean {
  if (round.is_submission_open) return true
  const b = roundScheduleBounds(round)
  if (!b) return false
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startDay = new Date(b.start.getFullYear(), b.start.getMonth(), b.start.getDate())
  const endDay = new Date(b.end.getFullYear(), b.end.getMonth(), b.end.getDate())
  return today >= startDay && today <= endDay
}

function sameCalendarMonth(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
}

function bestRoundForMonth(rounds: Round[], target: Date, notVote: (r: Round) => boolean): Round | undefined {
  const matches = rounds.filter((r) => {
    if (!notVote(r)) return false
    const anchor = cohortAnchorDate(r)
    return anchor ? sameCalendarMonth(anchor, target) : false
  })
  if (!matches.length) return undefined
  const open = matches.filter((r) => isSubmissionWindowOpen(r))
  const pool = open.length ? open : matches
  return pool.sort((a, b) => Number(b.id) - Number(a.id))[0]
}

/** Submit-month round: current calendar month — may share round id with Vote in same month. */
function pickNominationRound(
  rounds: Round[],
  voteRound: Round | undefined,
  calendarAnchor: Round | undefined,
): Round | undefined {
  const now = new Date()
  const currentMonth = new Date(now.getFullYear(), now.getMonth(), 1)
  const currentMonthStr = now.toLocaleDateString("en-US", { month: "long", year: "numeric" }).toLowerCase()
  const notVote = (r: Round) => {
    if (!voteRound) return true
    if (calendarAnchor && Number(r.id) === Number(calendarAnchor.id)) return true
    return Number(r.id) !== Number(voteRound.id)
  }

  const byMonth = bestRoundForMonth(rounds, currentMonth, notVote)
  if (byMonth) return byMonth

  const byOpenSubmission = [...rounds]
    .filter((r) => notVote(r) && isSubmissionWindowOpen(r))
    .sort((a, b) => Number(b.id) - Number(a.id))[0]
  if (byOpenSubmission) return byOpenSubmission

  const byName = rounds.find(
    (r) => notVote(r) && roundTitleStartsWithCurrentMonthYear(r.name, currentMonthStr),
  )
  if (byName) return byName

  const sorted = [...rounds].filter(notVote).sort((a, b) => Number(b.id) - Number(a.id))
  return sorted[0]
}

/**
 * Contests dashboard top pills: always separate **Submit** (nomination month) and **Vote** (live vote round).
 */
export function computeDisplayRounds(rounds: Round[]): DisplayRoundTab[] {
  if (!rounds?.length) return []
  const liveVote = rounds.find((r: Round) => isRoundVotingLive(r, rounds))
  const calendarAnchor = resolveVoteCalendarAnchorRound(rounds)
  const voteRound = calendarAnchor ?? liveVote
  const nominationRound = pickNominationRound(rounds, voteRound, calendarAnchor)

  const out: DisplayRoundTab[] = []
  const seen = new Set<string>()
  const push = (r: Round | undefined | null, pill: string, kind: RoundTabKind) => {
    if (!r) return
    const id = Number(r.id)
    if (Number.isNaN(id)) return
    const key = roundTabKey(kind, id)
    if (seen.has(key)) return
    seen.add(key)
    out.push({ round: r, pill, kind, tabKey: key })
  }

  push(nominationRound, "Submit", "nominate")
  push(voteRound, "Vote", "vote")

  if (out.length) return out

  return rounds.map((r) => {
    const kind: RoundTabKind = isRoundVotingLive(r, rounds) ? "vote" : "nominate"
    return {
      round: r,
      pill: kind === "vote" ? "Vote" : "Submit",
      kind,
      tabKey: roundTabKey(kind, r.id),
    }
  })
}

/**
 * True if the round's title is **primarily** the current calendar month+ year (en-US),
 * e.g. "May 2026…" — not a range like "April – May 2026" (would wrongly contain "may 2026").
 */
function roundTitleStartsWithCurrentMonthYear(name: string | undefined, currentMonthYearLower: string): boolean {
  if (!name?.trim() || !currentMonthYearLower.trim()) return false
  const target = currentMonthYearLower.toLowerCase().trim()
  const n = name
    .toLowerCase()
    .trim()
    .replace(/^\s*(round|season)\s*#?\d*\s*[:-–—]?\s*/i, "")
    .trim()
  return n.startsWith(target)
}

function parseDay(s?: string): Date | null {
  if (!s) return null
  const d = new Date(s.includes("T") ? s : `${s}T12:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Min/max calendar span from round date fields (same idea as Past archive dialog). */
function roundScheduleBounds(r: Round): { start: Date; end: Date } | null {
  const keys = ["submission_start_date", "submission_end_date", "voting_start_date", "voting_end_date"] as const
  const dates: Date[] = []
  for (const k of keys) {
    const d = parseDay(r[k])
    if (d) dates.push(d)
  }
  if (!dates.length) return null
  return {
    start: new Date(Math.min(...dates.map((x) => x.getTime()))),
    end: new Date(Math.max(...dates.map((x) => x.getTime()))),
  }
}

/**
 * Rounds to hide from the **Past** archive dialog only.
 *
 * - Always exclude the **live vote** round (`isRoundVotingLive`).
 * - Exclude the **current Submit** round when its title **starts with** the current
 *   month+year (e.g. `May 2026`), not substring match (avoids hiding `April – May 2026`).
 * - Exclude seasons that **start in the current calendar month** and are **still ongoing**
 *   (end ≥ today). That removes e.g. "May 2026" (May–Oct) from Past while keeping
 *   "March 2026" (Mar–May) which starts in March, not May.
 */
export function getPastArchiveExcludedRoundIds(rounds: Round[]): Set<number> {
  const ids = new Set<number>()
  if (!rounds?.length) return ids

  const voteRound = rounds.find((r: Round) => isRoundVotingLive(r, rounds))
  if (voteRound) {
    const id = Number(voteRound.id)
    if (!Number.isNaN(id)) ids.add(id)
  }

  const now = new Date()
  const currentMonthStr = now.toLocaleDateString("en-US", { month: "long", year: "numeric" }).toLowerCase()
  const nominationByName = rounds.find((r: Round) =>
    roundTitleStartsWithCurrentMonthYear(r.name, currentMonthStr),
  )
  if (nominationByName) {
    const id = Number(nominationByName.id)
    if (!Number.isNaN(id)) ids.add(id)
  }

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const tm = today.getMonth()
  const ty = today.getFullYear()

  for (const r of rounds) {
    const b = roundScheduleBounds(r)
    if (!b) continue
    const endDay = new Date(b.end.getFullYear(), b.end.getMonth(), b.end.getDate())
    if (endDay < today) continue
    if (b.start.getMonth() === tm && b.start.getFullYear() === ty) {
      const id = Number(r.id)
      if (!Number.isNaN(id)) ids.add(id)
    }
  }

  return ids
}
