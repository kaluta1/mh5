import { Language, LANGUAGE_CODES } from './locale-registry'
import enBase from './translations/en.json'

/** Synchronous English bundle — always available on first paint (no async chunk). */
export const ENGLISH_TRANSLATIONS = enBase as Record<string, any>

export function lookupTranslation(
  bundle: Record<string, any> | null | undefined,
  key: string,
): string {
  if (!bundle || !key) return ''
  const keys = key.split('.')
  let value: unknown = bundle
  for (const k of keys) {
    if (value && typeof value === 'object' && k in (value as Record<string, unknown>)) {
      value = (value as Record<string, unknown>)[k]
    } else {
      return ''
    }
  }
  return typeof value === 'string' ? value : ''
}

function mergeLocaleWithEnglish(base: any, candidate: any): any {
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
    return base
  }
  const out: Record<string, any> = Array.isArray(base) ? [...base] : { ...base }
  for (const [key, value] of Object.entries(candidate)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = mergeLocaleWithEnglish(base?.[key] ?? {}, value)
    } else {
      out[key] = value
    }
  }
  return out
}

/**
 * Lazily load translations for a single language and merge them with the English base.
 * This avoids bundling all 44 language JSONs into the initial JavaScript chunk.
 */
export async function loadTranslations(lang: Language): Promise<Record<string, any>> {
  if (!LANGUAGE_CODES.includes(lang)) {
    throw new Error(`Unsupported language: ${lang}`)
  }

  if (lang === 'en') {
    return ENGLISH_TRANSLATIONS
  }

  try {
    const mod = await import(`./translations/${lang}.json`)
    const locale = mod.default || mod
    return mergeLocaleWithEnglish(enBase, locale)
  } catch (error) {
    console.warn(`[translations] Failed to load ${lang}, falling back to English`, error)
    return ENGLISH_TRANSLATIONS
  }
}

// Re-export types for convenience
export { LANGUAGE_CODES, languages, type Language, type LanguageInfo } from './locale-registry'
