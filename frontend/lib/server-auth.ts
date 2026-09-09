import { getServerApiBase } from '@/lib/share-preview-server'

export async function hasValidBackendBearer(request: Request): Promise<boolean> {
  const authorization = request.headers.get('authorization') || ''
  if (!/^Bearer\s+\S+$/i.test(authorization)) return false
  const base = getServerApiBase().replace(/\/+$/, '')
  const endpoint = base.includes('/api/v1') ? `${base}/auth/me` : `${base}/api/v1/auth/me`
  try {
    const response = await fetch(endpoint, {
      headers: { Authorization: authorization },
      cache: 'no-store',
      signal: AbortSignal.timeout(10_000),
    })
    return response.ok
  } catch {
    return false
  }
}
