/**
 * Calls /api/i18n/translate with transient-error retries (502/429).
 * Returns null if the service is not configured (503) or after retries fail.
 */
export async function fetchTranslatedChunk(
  targetLocale: string,
  entries: Record<string, string>,
  signal: AbortSignal,
): Promise<Record<string, string> | null> {
  const maxAttempts = 3
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const res = await fetch("/api/i18n/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targetLocale, entries }),
      signal,
    })

    if (res.status === 503) {
      return null
    }

    if (res.ok) {
      const data = (await res.json()) as { translations?: Record<string, string> }
      return data.translations ?? {}
    }

    if (attempt < maxAttempts && (res.status === 502 || res.status === 429)) {
      await new Promise((r) => setTimeout(r, 350 * attempt))
      continue
    }

    return null
  }
  return null
}
