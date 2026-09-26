import { afterEach, describe, expect, it, vi } from 'vitest'
import { closeMediaSession, openMediaSession } from './media-session'

describe('media session', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('binds the browser to the signed-in viewer with a credentialed request (no token in the URL)', async () => {
    window.localStorage.setItem('access_token', 'abc.def.ghi')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await openMediaSession()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/v1\/media\/session$/)
    expect(url).not.toContain('abc.def.ghi')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer abc.def.ghi')
  })

  it('does nothing when signed out, and clears the session on logout', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await openMediaSession()
    expect(fetchMock).not.toHaveBeenCalled()
    await closeMediaSession()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/v1\/media\/session$/)
    expect(init.method).toBe('DELETE')
  })

  it('never throws when the network fails', async () => {
    window.localStorage.setItem('access_token', 't')
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))
    await expect(openMediaSession()).resolves.toBeUndefined()
    await expect(closeMediaSession()).resolves.toBeUndefined()
  })
})
