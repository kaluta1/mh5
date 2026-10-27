import api from '@/lib/api'

/** A member's short link as the API returns it (the owner is always the signed-in member). */
export type ShortLink = {
  id: number
  short_code: string
  short_url: string
  destination_url: string
  include_invitation: boolean
  is_active: boolean
  created_at: string | null
  disabled_at: string | null
  reused?: boolean
}

export type ShortLinkPage = { items: ShortLink[]; total: number }

/** Create a short link. `includeInvitation` only says whether to attach the caller's OWN invitation;
 * the server decides the owner and the code. */
export async function createShortLink(url: string, includeInvitation: boolean): Promise<ShortLink> {
  const { data } = await api.post<ShortLink>('/api/v1/share-links', {
    url: url.trim(),
    include_invitation: includeInvitation,
  })
  return data
}

export async function listShortLinks(limit = 50, offset = 0): Promise<ShortLinkPage> {
  const { data } = await api.get<ShortLinkPage>('/api/v1/share-links', { params: { limit, offset } })
  return data
}

export async function disableShortLink(id: number): Promise<ShortLink> {
  const { data } = await api.post<ShortLink>(`/api/v1/share-links/${id}/disable`)
  return data
}

/** The server's message for a refused request, or a plain fallback (never raw internals). */
export function shortLinkErrorMessage(error: unknown, fallback: string): string {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  if (response?.status === 429) return 'Too many requests. Please wait a minute and try again.'
  if (response?.status === 401) return 'Your session has expired. Please sign in again.'
  const detail = response?.data?.detail
  if (typeof detail === 'string' && detail.length > 0 && detail.length < 300) return detail
  return fallback
}

/** A quick client-side check before calling the server (the server's rules are the real ones). */
export function looksLikeMyHigh5Link(value: string): boolean {
  try {
    const url = new URL(value.trim())
    return (url.protocol === 'https:' || url.protocol === 'http:') && /(^|\.)myhigh5\.com$/i.test(url.hostname)
  } catch {
    return false
  }
}
