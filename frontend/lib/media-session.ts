/**
 * Child/Teen Safety Phase 7: protected entry media (<img>/<video>) cannot send an
 * Authorization header, so the backend binds the browser to the signed-in viewer
 * with an HttpOnly, SameSite=Strict cookie scoped to the media route. Media URLs
 * only carry a viewer-bound grant that is useless without this session, so no
 * reusable credential ever appears in a URL or a web-server access log.
 *
 * The call targets the same origin the media is loaded from (see mediaApiOrigin),
 * so the cookie is stored for exactly that host.
 */
import { mediaApiOrigin } from './media-url'

const SESSION_PATH = '/api/v1/media/session'

export async function openMediaSession(): Promise<void> {
  if (typeof window === 'undefined') return
  let token: string | null = null
  try {
    token = window.localStorage.getItem('access_token')
  } catch {
    token = null
  }
  if (!token) return
  try {
    await fetch(`${mediaApiOrigin()}${SESSION_PATH}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      credentials: 'include',
      cache: 'no-store',
    })
  } catch {
    // Best effort: protected media simply stays unavailable until the next refresh.
  }
}

export async function closeMediaSession(): Promise<void> {
  if (typeof window === 'undefined') return
  try {
    await fetch(`${mediaApiOrigin()}${SESSION_PATH}`, { method: 'DELETE', credentials: 'include', cache: 'no-store' })
  } catch {
    // Best effort; the session also expires on its own (1 hour).
  }
}
