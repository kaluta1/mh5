import en from './en.json'
import fr from './fr.json'
import es from './es.json'
import de from './de.json'
import pt from './pt.json'
import sw from './sw.json'
import ar from './ar.json'
import zh from './zh.json'
import hi from './hi.json'
import ru from './ru.json'
import it from './it.json'
import nl from './nl.json'
import tr from './tr.json'
import ja from './ja.json'
import ko from './ko.json'

export type Language =
  | 'en'
  | 'fr'
  | 'es'
  | 'de'
  | 'pt'
  | 'sw'
  | 'ar'
  | 'zh'
  | 'hi'
  | 'ru'
  | 'it'
  | 'nl'
  | 'tr'
  | 'ja'
  | 'ko'

export const languages = {
  en: { name: 'English', flag: '🇬🇧' },
  ar: { name: 'العربية', flag: '🇸🇦', rtl: true },
  zh: { name: '中文', flag: '🇨🇳' },
  nl: { name: 'Nederlands', flag: '🇳🇱' },
  fr: { name: 'Français', flag: '🇫🇷' },
  de: { name: 'Deutsch', flag: '🇩🇪' },
  hi: { name: 'हिन्दी', flag: '🇮🇳' },
  it: { name: 'Italiano', flag: '🇮🇹' },
  ja: { name: '日本語', flag: '🇯🇵' },
  ko: { name: '한국어', flag: '🇰🇷' },
  pt: { name: 'Português', flag: '🇵🇹' },
  ru: { name: 'Русский', flag: '🇷🇺' },
  es: { name: 'Español', flag: '🇪🇸' },
  sw: { name: 'Kiswahili', flag: '🇹🇿' },
  tr: { name: 'Türkçe', flag: '🇹🇷' },
} as const

export const translations = {
  en,
  fr,
  es,
  de,
  pt,
  sw,
  ar,
  zh,
  hi,
  ru,
  it,
  nl,
  tr,
  ja,
  ko,
} as const

export type TranslationKeys = typeof en
