import type { AxiosResponse } from 'axios'
import { cacheService } from './cache-service'

function extractErrorMessage(
  data: unknown,
  fallback: string,
): string {
  if (!data || typeof data !== 'object') return fallback
  const record = data as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail
  // A refusal with a reason: { detail: { code, message } }.
  if (record.detail && typeof record.detail === 'object' && !Array.isArray(record.detail)) {
    const message = (record.detail as Record<string, unknown>).message
    if (typeof message === 'string' && message.trim()) return message
  }
  if (typeof record.message === 'string') return record.message
  if (Array.isArray(record.detail) && record.detail.length > 0) {
    const first = record.detail[0] as { msg?: string } | string
    return typeof first === 'string' ? first : first?.msg || fallback
  }
  return fallback
}

/**
 * 401 and 403 are different things and only one of them ends the session.
 *
 * 401: the session itself is not valid (no token, an expired or superseded
 *      one, an account that was switched off). The stored token is useless:
 *      it is removed and the app is told the user is signed out.
 * 403: the user IS signed in and this one action is refused: a permission
 *      they do not hold, a wrong confirmation password, a rule. Their session
 *      is intact and stays. Signing an administrator out because the server
 *      said "you may not do that" would lose their work and tell them nothing.
 */
function clearSessionIfUnauthorized(response: AxiosResponse): void {
  if (response.status !== 401) return
  const url = response.config?.url || ''
  const isAuthAttempt = /\/auth\/(login|register)/.test(url)
  if (isAuthAttempt || typeof window === 'undefined') return

  try {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  } catch {
    // localStorage unavailable (SSR/tests)
  }
  cacheService.clear()
  window.dispatchEvent(new CustomEvent('auth:unauthorized'))
}

/** axios validateStatus accepts 4xx — treat as errors so UI can show messages. */
export function throwIfApiError(
  response: AxiosResponse,
  fallback = 'Request failed',
): void {
  if (response.status < 400) return

  clearSessionIfUnauthorized(response)

  const err: Error & { response?: AxiosResponse } = new Error(
    extractErrorMessage(response.data, fallback),
  )
  err.response = response
  throw err
}

export function logApiResponseStatus(response: AxiosResponse): AxiosResponse {
  if (response.status >= 400) {
    clearSessionIfUnauthorized(response)
  }
  return response
}
