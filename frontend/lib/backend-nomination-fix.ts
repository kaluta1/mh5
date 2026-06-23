import { getEffectiveApiUrl } from '@/lib/config'

let cachedHasFix: boolean | null = null
let pendingCheck: Promise<boolean> | null = null

/** Cached probe: production VPS without redeploy returns 404 on /api/v1/build-info. */
export async function backendHasNominationRosterFix(): Promise<boolean> {
  if (cachedHasFix !== null) return cachedHasFix
  if (pendingCheck) return pendingCheck

  pendingCheck = (async () => {
    try {
      const base = getEffectiveApiUrl().replace(/\/+$/, '')
      const res = await fetch(`${base}/api/v1/build-info`, { cache: 'no-store' })
      if (!res.ok) {
        cachedHasFix = false
        return false
      }
      const data = (await res.json()) as { build_id?: string }
      const bid = String(data?.build_id ?? '')
      cachedHasFix =
        bid.includes('nomination-roster-fix') ||
        bid.includes('nomination-category-scope') ||
        bid.includes('march-cohort-align') ||
        bid.includes('march-cohort-calendar')
      return cachedHasFix
    } catch {
      cachedHasFix = false
      return false
    } finally {
      pendingCheck = null
    }
  })()

  return pendingCheck
}

export function resetNominationBackendFixCache(): void {
  cachedHasFix = null
  pendingCheck = null
}
