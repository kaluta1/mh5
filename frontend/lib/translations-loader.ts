import { Language, LANGUAGE_CODES } from './locale-registry'
import enBase from './translations/en.json'

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
    return enBase as Record<string, any>
  }

  try {
    const mod = await import(`./translations/${lang}.json`)
    const locale = mod.default || mod
    return mergeLocaleWithEnglish(enBase, locale)
  } catch (error) {
    console.warn(`[translations] Failed to load ${lang}, falling back to English`, error)
    return enBase as Record<string, any>
  }
}

// Re-export types for convenience
export { LANGUAGE_CODES, languages, type Language, type LanguageInfo } from './locale-registry'
