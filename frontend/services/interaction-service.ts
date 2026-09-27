import api from '@/lib/api'

/** Phase 9 interaction safety: blocks, reports and the contact check. The
 * backend decides every write; these calls only let the UI reflect it. */

export type ReportReason =
  | 'SPAM'
  | 'HARASSMENT'
  | 'INAPPROPRIATE_CONTENT'
  | 'PERSONAL_INFORMATION'
  | 'CHILD_SAFETY'
  | 'OTHER'

export interface ContactStatus {
  user_id: number
  can_message: boolean
  blocked_by_me: boolean
}

export const INTERACTION_UNAVAILABLE_MESSAGE = "Messaging isn't available with this member."

/** A safe, human-readable message for an interaction API error (never a raw object). */
export function interactionErrorMessage(error: any, fallback = 'Something went wrong. Please try again.'): string {
  const detail = error?.response?.data?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    if (detail.code === 'INTERACTION_UNAVAILABLE') return INTERACTION_UNAVAILABLE_MESSAGE
    if (typeof detail.message === 'string') return detail.message
  }
  if (typeof detail === 'string') return detail
  return fallback
}

async function checked<T>(request: Promise<{ status: number; data: T }>): Promise<T> {
  const response = await request
  if (response.status >= 400) {
    const error: any = new Error('Request failed')
    error.response = response
    throw error
  }
  return response.data
}

export const interactionService = {
  contactStatus: (userId: number) => checked<ContactStatus>(api.get(`/api/v1/interactions/contact/${userId}`)),
  block: (userId: number) => checked(api.post(`/api/v1/interactions/blocks/${userId}`)),
  unblock: (userId: number) => checked(api.delete(`/api/v1/interactions/blocks/${userId}`)),
  report: (targetType: 'comment' | 'message' | 'user', targetId: number, reason: ReportReason) =>
    checked(api.post('/api/v1/interactions/reports', { target_type: targetType, target_id: targetId, reason })),
}
