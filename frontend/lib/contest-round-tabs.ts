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

/** Submit-month round: open submission, title match, or newest non-vote round — never reuse the live vote round. */
function pickNominationRound(rounds: Round[], voteRound: Round | undefined): Round | undefined {
  const now = new Date()
  const currentMonthStr = now.toLocaleDateString("en-US", { month: "long", year: "numeric" }).toLowerCase()
  const notVote = (r: Round) => !voteRound || Number(r.id) !== Number(voteRound.id)

  const byOpenSubmission = rounds.find((r) => notVote(r) && isSubmissionWindowOpen(r))
  if (byOpenSubmission) return byOpenSubmission

  const byName = rounds.find(
    (r) => notVote(r) && roundTitleStartsWithCurrentMonthYear(r.name, currentMonthStr),
  )
  if (byName) return byName

  const looseName = rounds.find(
    (r) => notVote(r) && String(r.name || "").toLowerCase().includes(currentMonthStr),
  )
  if (looseName) return looseName

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
