import { I18N_AI_CACHE_VERSION } from "@/lib/i18n-ai-constants"

type AiCachePayload = {
  v: number
  translations: Record<string, string>
}

function storageKey(locale: string) {
  return `mh5-i18n-ai:${I18N_AI_CACHE_VERSION}:${locale}`
}

/** Client-only */
export function loadAiTranslationFlat(locale: string): Record<string, string> {
  if (typeof window === "undefined") return {}
  try {
    const raw = localStorage.getItem(storageKey(locale))
    if (!raw) return {}
    const p = JSON.parse(raw) as AiCachePayload
    if (!p || p.v !== I18N_AI_CACHE_VERSION || !p.translations) return {}
    return p.translations
  } catch {
    return {}
  }
}

export function saveAiTranslationFlat(locale: string, flat: Record<string, string>) {
  if (typeof window === "undefined") return
  try {
    const payload: AiCachePayload = { v: I18N_AI_CACHE_VERSION, translations: flat }
    localStorage.setItem(storageKey(locale), JSON.stringify(payload))
  } catch {
    // Quota exceeded — ignore; UI still works in English
  }
}

export function mergeAiTranslationFlat(
  locale: string,
  partial: Record<string, string>,
): Record<string, string> {
  const cur = loadAiTranslationFlat(locale)
  const next = { ...cur, ...partial }
  saveAiTranslationFlat(locale, next)
  return next
}
