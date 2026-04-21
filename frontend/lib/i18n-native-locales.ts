/**
 * All supported locales are native JSON bundles now.
 * AI runtime translation has been removed.
 */
export const LOCALES_WITH_NATIVE_BUNDLE = [
  "fr",
  "es",
  "de",
  "pt",
  "sw",
  "ar",
  "zh",
  "hi",
  "ru",
  "it",
  "nl",
  "tr",
  "ja",
  "ko",
] as const

export type NativeBundleLocale = (typeof LOCALES_WITH_NATIVE_BUNDLE)[number]

export function localeUsesAiTranslation(language: string): boolean {
  return false
}
