/**
 * One-time links sent by email (email verification, password reset).
 *
 * The credential rides in the URL FRAGMENT (`/verify-email#token=...`). A
 * browser never sends a fragment to a server, so the credential is absent from
 * access logs, from proxies and from the Referer header. The page takes it,
 * removes it from the address bar and the history entry at once, and exchanges
 * it with a POST whose body carries it.
 */
import { readFragmentToken } from './guardian-consent'

type LinkWindow = {
  location: { hash: string; pathname: string; search: string }
  history: { replaceState: (data: unknown, unused: string, url?: string | URL | null) => void; state?: unknown }
}

/**
 * Returns the credential from the current URL's fragment ('' when there is
 * none or it is malformed) and scrubs the URL: the fragment is removed, and so
 * is a `token` query parameter. Links from emails sent before this flow put a
 * token in the query string; those tokens are no longer accepted, so one found
 * there is discarded, never used.
 */
export function takeLinkToken(win: LinkWindow | undefined = typeof window !== 'undefined' ? window : undefined): string {
  if (!win) return ''
  const token = readFragmentToken(win.location.hash || '')
  const query = new URLSearchParams(win.location.search || '')
  const hadQueryToken = query.has('token')
  if (win.location.hash || hadQueryToken) {
    query.delete('token')
    const rest = query.toString()
    try {
      win.history.replaceState(win.history.state ?? null, '', win.location.pathname + (rest ? `?${rest}` : ''))
    } catch {
      // Scrubbing the address bar is best effort; the exchange still happens.
    }
  }
  return token
}
