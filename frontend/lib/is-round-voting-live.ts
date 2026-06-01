type RoundVotingFields = {
  id: number
  is_voting_open?: boolean
  status?: string
  voting_start_date?: string | null
  voting_end_date?: string | null
  submission_end_date?: string | null
}

function parseDay(s?: string | null): Date | null {
  if (!s) return null
  const d = new Date(s.includes('T') ? s : `${s}T12:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Latest completed submission month among open vote rounds (e.g. May when today is June). */
function pickLiveVoteRound(candidates: RoundVotingFields[]): RoundVotingFields | null {
  if (!candidates.length) return null
  const today = new Date()
  const todayMid = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const scored = candidates
    .map((r) => {
      const end = parseDay(r.submission_end_date)
      const endMid = end
        ? new Date(end.getFullYear(), end.getMonth(), end.getDate())
        : null
      return { r, endMid }
    })
    .filter((x) => x.endMid && x.endMid <= todayMid)
  const pool = scored.length ? scored : candidates.map((r) => ({ r, endMid: parseDay(r.submission_end_date) }))
  pool.sort((a, b) => {
    const ta = a.endMid?.getTime() ?? 0
    const tb = b.endMid?.getTime() ?? 0
    if (tb !== ta) return tb - ta
    return b.r.id - a.r.id
  })
  return pool[0]?.r ?? null
}

/**
 * True only when the round is in an active voting window for UI (e.g. "VOTE NOW").
 * - Uses status + voting dates (voting_end_date is often the global season end, so it alone cannot end old months).
 * - When `allRounds` is provided, only the latest round (max id) among those flagged open stays eligible,
 *   so stale is_voting_open on past months (Jan/Feb) does not show the label once a newer month is live.
 */
function _calendarVotingWindowOpen(round: RoundVotingFields): boolean {
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

export function isRoundVotingLive(round: RoundVotingFields, allRounds?: RoundVotingFields[]): boolean {
  if (round.status === 'completed') return false
  const calendarOpen =
    !!(round.voting_start_date && round.voting_end_date) && _calendarVotingWindowOpen(round)
  if (!round.is_voting_open && !calendarOpen) return false

  if (allRounds && allRounds.length > 0) {
    const flagged = allRounds.filter(
      (r) => r.status !== 'completed' && Boolean(r.is_voting_open),
    )
    if (flagged.length > 0) {
      const live = pickLiveVoteRound(flagged)
      if (live) return round.id === live.id
    }
    const candidates = allRounds.filter((r) => {
      const cal =
        !!(r.voting_start_date && r.voting_end_date) && _calendarVotingWindowOpen(r)
      return (Boolean(r.is_voting_open) || cal) && r.status !== 'completed'
    })
    if (candidates.length === 0) return false
    const live = pickLiveVoteRound(candidates) ?? candidates.sort((a, b) => b.id - a.id)[0]
    if (round.id !== live.id) return false
  }

  return Boolean(round.is_voting_open) || _calendarVotingWindowOpen(round)
}
