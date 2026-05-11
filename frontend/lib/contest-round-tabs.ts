import type { Round } from "@/lib/api-service"
import { isRoundVotingLive } from "@/lib/is-round-voting-live"

export type RoundTabKind = "nominate" | "vote" | "combined"

/**
 * Same round pills as the contests dashboard: current nomination month + live vote round
 * (or a single combined tab when they are the same round).
 */
export function computeDisplayRounds(rounds: Round[]): Array<{ round: Round; pill: string; kind: RoundTabKind }> {
  if (!rounds?.length) return []
  const voteRound = rounds.find((r: Round) => isRoundVotingLive(r, rounds))
  const now = new Date()
  const currentMonthStr = now.toLocaleDateString("en-US", { month: "long", year: "numeric" }).toLowerCase()
  const nominationRound =
    rounds.find((r: Round) => String(r.name || "").toLowerCase().includes(currentMonthStr)) || rounds[0]
  if (nominationRound && voteRound && Number(nominationRound.id) === Number(voteRound.id)) {
    return [{ round: nominationRound, pill: "Submit & Vote", kind: "combined" }]
  }
  const out: Array<{ round: Round; pill: string; kind: RoundTabKind }> = []
  const seen = new Set<number>()
  const push = (r: Round | undefined | null, pill: string, kind: RoundTabKind) => {
    if (!r) return
    const id = Number(r.id)
    if (Number.isNaN(id) || seen.has(id)) return
    seen.add(id)
    out.push({ round: r, pill, kind })
  }
  push(nominationRound, "Submit", "nominate")
  push(voteRound as Round | undefined, "Vote", "vote")
  return out.length
    ? out
    : rounds.map((r) => ({
        round: r,
        pill: isRoundVotingLive(r, rounds) ? "Vote" : "Submit",
        kind: (isRoundVotingLive(r, rounds) ? "vote" : "nominate") as RoundTabKind,
      }))
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
