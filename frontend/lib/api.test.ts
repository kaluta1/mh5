import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { AxiosResponse } from 'axios'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('axios', () => ({
  default: {
    create: () => ({
      get: mockGet,
      post: mockPost,
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    }),
  },
}))

vi.mock('./cache-service', () => ({
  cacheService: { clear: vi.fn() },
}))

vi.mock('./config', () => ({
  API_URL: 'https://example.com',
  getEffectiveApiUrl: () => 'https://example.com',
}))

vi.mock('./language-cookie', () => ({
  LANGUAGE_PREFERENCE_KEY: 'myhigh5-language',
}))

vi.mock('./locale-registry', () => ({
  LANGUAGE_CODES: ['en'],
}))

describe('apiService error handling', () => {
  beforeEach(() => {
    vi.resetModules()
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('throws when GET receives a 4xx response', async () => {
    mockGet.mockResolvedValue({
      status: 401,
      data: { detail: 'Unauthorized' },
      config: { url: '/api/v1/social/posts' },
    } as AxiosResponse)

    const { apiService } = await import('./api')
    await expect(apiService.get('/api/v1/social/posts')).rejects.toThrow('Unauthorized')
  })

  it('returns data when GET succeeds', async () => {
    mockGet.mockResolvedValue({
      status: 200,
      data: { posts: [{ id: 1 }] },
    } as AxiosResponse)

    const { apiService } = await import('./api')
    await expect(apiService.get('/api/v1/social/posts')).resolves.toEqual({ posts: [{ id: 1 }] })
  })

  it('throws when POST receives a 422 response', async () => {
    mockPost.mockResolvedValue({
      status: 422,
      data: { detail: 'Validation failed' },
      config: { url: '/api/v1/social/posts', method: 'post' },
    } as AxiosResponse)

    const { apiService } = await import('./api')
    await expect(apiService.post('/api/v1/social/posts', { content: '' })).rejects.toThrow(
      'Validation failed',
    )
  })
})

describe('sign-in on an unreliable connection', () => {
  const lost = () => Object.assign(new Error('timeout of 30000ms exceeded'), { code: 'ECONNABORTED' })
  const refused = (status: number) => Object.assign(new Error('Request failed'), { response: { status, data: {} } })

  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPost.mockReset()
    localStorage.clear()
  })

  it('repeats a sign-in that got no answer, once', async () => {
    mockPost.mockRejectedValueOnce(lost()).mockResolvedValueOnce({ status: 200, data: { access_token: 'tok' } })
    const { authService } = await import('./api')
    const signIn = authService.login({ email_or_username: 'a', password: 'b' })
    await vi.runAllTimersAsync()
    await expect(signIn).resolves.toEqual({ access_token: 'tok' })
    expect(mockPost).toHaveBeenCalledTimes(2)
    expect(localStorage.getItem('access_token')).toBe('tok')
  })

  it('never repeats a refused sign-in (wrong password)', async () => {
    mockPost.mockRejectedValueOnce(refused(401))
    const { authService } = await import('./api')
    await expect(authService.login({ email_or_username: 'a', password: 'b' })).rejects.toThrow()
    expect(mockPost).toHaveBeenCalledTimes(1)
  })

  it('withNetworkRetry repeats lost reads a bounded number of times and never a refusal', async () => {
    const { withNetworkRetry, isTransientNetworkError } = await import('./api')
    const read = vi.fn().mockRejectedValueOnce(lost()).mockRejectedValueOnce(lost()).mockResolvedValueOnce('me')
    const ok = withNetworkRetry(read)
    await vi.runAllTimersAsync()
    await expect(ok).resolves.toBe('me')
    expect(read).toHaveBeenCalledTimes(3)

    const alwaysLost = vi.fn().mockRejectedValue(lost())
    const failed = withNetworkRetry(alwaysLost).catch((e) => e)
    await vi.runAllTimersAsync()
    expect(isTransientNetworkError(await failed)).toBe(true)
    expect(alwaysLost).toHaveBeenCalledTimes(3)

    const denied = vi.fn().mockRejectedValue(refused(401))
    await expect(withNetworkRetry(denied)).rejects.toThrow()
    expect(denied).toHaveBeenCalledTimes(1)
  })
})
