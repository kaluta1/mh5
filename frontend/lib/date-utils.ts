/**
 * Utilitaires pour formater les dates selon la langue
 */

import { Language } from './translations'

/**
 * Mappe les noms de jours (toutes langues) vers les traductions
 */
const dayMap: Record<string, Partial<Record<Language, string>>> = {
  // Anglais
  'Monday': { fr: 'Lundi', en: 'Monday', es: 'Lunes', de: 'Montag' },
  'Tuesday': { fr: 'Mardi', en: 'Tuesday', es: 'Martes', de: 'Dienstag' },
  'Wednesday': { fr: 'Mercredi', en: 'Wednesday', es: 'Miércoles', de: 'Mittwoch' },
  'Thursday': { fr: 'Jeudi', en: 'Thursday', es: 'Jueves', de: 'Donnerstag' },
  'Friday': { fr: 'Vendredi', en: 'Friday', es: 'Viernes', de: 'Freitag' },
  'Saturday': { fr: 'Samedi', en: 'Saturday', es: 'Sábado', de: 'Samstag' },
  'Sunday': { fr: 'Dimanche', en: 'Sunday', es: 'Domingo', de: 'Sonntag' },
  'Mon': { fr: 'Lun', en: 'Mon', es: 'Lun', de: 'Mo' },
  'Tue': { fr: 'Mar', en: 'Tue', es: 'Mar', de: 'Di' },
  'Wed': { fr: 'Mer', en: 'Wed', es: 'Mié', de: 'Mi' },
  'Thu': { fr: 'Jeu', en: 'Thu', es: 'Jue', de: 'Do' },
  'Fri': { fr: 'Ven', en: 'Fri', es: 'Vie', de: 'Fr' },
  'Sat': { fr: 'Sam', en: 'Sat', es: 'Sáb', de: 'Sa' },
  'Sun': { fr: 'Dim', en: 'Sun', es: 'Dom', de: 'So' },
  // Français (pour traduire depuis le français)
  'Lundi': { fr: 'Lundi', en: 'Monday', es: 'Lunes', de: 'Montag' },
  'Mardi': { fr: 'Mardi', en: 'Tuesday', es: 'Martes', de: 'Dienstag' },
  'Mercredi': { fr: 'Mercredi', en: 'Wednesday', es: 'Miércoles', de: 'Mittwoch' },
  'Jeudi': { fr: 'Jeudi', en: 'Thursday', es: 'Jueves', de: 'Donnerstag' },
  'Vendredi': { fr: 'Vendredi', en: 'Friday', es: 'Viernes', de: 'Freitag' },
  'Samedi': { fr: 'Samedi', en: 'Saturday', es: 'Sábado', de: 'Samstag' },
  'Dimanche': { fr: 'Dimanche', en: 'Sunday', es: 'Domingo', de: 'Sonntag' },
  'Lun': { fr: 'Lun', en: 'Mon', es: 'Lun', de: 'Mo' },
  'Mar': { fr: 'Mar', en: 'Tue', es: 'Mar', de: 'Di' },
  'Mer': { fr: 'Mer', en: 'Wed', es: 'Mié', de: 'Mi' },
  'Jeu': { fr: 'Jeu', en: 'Thu', es: 'Jue', de: 'Do' },
  'Ven': { fr: 'Ven', en: 'Fri', es: 'Vie', de: 'Fr' },
  'Sam': { fr: 'Sam', en: 'Sat', es: 'Sáb', de: 'Sa' },
  'Dim': { fr: 'Dim', en: 'Sun', es: 'Dom', de: 'So' },
  // Espagnol
  'Lunes': { fr: 'Lundi', en: 'Monday', es: 'Lunes', de: 'Montag' },
  'Martes': { fr: 'Mardi', en: 'Tuesday', es: 'Martes', de: 'Dienstag' },
  'Miércoles': { fr: 'Mercredi', en: 'Wednesday', es: 'Miércoles', de: 'Mittwoch' },
  'Jueves': { fr: 'Jeudi', en: 'Thursday', es: 'Jueves', de: 'Donnerstag' },
  'Viernes': { fr: 'Vendredi', en: 'Friday', es: 'Viernes', de: 'Freitag' },
  'Sábado': { fr: 'Samedi', en: 'Saturday', es: 'Sábado', de: 'Samstag' },
  'Domingo': { fr: 'Dimanche', en: 'Sunday', es: 'Domingo', de: 'Sonntag' },
  'Mié': { fr: 'Mer', en: 'Wed', es: 'Mié', de: 'Mi' },
  'Sáb': { fr: 'Sam', en: 'Sat', es: 'Sáb', de: 'Sa' },
  'Dom': { fr: 'Dim', en: 'Sun', es: 'Dom', de: 'So' },
  // Allemand
  'Montag': { fr: 'Lundi', en: 'Monday', es: 'Lunes', de: 'Montag' },
  'Dienstag': { fr: 'Mardi', en: 'Tuesday', es: 'Martes', de: 'Dienstag' },
  'Mittwoch': { fr: 'Mercredi', en: 'Wednesday', es: 'Miércoles', de: 'Mittwoch' },
  'Donnerstag': { fr: 'Jeudi', en: 'Thursday', es: 'Jueves', de: 'Donnerstag' },
  'Freitag': { fr: 'Vendredi', en: 'Friday', es: 'Viernes', de: 'Freitag' },
  'Samstag': { fr: 'Samedi', en: 'Saturday', es: 'Sábado', de: 'Samstag' },
  'Sonntag': { fr: 'Dimanche', en: 'Sunday', es: 'Domingo', de: 'Sonntag' },
  'Mo': { fr: 'Lun', en: 'Mon', es: 'Lun', de: 'Mo' },
  'Di': { fr: 'Mar', en: 'Tue', es: 'Mar', de: 'Di' },
  'Mi': { fr: 'Mer', en: 'Wed', es: 'Mié', de: 'Mi' },
  'Do': { fr: 'Jeu', en: 'Thu', es: 'Jue', de: 'Do' },
  'Fr': { fr: 'Ven', en: 'Fri', es: 'Vie', de: 'Fr' },
  'Sa': { fr: 'Sam', en: 'Sat', es: 'Sáb', de: 'Sa' },
  'So': { fr: 'Dim', en: 'Sun', es: 'Dom', de: 'So' },
}

