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

/** Round IDs shown as Submit / Vote on the dashboard — not "past" archive. */
export function getActiveDashboardRoundIds(rounds: Round[]): Set<number> {
  const ids = new Set<number>()
  for (const { round } of computeDisplayRounds(rounds)) {
    const id = Number(round.id)
    if (!Number.isNaN(id)) ids.add(id)
  }
  return ids
}
