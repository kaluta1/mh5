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

/**
 * One state for a contest card, resolved from everything the card knows.
 *
 * The public participant count alone is not enough: a member whose own entry is
 * still on hold has a public count of 0, yet must never be told "Be the first
 * nominator!" next to an Edit button for the entry they already submitted.
 */
export type OwnEntryCardState = 'pending' | 'rejected' | 'live' | 'submitted'

export type ContestCardView =
  /** Zero public entries, nominating is open, viewer has no entry: invite the first nomination. */
  | 'be_first'
  /** Zero public nominations and nominating is not possible (closed round / Vote view). */
  | 'none'
  /** Show the "View N ..." action. */
  | 'view'
  /** Zero public entries but the viewer has their own entry: show its state instead. */
  | 'own'
  /** The count is not known (missing or failed): never treated as zero. */
  | 'count_unknown'

export interface ContestCardState {
  view: ContestCardView
  /** State of the viewer's own entry, or null when they have none. */
  own: OwnEntryCardState | null
}

export function ownEntryCardState(hasOwnEntry: boolean, status?: string | null): OwnEntryCardState | null {
  if (!hasOwnEntry) return null
  if (status === 'REJECTED') return 'rejected'
  if (status === 'PENDING_REVIEW') return 'pending'
  if (status === 'PUBLIC') return 'live'
  // The server did not say (older response, or the entry was created a moment ago).
  return 'submitted'
}

export function contestCardState(opts: {
  isNomination: boolean
  /** Public participant count; null/undefined/NaN means "not known". */
  contestants: number | null | undefined
  nominationOpen: boolean
  hasOwnEntry: boolean
  ownEntryStatus?: string | null
}): ContestCardState {
  const own = ownEntryCardState(opts.hasOwnEntry, opts.ownEntryStatus)
  const count = opts.contestants
  if (typeof count !== 'number' || !Number.isFinite(count) || count < 0) {
    return { view: 'count_unknown', own }
  }
  if (count > 0) return { view: 'view', own }
  if (own) return { view: 'own', own }
  if (!opts.isNomination) return { view: 'view', own }
  return { view: nominationCtaState({ contestants: count, nominationOpen: opts.nominationOpen }), own }
}
