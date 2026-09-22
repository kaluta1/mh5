import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'

/**
 * Regression coverage for KALUTASOCIETY_FRONTEND_WRONG_API_ORIGIN: a build
 * with NEXT_PUBLIC_API_URL baked to one real domain (e.g. myhigh5.com),
 * served from a DIFFERENT real domain (e.g. kalutasociety.com), must still
 * call its own origin's /api -- not the baked one, which may point at an
 * entirely different, unrelated server. This is what caused login to fail
 * with "Network error. Please check your connection and try again."
 *
 * Each test stubs NEXT_PUBLIC_API_URL, resets modules, and re-imports
 * ./config fresh -- API_URL is computed once at module load from the env,
 * exactly like a real Next.js build bakes it in once.
 */

const originalLocation = window.location

function setPageLocation(url: string) {
  const parsed = new URL(url)
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      hostname: parsed.hostname,
      protocol: parsed.protocol,
      port: parsed.port,
      origin: parsed.origin,
      href: parsed.href,
    },
  })
}

async function loadConfigWithApiUrl(bakedApiUrl: string, nodeEnv: 'production' | 'development' = 'production') {
  vi.resetModules()
  vi.stubEnv('NEXT_PUBLIC_API_URL', bakedApiUrl)
  vi.stubEnv('NODE_ENV', nodeEnv)
  return await import('./config')
}

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('getEffectiveApiUrl', () => {
  it('rewrites to the page origin when the baked API URL is a DIFFERENT real domain (the exact production bug)', async () => {
    setPageLocation('https://kalutasociety.com/dashboard/top-high5')
    const { getEffectiveApiUrl } = await loadConfigWithApiUrl('https://myhigh5.com')
    expect(getEffectiveApiUrl()).toBe('https://kalutasociety.com')
  })

  it('rewrites the other direction too (baked kalutasociety.com, served from myhigh5.com)', async () => {
    setPageLocation('https://myhigh5.com/dashboard')
    const { getEffectiveApiUrl } = await loadConfigWithApiUrl('https://kalutasociety.com')
    expect(getEffectiveApiUrl()).toBe('https://myhigh5.com')
  })

  it('still rewrites when the baked API URL is stale localhost (pre-existing VPS-mistake case, unchanged)', async () => {
    setPageLocation('https://kalutasociety.com/dashboard')
    const { getEffectiveApiUrl } = await loadConfigWithApiUrl('http://localhost:8001')
    expect(getEffectiveApiUrl()).toBe('https://kalutasociety.com')
  })

  it('does NOT rewrite when the baked API URL already matches the page origin', async () => {
    setPageLocation('https://kalutasociety.com/dashboard')
    const { getEffectiveApiUrl } = await loadConfigWithApiUrl('https://kalutasociety.com')
    expect(getEffectiveApiUrl()).toBe('https://kalutasociety.com')
  })

  it('does NOT rewrite for local development (page itself is localhost)', async () => {
    setPageLocation('http://localhost:3001/dashboard')
    const { getEffectiveApiUrl } = await loadConfigWithApiUrl('http://localhost:8001', 'development')
    expect(getEffectiveApiUrl()).toBe('http://localhost:8001')
  })

  it('preserves https on the rewritten origin even if the baked URL was http', async () => {
    setPageLocation('https://kalutasociety.com/dashboard')
    const { getEffectiveApiUrl } = await loadConfigWithApiUrl('http://myhigh5.com')
    expect(getEffectiveApiUrl()).toBe('https://kalutasociety.com')
  })
})
