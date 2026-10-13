/**
 * Privileged administrator actions (making somebody an administrator,
 * switching an administrator account, recording a payment by hand) are
 * authorized and refused by the server: an explicit permission, the acting
 * administrator's current password, and never on their own account. The pages
 * only collect the password and show the server's answer.
 */

/** What a manual payment must say about the money it stands for (server rule). */
export const GRANT_REASON_MIN_LENGTH = 10

/** The server's message for a refused action, whatever shape `detail` has. */
export function adminErrorText(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail ?? error?.data?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && typeof detail.message === 'string') {
    return detail.message
  }
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  return fallback
}

/** A reference to the payment that was received: required, and long enough to mean something. */
export function validGrantReason(value: string): boolean {
  return value.trim().replace(/\s+/g, ' ').length >= GRANT_REASON_MIN_LENGTH
}
