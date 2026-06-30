import type { Language } from './locale-registry'
import { LOCALE_BY_LANG } from './date-utils'

/** BCP 47 locale for `Intl` / `toLocaleDateString` — defaults to English. */
export function intlLocaleFor(language?: string | null): string {
  if (!language) return 'en-US'
  return LOCALE_BY_LANG[language as Language] ?? 'en-US'
}
