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

/** Geography chip under the Vote pill → which calendar cohort (submission month). */
export type VoteGeographyLevel = "country" | "regional" | "continental" | "global"

/**
 * Months to subtract from the live vote round's submission month.
 * May vote + Country → May cohort; Regional → April; Continental → March; Global → Feb.
 */
const VOTE_LEVEL_SUBMISSION_MONTH_OFFSET: Record<VoteGeographyLevel, number> = {
  country: 0,
  regional: 1,
  continental: 2,
  global: 3,
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

/**
 * Under **Vote**, each level chip is a different nomination cohort month, not the same round id.
 * Vote pill stays on the live vote round (e.g. May); Country uses that month, Regional uses M-1, etc.
 */
export function cohortRoundForVoteGeographyLevel(
  voteRound: Round | undefined,
  level: VoteGeographyLevel | "all",
  rounds: Round[],
): Round | undefined {
  if (!voteRound || !rounds.length) return voteRound
  if (!level || level === "all") return voteRound

  const offset = VOTE_LEVEL_SUBMISSION_MONTH_OFFSET[level]
  const anchor = cohortAnchorDate(voteRound)
  if (!anchor) return voteRound

  const targetMonth = addCalendarMonths(anchor, offset)
  const match = rounds.find((r) => roundMatchesMonthYear(r, targetMonth))
  return match ?? voteRound
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

/** Submit-month round: current calendar month (highest id if duplicates) — never the live vote round. */
function pickNominationRound(rounds: Round[], voteRound: Round | undefined): Round | undefined {
  const now = new Date()
  const currentMonth = new Date(now.getFullYear(), now.getMonth(), 1)
  const currentMonthStr = now.toLocaleDateString("en-US", { month: "long", year: "numeric" }).toLowerCase()
  const notVote = (r: Round) => !voteRound || Number(r.id) !== Number(voteRound.id)

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
  const voteRound = rounds.find((r: Round) => isRoundVotingLive(r, rounds))
  const nominationRound = pickNominationRound(rounds, voteRound)

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
