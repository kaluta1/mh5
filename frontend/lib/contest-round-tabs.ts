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

/**
 * Rounds to hide from the **Past** archive dialog only.
 *
 * - Always exclude the **live vote** round (`isRoundVotingLive`).
 * - Exclude the **current Submit** round only when its title **starts with** the current
 *   month+year (e.g. `May 2026`). Do not use substring match: names like `April – May 2026`
 *   were matching `may 2026` and hiding April from the Past list.
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

  return ids
}