/**
 * Mappe les noms de mois (toutes langues) vers les traductions
 */
const monthMap: Record<string, Partial<Record<Language, string>>> = {
  // Anglais
  'January': { fr: 'Janvier', en: 'January', es: 'Enero', de: 'Januar' },
  'February': { fr: 'Février', en: 'February', es: 'Febrero', de: 'Februar' },
  'March': { fr: 'Mars', en: 'March', es: 'Marzo', de: 'März' },
  'April': { fr: 'Avril', en: 'April', es: 'Abril', de: 'April' },
  'May': { fr: 'Mai', en: 'May', es: 'Mayo', de: 'Mai' },
  'June': { fr: 'Juin', en: 'June', es: 'Junio', de: 'Juni' },
  'July': { fr: 'Juillet', en: 'July', es: 'Julio', de: 'Juli' },
  'August': { fr: 'Août', en: 'August', es: 'Agosto', de: 'August' },
  'September': { fr: 'Septembre', en: 'September', es: 'Septiembre', de: 'September' },
  'October': { fr: 'Octobre', en: 'October', es: 'Octubre', de: 'Oktober' },
  'November': { fr: 'Novembre', en: 'November', es: 'Noviembre', de: 'November' },
  'December': { fr: 'Décembre', en: 'December', es: 'Diciembre', de: 'Dezember' },
  'Jan': { fr: 'Jan', en: 'Jan', es: 'Ene', de: 'Jan' },
  'Feb': { fr: 'Fév', en: 'Feb', es: 'Feb', de: 'Feb' },
  'Mar': { fr: 'Mar', en: 'Mar', es: 'Mar', de: 'Mär' },
  'Apr': { fr: 'Avr', en: 'Apr', es: 'Abr', de: 'Apr' },
  'Jun': { fr: 'Juin', en: 'Jun', es: 'Jun', de: 'Jun' },
  'Jul': { fr: 'Juil', en: 'Jul', es: 'Jul', de: 'Jul' },
  'Aug': { fr: 'Août', en: 'Aug', es: 'Ago', de: 'Aug' },
  'Sep': { fr: 'Sep', en: 'Sep', es: 'Sep', de: 'Sep' },
  'Oct': { fr: 'Oct', en: 'Oct', es: 'Oct', de: 'Okt' },
  'Nov': { fr: 'Nov', en: 'Nov', es: 'Nov', de: 'Nov' },
  'Dec': { fr: 'Déc', en: 'Dec', es: 'Dic', de: 'Dez' },
  // Français (pour traduire depuis le français)
  'Janvier': { fr: 'Janvier', en: 'January', es: 'Enero', de: 'Januar' },
  'Février': { fr: 'Février', en: 'February', es: 'Febrero', de: 'Februar' },
  'Mars': { fr: 'Mars', en: 'March', es: 'Marzo', de: 'März' },
  'Avril': { fr: 'Avril', en: 'April', es: 'Abril', de: 'April' },
  'Mai': { fr: 'Mai', en: 'May', es: 'Mayo', de: 'Mai' },
  'Juin': { fr: 'Juin', en: 'June', es: 'Junio', de: 'Juni' },
  'Juillet': { fr: 'Juillet', en: 'July', es: 'Julio', de: 'Juli' },
  'Août': { fr: 'Août', en: 'August', es: 'Agosto', de: 'August' },
  'Septembre': { fr: 'Septembre', en: 'September', es: 'Septiembre', de: 'September' },
  'Octobre': { fr: 'Octobre', en: 'October', es: 'Octubre', de: 'Oktober' },
  'Novembre': { fr: 'Novembre', en: 'November', es: 'Noviembre', de: 'November' },
  'Décembre': { fr: 'Décembre', en: 'December', es: 'Diciembre', de: 'Dezember' },
  'Fév': { fr: 'Fév', en: 'Feb', es: 'Feb', de: 'Feb' },
  'Avr': { fr: 'Avr', en: 'Apr', es: 'Abr', de: 'Apr' },
  'Juil': { fr: 'Juil', en: 'Jul', es: 'Jul', de: 'Jul' },
  'Déc': { fr: 'Déc', en: 'Dec', es: 'Dic', de: 'Dez' },
  // Espagnol
  'Enero': { fr: 'Janvier', en: 'January', es: 'Enero', de: 'Januar' },
  'Febrero': { fr: 'Février', en: 'February', es: 'Febrero', de: 'Februar' },
  'Marzo': { fr: 'Mars', en: 'March', es: 'Marzo', de: 'März' },
  'Abril': { fr: 'Avril', en: 'April', es: 'Abril', de: 'April' },
  'Mayo': { fr: 'Mai', en: 'May', es: 'Mayo', de: 'Mai' },
  'Junio': { fr: 'Juin', en: 'June', es: 'Junio', de: 'Juni' },
  'Julio': { fr: 'Juillet', en: 'July', es: 'Julio', de: 'Juli' },
  'Agosto': { fr: 'Août', en: 'August', es: 'Agosto', de: 'August' },
  'Septiembre': { fr: 'Septembre', en: 'September', es: 'Septiembre', de: 'September' },
  'Octubre': { fr: 'Octobre', en: 'October', es: 'Octubre', de: 'Oktober' },
  'Noviembre': { fr: 'Novembre', en: 'November', es: 'Noviembre', de: 'November' },
  'Diciembre': { fr: 'Décembre', en: 'December', es: 'Diciembre', de: 'Dezember' },
  'Ene': { fr: 'Jan', en: 'Jan', es: 'Ene', de: 'Jan' },
  'Abr': { fr: 'Avr', en: 'Apr', es: 'Abr', de: 'Apr' },
  'Ago': { fr: 'Août', en: 'Aug', es: 'Ago', de: 'Aug' },
  'Dic': { fr: 'Déc', en: 'Dec', es: 'Dic', de: 'Dez' },
  // Allemand
  'Januar': { fr: 'Janvier', en: 'January', es: 'Enero', de: 'Januar' },
  'Februar': { fr: 'Février', en: 'February', es: 'Febrero', de: 'Februar' },
  'März': { fr: 'Mars', en: 'March', es: 'Marzo', de: 'März' },
  'Mär': { fr: 'Mar', en: 'Mar', es: 'Mar', de: 'Mär' },
  'Okt': { fr: 'Oct', en: 'Oct', es: 'Oct', de: 'Okt' },
  'Dezember': { fr: 'Décembre', en: 'December', es: 'Diciembre', de: 'Dezember' },
  'Dez': { fr: 'Déc', en: 'Dec', es: 'Dic', de: 'Dez' },
}

