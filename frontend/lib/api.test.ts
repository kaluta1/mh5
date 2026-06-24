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
