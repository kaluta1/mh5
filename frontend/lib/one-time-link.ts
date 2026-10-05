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

export interface LinkCredential {
  /** The credential to exchange, or '' when there is none that can be used. */
  token: string
  /**
   * 'current'  a well-formed credential in the fragment (returned in `token`);
   * 'legacy'   a `?token=` query parameter from an email sent before this flow.
   *            Those tokens are no longer accepted: it is discarded, never sent;
   * 'invalid'  a fragment that is not a credential;
   * 'none'     the page was opened without any link credential.
   */
  kind: 'current' | 'legacy' | 'invalid' | 'none'
}

/**
 * Reads the link credential from the current URL and scrubs the URL: the
 * fragment is removed, and so is a `token` query parameter.
 */
export function takeLink(win: LinkWindow | undefined = typeof window !== 'undefined' ? window : undefined): LinkCredential {
  if (!win) return { token: '', kind: 'none' }
  const hash = win.location.hash || ''
  const token = readFragmentToken(hash)
  const query = new URLSearchParams(win.location.search || '')
  const hadQueryToken = query.has('token')
  if (hash || hadQueryToken) {
    query.delete('token')
    const rest = query.toString()
    try {
      win.history.replaceState(win.history.state ?? null, '', win.location.pathname + (rest ? `?${rest}` : ''))
    } catch {
      // Scrubbing the address bar is best effort; the exchange still happens.
    }
  }
  if (token) return { token, kind: 'current' }
  if (hadQueryToken) return { token: '', kind: 'legacy' }
  if (hash.replace(/^#/, '')) return { token: '', kind: 'invalid' }
  return { token: '', kind: 'none' }
}

/** The credential alone ('' when there is none or it cannot be used). */
export function takeLinkToken(win: LinkWindow | undefined = typeof window !== 'undefined' ? window : undefined): string {
  return takeLink(win).token
}
