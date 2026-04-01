/**
 * Nomination closes at the later of:
 * - end of submission_end calendar day + grace
 * - start of voting_start calendar day + grace
 * Matches backend `ContestStatusService.round_nomination_closes_at`.
 */
export const NOMINATION_GRACE_HOURS = 5

export function getRoundNominationDeadlineMs(round: {
  submission_end_date?: string
  voting_start_date?: string
  /** Backend sets this when MYHIGH5_NOMINATION_EXTENSION_UNTIL is active (operator extension, UTC). */
  nomination_extension_until?: string | null
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
  const extRaw = round.nomination_extension_until
  if (extRaw) {
    const extMs = new Date(extRaw).getTime()
    if (!Number.isNaN(extMs)) {
      endMs = Math.max(endMs, extMs)
    }
  }
  return endMs
}
