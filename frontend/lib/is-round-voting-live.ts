/**
 * True only when the round is in an active voting window for UI (e.g. "VOTE NOW").
 * Uses status + voting dates so ended months (Jan/Feb) do not show the label when March is live.
 */
export function isRoundVotingLive(round: {
  is_voting_open?: boolean
  status?: string
  voting_start_date?: string | null
  voting_end_date?: string | null
}): boolean {
  if (!round.is_voting_open) return false
  if (round.status === 'completed') return false

  const today = new Date()
  const todayMid = new Date(today.getFullYear(), today.getMonth(), today.getDate())

  const endRaw = round.voting_end_date
  if (endRaw) {
    const end = new Date(endRaw)
    if (!Number.isNaN(end.getTime())) {
      const endDay = new Date(end.getFullYear(), end.getMonth(), end.getDate())
      if (todayMid > endDay) return false
    }
  }

  const startRaw = round.voting_start_date
  if (startRaw) {
    const start = new Date(startRaw)
    if (!Number.isNaN(start.getTime())) {
      const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate())
      if (todayMid < startDay) return false
    }
  }

  return true
}
