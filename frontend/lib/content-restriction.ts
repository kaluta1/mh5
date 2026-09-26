/**
 * Child/Teen Safety Phase 7: the backend decides which entries a viewer may
 * receive. When it refuses one for age reasons it answers 403 with
 * `detail: { code: "CONTENT_RESTRICTED", reason, message }` and no content.
 * Hidden entries (held, under review, escalated...) are a plain 404.
 */
export type ContentRestrictionReason = 'SIGN_IN_REQUIRED' | 'AGE_REQUIRED' | 'AGE_RESTRICTED'

export interface ContentRestriction {
  reason: ContentRestrictionReason
  message: string
}

const FALLBACK_MESSAGES: Record<ContentRestrictionReason, string> = {
  SIGN_IN_REQUIRED: 'Sign in to view this content.',
  AGE_REQUIRED: 'Add your date of birth to your profile to view this content.',
  AGE_RESTRICTED: "This content isn't available for your account.",
}

export function getContentRestriction(err: unknown): ContentRestriction | null {
  const response = (err as { response?: { status?: number; data?: { detail?: unknown } } } | null)?.response
  const detail = response?.data?.detail as { code?: unknown; reason?: unknown; message?: unknown } | undefined
  if (response?.status !== 403 || !detail || typeof detail !== 'object' || detail.code !== 'CONTENT_RESTRICTED') {
    return null
  }
  const reason = (Object.keys(FALLBACK_MESSAGES) as ContentRestrictionReason[]).includes(
    detail.reason as ContentRestrictionReason,
  )
    ? (detail.reason as ContentRestrictionReason)
    : 'AGE_RESTRICTED'
  const message = typeof detail.message === 'string' && detail.message ? detail.message : FALLBACK_MESSAGES[reason]
  return { reason, message }
}
