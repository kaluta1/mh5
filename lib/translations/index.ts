import en from './en.json'
import fr from './fr.json'
import es from './es.json'
import de from './de.json'

export type Language = 'en' | 'fr' | 'es' | 'de'

export const languages = {
  en: { name: 'English', flag: '🇺🇸' },
  fr: { name: 'Français', flag: '🇫🇷' },
  es: { name: 'Español', flag: '🇪🇸' },
  de: { name: 'Deutsch', flag: '🇩🇪' }
} as const

export const translations = {
  en,
  fr,
  es,
  de
} as const

export type TranslationKeys = typeof en
