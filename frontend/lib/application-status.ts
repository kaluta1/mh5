/**
 * Status shown to a member for their own application.
 *
 * `is_qualified` is a competition flag that defaults to true; it is not a
 * review outcome. Whether an entry is published comes from `public_status`
 * (owner-only field): an entry still on hold is "pending" and a rejected one
 * is "rejected" -- neither is ever "approved".
 */
export type ApplicationStatus = 'pending' | 'approved' | 'rejected'

export function applicationStatus(row: {
  is_qualified?: boolean | null
  public_status?: string | null
}): ApplicationStatus {
  if (row.public_status === 'REJECTED') return 'rejected'
  if (row.public_status && row.public_status !== 'PUBLIC') return 'pending'
  return row.is_qualified ? 'approved' : 'pending'
}

/** The owner's entry exists but is not listed yet. */
export function ownEntryPendingReview(contest: { current_user_entry_status?: string | null } | null | undefined): boolean {
  return contest?.current_user_entry_status === 'PENDING_REVIEW'
}
