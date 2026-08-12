import { cacheService } from '@/lib/cache-service'
import { clearCache as clearUploadFileCache } from '@/lib/utils/file-cache'

export type ClearAppCacheResult = {
  cleared: string[]
}

const SESSION_KEY_PATTERNS = [
  /^mh5[-_]/i,
  /^contestId$/,
  /^mh5_502_retry$/,
]

function shouldClearSessionKey(key: string): boolean {
  return SESSION_KEY_PATTERNS.some((pattern) => pattern.test(key))
}

/**
 * Clear stale browser caches while keeping login tokens and user preferences.
 * Safe for support URL https://myhigh5.com/clear-cache
 */
export async function clearAppCache(): Promise<ClearAppCacheResult> {
  const cleared: string[] = []

  if (typeof window === 'undefined') {
    return { cleared }
  }

  try {
    cacheService.clear()
    cleared.push('API response cache (api_cache)')
  } catch {
    /* ignore */
  }

  try {
    clearUploadFileCache()
    cleared.push('Upload file deduplication cache')
  } catch {
    /* ignore */
  }

  try {
    const keysToRemove: string[] = []
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i)
      if (key && shouldClearSessionKey(key)) {
        keysToRemove.push(key)
      }
    }
    keysToRemove.forEach((key) => sessionStorage.removeItem(key))
    if (keysToRemove.length > 0) {
      cleared.push(`Session flags (${keysToRemove.length} item(s))`)
    }
  } catch {
    /* ignore */
  }

  if (typeof caches !== 'undefined') {
    try {
      const names = await caches.keys()
      let deleted = 0
      for (const name of names) {
        if (await caches.delete(name)) {
          deleted += 1
        }
      }
      if (deleted > 0) {
        cleared.push(`Browser Cache API (${deleted} store(s))`)
      }
    } catch {
      /* ignore */
    }
  }

  return { cleared }
}
