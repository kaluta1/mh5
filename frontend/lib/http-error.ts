import type { AxiosResponse } from 'axios'
import { cacheService } from './cache-service'

function extractErrorMessage(
  data: unknown,
  fallback: string,
): string {
  if (!data || typeof data !== 'object') return fallback
  const record = data as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail
  if (typeof record.message === 'string') return record.message
  if (Array.isArray(record.detail) && record.detail.length > 0) {
    const first = record.detail[0] as { msg?: string } | string
    return typeof first === 'string' ? first : first?.msg || fallback
  }
  return fallback
}

function clearSessionIfUnauthorized(response: AxiosResponse): void {
  if (response.status !== 401 && response.status !== 403) return
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
