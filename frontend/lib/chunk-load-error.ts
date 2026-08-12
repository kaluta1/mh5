const CHUNK_RELOAD_KEY = 'mh5_chunk_reload'

export function isChunkLoadError(error: unknown): boolean {
  if (!error) return false
  const msg =
    error instanceof Error
      ? `${error.name} ${error.message}`
      : typeof error === 'string'
        ? error
        : String(error)
  const lower = msg.toLowerCase()
  return (
    lower.includes('loading chunk') ||
    lower.includes('failed to fetch dynamically imported module') ||
    lower.includes('chunkloaderror') ||
    lower.includes('importing a module script failed')
  )
}

export function isNextStaticScript(url: string): boolean {
  return url.includes('/_next/static/')
}

export function clearCacheRedirectUrl(): string {
  if (typeof window === 'undefined') return '/clear-cache'
  const redirect = `${window.location.pathname}${window.location.search}`
  return `/clear-cache?redirect=${encodeURIComponent(redirect)}`
}

/**
 * Recover from stale Next.js chunks after deploy: reload once, then clear-cache redirect.
 */
export function recoverFromChunkLoadError(): void {
  if (typeof window === 'undefined') return

  try {
    if (!sessionStorage.getItem(CHUNK_RELOAD_KEY)) {
      sessionStorage.setItem(CHUNK_RELOAD_KEY, '1')
      window.location.reload()
      return
    }
  } catch {
    window.location.reload()
    return
  }

  window.location.href = clearCacheRedirectUrl()
}

export function clearChunkReloadFlag(): void {
  if (typeof window === 'undefined') return
  try {
    sessionStorage.removeItem(CHUNK_RELOAD_KEY)
  } catch {
    // ignore
  }
}
