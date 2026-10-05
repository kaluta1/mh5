import { describe, expect, it, vi } from 'vitest'
import { takeLink, takeLinkToken } from './one-time-link'

const TOKEN = 'pK3v9sQ2xL7mN1bV5cX8zA4dF6gH0jRtYuIoPwEqSdF'
const LEGACY_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyQGV4YW1wbGUuY29tIn0.c2lnbmF0dXJl'

function fakeWindow(hash: string, search = '', pathname = '/verify-email') {
  const replaceState = vi.fn()
  return { win: { location: { hash, search, pathname }, history: { replaceState, state: { k: 1 } } }, replaceState }
}

describe('takeLinkToken', () => {
  it('reads the credential from the fragment and removes it from the address bar', () => {
    const { win, replaceState } = fakeWindow(`#token=${TOKEN}`)
    expect(takeLinkToken(win)).toBe(TOKEN)
    expect(replaceState).toHaveBeenCalledTimes(1)
    expect(replaceState).toHaveBeenCalledWith({ k: 1 }, '', '/verify-email')
    expect(JSON.stringify(replaceState.mock.calls)).not.toContain(TOKEN)
  })

  it('keeps unrelated query parameters', () => {
    const { win, replaceState } = fakeWindow(`#token=${TOKEN}`, '?lang=fr', '/reset-password')
    expect(takeLinkToken(win)).toBe(TOKEN)
    expect(replaceState).toHaveBeenCalledWith({ k: 1 }, '', '/reset-password?lang=fr')
  })

  it('never uses a token found in the query string, and scrubs it', () => {
    const { win, replaceState } = fakeWindow('', `?token=${TOKEN}&lang=fr`)
    expect(takeLinkToken(win)).toBe('')
    expect(replaceState).toHaveBeenCalledWith({ k: 1 }, '', '/verify-email?lang=fr')
  })

  it('prefers nothing over a malformed fragment', () => {
    for (const hash of ['#token=', '#token=short', '#token=has spaces in it!!', '#token=<script>alert(1)</script>', '#other=1']) {
      const { win } = fakeWindow(hash)
      expect(takeLinkToken(win)).toBe('')
    }
  })

  it('does nothing when there is no credential anywhere', () => {
    const { win, replaceState } = fakeWindow('', '?lang=fr')
    expect(takeLinkToken(win)).toBe('')
    expect(replaceState).not.toHaveBeenCalled()
  })

  it('still returns the credential when the history API refuses', () => {
    const { win } = fakeWindow(`#token=${TOKEN}`)
    win.history.replaceState = vi.fn(() => {
      throw new Error('SecurityError')
    })
    expect(takeLinkToken(win)).toBe(TOKEN)
  })

  it('is safe without a window (server render)', () => {
    expect(takeLinkToken(undefined)).toBe('')
  })
})

describe('takeLink', () => {
  it('tells a current link, an old link, a broken link and no link apart', () => {
    expect(takeLink(fakeWindow(`#token=${TOKEN}`).win)).toEqual({ token: TOKEN, kind: 'current' })
    expect(takeLink(fakeWindow('', `?token=${LEGACY_JWT}`).win)).toEqual({ token: '', kind: 'legacy' })
    expect(takeLink(fakeWindow('#token=short').win)).toEqual({ token: '', kind: 'invalid' })
    expect(takeLink(fakeWindow('', '').win)).toEqual({ token: '', kind: 'none' })
    expect(takeLink(fakeWindow('#', '').win)).toEqual({ token: '', kind: 'none' })
    expect(takeLink(undefined)).toEqual({ token: '', kind: 'none' })
  })

  it('never returns a legacy query-string token, in any shape, and always scrubs it', () => {
    for (const search of [`?token=${LEGACY_JWT}`, `?token=${TOKEN}`, `?lang=fr&token=${LEGACY_JWT}`, '?token=']) {
      const { win, replaceState } = fakeWindow('', search, '/reset-password')
      const link = takeLink(win)
      expect(link).toEqual({ token: '', kind: 'legacy' })
      const scrubbed = String(replaceState.mock.calls[0][2])
      expect(scrubbed).not.toContain('token')
      expect(scrubbed.startsWith('/reset-password')).toBe(true)
    }
  })

  it('a fragment credential wins over a legacy query token, and both are scrubbed', () => {
    const { win, replaceState } = fakeWindow(`#token=${TOKEN}`, `?token=${LEGACY_JWT}`)
    expect(takeLink(win)).toEqual({ token: TOKEN, kind: 'current' })
    expect(replaceState).toHaveBeenCalledWith({ k: 1 }, '', '/verify-email')
  })
})
