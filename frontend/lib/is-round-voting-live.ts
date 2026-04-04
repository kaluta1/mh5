type RoundVotingFields = {
  id: number
  is_voting_open?: boolean
  status?: string
  voting_start_date?: string | null
  voting_end_date?: string | null
}

/**
 * True only when the round is in an active voting window for UI (e.g. "VOTE NOW").
 * - Uses status + voting dates (voting_end_date is often the global season end, so it alone cannot end old months).
 * - When `allRounds` is provided, only the latest round (max id) among those flagged open stays eligible,
 *   so stale is_voting_open on past months (Jan/Feb) does not show the label once a newer month is live.
 */
export function isRoundVotingLive(round: RoundVotingFields, allRounds?: RoundVotingFields[]): boolean {
  if (!round.is_voting_open) return false
  if (round.status === 'completed') return false

  if (allRounds && allRounds.length > 0) {
    const candidates = allRounds.filter((r) => r.is_voting_open && r.status !== 'completed')
    if (candidates.length === 0) return false
    const maxId = Math.max(...candidates.map((r) => r.id))
    if (round.id !== maxId) return false
  }

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
