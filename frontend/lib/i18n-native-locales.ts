/**
 * Locales with hand-maintained JSON in `translations.ts` (not English-copy aliases).
 * All other selector codes use AI + cache on top of the English source strings.
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
  return language !== "en" && !LOCALES_WITH_NATIVE_BUNDLE.includes(language as NativeBundleLocale)
}
