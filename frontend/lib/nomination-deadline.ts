/**
 * Nomination closes at the later of:
 * - end of submission_end calendar day (+ NOMINATION_GRACE_HOURS)
 * - start of voting_start calendar day (+ NOMINATION_GRACE_HOURS)
 * Matches backend `ContestStatusService.round_nomination_closes_at`.
 */
export const NOMINATION_GRACE_HOURS = 0

export function getRoundNominationDeadlineMs(round: {
  submission_end_date?: string
  voting_start_date?: string
}): number | null {
  if (!round.submission_end_date) return null
  const graceMs = NOMINATION_GRACE_HOURS * 60 * 60 * 1000
  const sub = new Date(round.submission_end_date)
  const endOfSubDay = new Date(sub)
  endOfSubDay.setHours(23, 59, 59, 999)
  let endMs = endOfSubDay.getTime() + graceMs
  if (round.voting_start_date) {
    const v = new Date(round.voting_start_date)
    const startVoteDay = new Date(v.getFullYear(), v.getMonth(), v.getDate(), 0, 0, 0, 0).getTime()
    endMs = Math.max(endMs, startVoteDay + graceMs)
  }
  return endMs
}
