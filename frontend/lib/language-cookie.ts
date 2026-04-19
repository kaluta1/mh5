import { LANGUAGE_CODES, type Language } from '@/lib/translations'

/** Same name as localStorage key — server reads this in `detectLanguageFromHeaders`. */
export const LANGUAGE_PREFERENCE_KEY = 'myhigh5-language'

/** Keep in sync with `LANGUAGE_CODES` / `Language` in `lib/translations.ts` (for inline scripts). */
export const SUPPORTED_LANGUAGE_CODES: Language[] = [...LANGUAGE_CODES]

const MAX_AGE_SECONDS = 60 * 60 * 24 * 365

/**
 * Persists language for the browser and for the next full page request (SSR reads Cookie).
 */
export function setLanguagePreferenceClient(language: Language): void {
  if (typeof document === 'undefined') return
  const value = encodeURIComponent(language)
  document.cookie = `${LANGUAGE_PREFERENCE_KEY}=${value}; path=/; max-age=${MAX_AGE_SECONDS}; SameSite=Lax`
}
