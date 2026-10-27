import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/share-preview-server', () => ({ getServerApiBase: () => 'http://127.0.0.1:8001' }))

import { resolveShortLink, shortLinkUnavailablePage } from './short-link-proxy'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

const visit = (code: string, ua = 'Mozilla/5.0') =>
  resolveShortLink(new NextRequest(`https://myhigh5.com/s/${code}`, { headers: { 'user-agent': ua } }), code)

describe('short link proxy', () => {
  it('forwards an invitation redirect with its cookie, never cached', async () => {
    fetchMock.mockResolvedValue(new Response(null, {
      status: 302,
      headers: { location: 'https://myhigh5.com/feed/12?ref=INV1', 'set-cookie': 'mh5_ref=abc; HttpOnly; Path=/' },
    }))
    const r = await visit('Km9R4tQ')
    expect(r.status).toBe(302)
    expect(r.headers.get('location')).toBe('https://myhigh5.com/feed/12?ref=INV1')
    expect(r.headers.get('set-cookie')).toContain('mh5_ref=abc')
    expect(r.headers.get('cache-control')).toContain('no-store')
    expect(fetchMock.mock.calls[0][0]).toBe('http://127.0.0.1:8001/api/v1/l/Km9R4tQ')
    expect(fetchMock.mock.calls[0][1].redirect).toBe('manual')
  })

  it('forwards a neutral redirect without a cookie', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 302, headers: { location: 'https://myhigh5.com/faq' } }))
    const r = await visit('Ab7kP2x')
    expect(r.status).toBe(302)
    expect(r.headers.get('set-cookie')).toBeNull()
  })

  it('passes the visitor user agent so crawlers get the preview route upstream', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 302, headers: { location: 'https://myhigh5.com/s/f/12' } }))
    await visit('Ab7kP2x', 'facebookexternalhit/1.1')
    expect(fetchMock.mock.calls[0][1].headers['user-agent']).toBe('facebookexternalhit/1.1')
  })

  it('shows the branded page for unknown or disabled links, without calling home', async () => {
    fetchMock.mockResolvedValue(new Response('{"code":"SHORT_LINK_UNAVAILABLE"}', { status: 404 }))
    const r = await visit('Zz9Zz9Z')
    expect(r.status).toBe(404)
    expect(r.headers.get('location')).toBeNull()
    const html = await r.text()
    expect(html).toContain('This link is not available')
    expect(html).toContain('prefers-color-scheme: dark')
    expect(r.headers.get('cache-control')).toBe('no-store')
  })

  it('refuses malformed codes before any upstream call', async () => {
    for (const code of ['', 'a/b', '../x', 'x'.repeat(40)]) {
      expect((await visit(code)).status).toBe(404)
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('answers an upstream failure with the branded page, never internals', async () => {
    fetchMock.mockRejectedValue(new Error('ECONNREFUSED 127.0.0.1:8001'))
    const r = await visit('Ab7kP2x')
    expect(r.status).toBe(502)
    expect(await r.text()).not.toContain('ECONNREFUSED')
  }, 10000)

  it('the unavailable page is mobile-ready', async () => {
    const html = await shortLinkUnavailablePage().text()
    expect(html).toContain('width=device-width')
    expect(html).toContain('noindex')
  })
})
