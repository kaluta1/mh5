import api from '@/lib/api'

export type Json = Record<string, any>

export function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return typeof detail === 'string' ? detail : (detail as Json).message || JSON.stringify(detail)
  }
  return e instanceof Error ? e.message : 'Request failed'
}

export async function call(method: 'get' | 'post' | 'patch', url: string, body?: unknown, extra?: Json) {
  const res = await api.request({ method, url: `/api/v1/advertising${url}`, data: body, ...(extra || {}) })
  if (res.status >= 400) throw { response: res }
  return res.data
}

/** The browser's IANA time zone (falls back to UTC). */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

export function timeZones(current: string): string[] {
  let all: string[] = []
  try {
    all = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.('timeZone') || []
  } catch {
    all = []
  }
  const base = all.length ? all : ['UTC', 'Africa/Nairobi', 'Africa/Lagos', 'Europe/London', 'America/New_York', 'Asia/Dhaka']
  return Array.from(new Set(['UTC', current, ...base]))
}

/** Minutes between two `datetime-local` values (same zone), or null. */
export function durationMinutes(start: string, end: string): number | null {
  if (!start || !end) return null
  const a = Date.parse(`${start}:00Z`)
  const b = Date.parse(`${end}:00Z`)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null
  return Math.round((b - a) / 60000)
}

export function formatDuration(minutes: number | null): string {
  if (minutes == null) return ''
  if (minutes <= 0) return 'The end must be after the start'
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const mins = minutes % 60
  return [days ? `${days} day${days === 1 ? '' : 's'}` : '', hours ? `${hours} h` : '', mins ? `${mins} min` : '']
    .filter(Boolean).join(' ')
}
