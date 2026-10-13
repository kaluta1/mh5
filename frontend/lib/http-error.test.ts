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

  it('reads the reason of a refusal that carries a code', async () => {
    const { throwIfApiError } = await import('./http-error')
    const response = {
      status: 403,
      data: { detail: { code: 'PERMISSION_REQUIRED', message: 'The manage_administrators permission is required.' } },
      config: { url: '/api/v1/admin/users/7/role', method: 'put' },
    } as AxiosResponse
    expect(() => throwIfApiError(response, 'Request failed')).toThrow('The manage_administrators permission is required.')
    const empty = { status: 403, data: { detail: { code: 'X' } }, config: { url: '/x' } } as AxiosResponse
    expect(() => throwIfApiError(empty, 'Request failed')).toThrow('Request failed')
  })
})

describe('the session', () => {
  const TOKEN = 'synthetic-session-token'
  const answer = (status: number, url: string) =>
    ({ status, data: { detail: 'x' }, config: { url, method: 'get' } }) as AxiosResponse

  beforeEach(() => {
    vi.resetModules()
    localStorage.setItem('access_token', TOKEN)
    localStorage.setItem('refresh_token', TOKEN)
  })

  it('is kept when an action is refused (403): the user is signed in and simply may not do that', async () => {
    const { logApiResponseStatus, throwIfApiError } = await import('./http-error')
    const signedOut = vi.fn()
    window.addEventListener('auth:unauthorized', signedOut)
    for (const status of [400, 403, 404, 409, 422, 429]) {
      logApiResponseStatus(answer(status, '/api/v1/admin/finance/settings'))
      expect(() => throwIfApiError(answer(status, '/api/v1/admin/users/7/role'))).toThrow()
    }
    expect(localStorage.getItem('access_token')).toBe(TOKEN)
    expect(localStorage.getItem('refresh_token')).toBe(TOKEN)
    expect(signedOut).not.toHaveBeenCalled()
    window.removeEventListener('auth:unauthorized', signedOut)
  })

  it('ends when the session itself is not valid (401), but not on a failed sign-in attempt', async () => {
    const { logApiResponseStatus } = await import('./http-error')
    const { cacheService } = await import('./cache-service')
    const signedOut = vi.fn()
    window.addEventListener('auth:unauthorized', signedOut)
    logApiResponseStatus(answer(401, '/api/v1/auth/login'))                // wrong password while signing in
    logApiResponseStatus(answer(401, '/api/v1/auth/register'))
    expect(localStorage.getItem('access_token')).toBe(TOKEN)
    expect(signedOut).not.toHaveBeenCalled()
    logApiResponseStatus(answer(401, '/api/v1/users/me'))                  // expired, superseded or switched off
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
    expect(cacheService.clear).toHaveBeenCalled()
    expect(signedOut).toHaveBeenCalledTimes(1)
    window.removeEventListener('auth:unauthorized', signedOut)
  })
})
