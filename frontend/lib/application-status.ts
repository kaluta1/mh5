/**
 * Status shown to a member for their own application.
 *
 * `is_qualified` is a competition flag that defaults to true; it is not a
 * review outcome. Whether an entry is published comes from `public_status`
 * (owner-only field): an entry on hold is "pending", a rejected one is
 * "rejected", and one whose external video no longer exists is "unavailable"
 * -- none of these is ever "approved".
 */
export type ApplicationStatus = 'pending' | 'approved' | 'rejected' | 'unavailable'

export function applicationStatus(row: {
  is_qualified?: boolean | null
  public_status?: string | null
}): ApplicationStatus {
  if (row.public_status === 'REJECTED') return 'rejected'
  if (row.public_status === 'CREATIVE_UNAVAILABLE') return 'unavailable'
  if (row.public_status && row.public_status !== 'PUBLIC') return 'pending'
  return row.is_qualified ? 'approved' : 'pending'
}

/** The owner's entry exists but is not listed yet. */
export function ownEntryPendingReview(contest: { current_user_entry_status?: string | null } | null | undefined): boolean {
  return contest?.current_user_entry_status === 'PENDING_REVIEW'
}