/**
 * Traduit un nom de jour selon la langue
 */
export function translateDay(day: string, language: Language = 'fr'): string {
  return dayMap[day]?.[language] || day
}

/**
 * Traduit un nom de mois selon la langue
 */
export function translateMonth(month: string, language: Language = 'fr'): string {
  return monthMap[month]?.[language] || month
}

/**
 * Formate une date selon la langue
 */
// Map app language code -> BCP 47 locale tag for `toLocaleDateString`.
// Browsers fall back gracefully on unsupported locales.
const LOCALE_BY_LANG: Partial<Record<Language, string>> = {
  fr: 'fr-FR',
  en: 'en-US',
  es: 'es-ES',
  de: 'de-DE',
  pt: 'pt-PT',
  sw: 'sw-TZ',
  ar: 'ar-SA',
  zh: 'zh-CN',
  hi: 'hi-IN',
  ru: 'ru-RU',
  it: 'it-IT',
  nl: 'nl-NL',
  tr: 'tr-TR',
  ja: 'ja-JP',
  ko: 'ko-KR',
}

export function formatDate(date: Date | string, language: Language = 'fr', options?: Intl.DateTimeFormatOptions): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date
  const defaultOptions: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }
  return dateObj.toLocaleDateString(LOCALE_BY_LANG[language] || 'en-US', options || defaultOptions)
}

/**
 * Formate une date courte (jour/mois) selon la langue
 */
export function formatShortDate(date: Date | string, language: Language = 'fr'): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date
  return dateObj.toLocaleDateString(LOCALE_BY_LANG[language] || 'en-US', {
    day: 'numeric',
    month: 'short',
  })
}

