/**
 * Nomination card call-to-action state.
 *
 * "Nobody was nominated in this round" and "you can nominate now" are different
 * facts: a zero count only invites a first nomination while the round's submission
 * window is open. A closed (historical) round shows a neutral, non-action state.
 */
export type NominationCtaState = 'be_first' | 'none' | 'view'

export function isNominationOpen(opts: {
  /** Selected round is past its submission window. */
  isRoundClosed?: boolean
  /** Backend authority: round.is_submission_open (undefined when not provided). */
  isSubmissionOpen?: boolean
  /** Vote view: nominating is never offered there. */
  isVoteMode?: boolean
}): boolean {
  if (opts.isVoteMode) return false
  if (opts.isRoundClosed) return false
  return opts.isSubmissionOpen !== false
}

export function nominationCtaState(opts: { contestants: number; nominationOpen: boolean }): NominationCtaState {
  if (opts.contestants > 0) return 'view'
  return opts.nominationOpen ? 'be_first' : 'none'
}
