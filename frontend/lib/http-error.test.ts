import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { AxiosResponse } from 'axios'

vi.mock('./cache-service', () => ({
  cacheService: { clear: vi.fn() },
}))

describe('throwIfApiError', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('does not throw on 2xx responses', async () => {
    const { throwIfApiError } = await import('./http-error')
    const response = { status: 200, data: { ok: true } } as AxiosResponse
    expect(() => throwIfApiError(response)).not.toThrow()
  })

  it('throws on 4xx responses with detail message', async () => {
    const { throwIfApiError } = await import('./http-error')
    const response = {
      status: 422,
      data: { detail: 'Validation failed' },
      config: { url: '/api/v1/contact', method: 'post' },
    } as AxiosResponse

    expect(() => throwIfApiError(response)).toThrow('Validation failed')
  })

  it('throws on 401 responses', async () => {
    const { throwIfApiError } = await import('./http-error')
    const response = {
      status: 401,
      data: { detail: 'Unauthorized' },
      config: { url: '/api/v1/users/me', method: 'get' },
    } as AxiosResponse

    expect(() => throwIfApiError(response, 'Request failed')).toThrow('Unauthorized')
  })
})
