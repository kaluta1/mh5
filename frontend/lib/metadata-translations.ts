/**
 * Traductions pour les métadonnées SEO
 * Utilisé côté serveur pour générer les métadonnées selon la langue
 */
import { Language, translations } from './translations'
import { LANGUAGE_PREFERENCE_KEY, SUPPORTED_LANGUAGE_CODES } from './language-cookie'

export interface MetadataTranslations {
  siteName: string
  defaultTitle: string
  defaultDescription: string
  pages: {
    home: {
      title: string
      description: string
    }
    contests: {
      title: string
      description: string
    }
    about: {
      title: string
      description: string
    }
    contact: {
      title: string
      description: string
    }
    login: {
      title: string
      description: string
    }
    register: {
      title: string
      description: string
    }
  }
}

function getNestedTranslation(lang: Language, keys: string[]): string {
  let value: any = translations[lang]
  for (const key of keys) {
    if (value && typeof value === 'object' && key in value) {
      value = value[key]
    } else {
      // Fallback to English
      value = translations.en
      for (const k of keys) {
        if (value && typeof value === 'object' && k in value) {
          value = value[k]
        } else {
          return keys.join('.')
        }
      }
      break
    }
  }
  return typeof value === 'string' ? value : keys.join('.')
}

export function getMetadataTranslations(lang: Language = 'en'): MetadataTranslations {
  const siteName = 'MyHigh5'
  
  // Récupérer les traductions
  // Certaines langues ont hero.title directement, d'autres ont title_line1, title_line2, title_line3
  let heroTitle = getNestedTranslation(lang, ['hero', 'title'])
  if (!heroTitle || heroTitle === 'hero.title') {
    // Essayer avec title_line2 (le plus important) ou title_line1
    const heroTitleLine2 = getNestedTranslation(lang, ['hero', 'title_line2'])
    const heroTitleLine1 = getNestedTranslation(lang, ['hero', 'title_line1'])
    heroTitle = heroTitleLine2 || heroTitleLine1 || 'Compete & Earn'
  }
  const heroSubtitle = getNestedTranslation(lang, ['hero', 'subtitle'])
  let heroDescription = getNestedTranslation(lang, ['hero', 'description'])
  // Si la description est une clé de traduction (commence par "hero."), utiliser une valeur par défaut
  if (!heroDescription || heroDescription === 'hero.description' || heroDescription.startsWith('hero.')) {
    heroDescription = 'Join contests, build your network, and earn through our 10-level affiliate program. Every vote, every referral generates income.'
  }
  
  const contestsNav = getNestedTranslation(lang, ['navigation', 'contests'])
  let contestsSubtitle = getNestedTranslation(lang, ['pages', 'contests', 'subtitle'])
  // Si le subtitle est une clé de traduction, utiliser une valeur par défaut en anglais
  if (!contestsSubtitle || contestsSubtitle === 'pages.contests.subtitle' || contestsSubtitle.startsWith('pages.')) {
    contestsSubtitle = 'Join exciting competitions from local to global level. Participate, nominate, or vote in exciting competitions that progress from the local level to the global level.'
  }
  
  const aboutNav = getNestedTranslation(lang, ['navigation', 'about'])
  let aboutSubtitle = getNestedTranslation(lang, ['pages', 'about', 'subtitle'])
  // Si le subtitle est une clé de traduction, utiliser une valeur par défaut en anglais
  if (!aboutSubtitle || aboutSubtitle === 'pages.about.subtitle' || aboutSubtitle.startsWith('pages.')) {
    aboutSubtitle = 'The first global contest platform connecting talents worldwide, from local to global level.'
  }
  
  const contactNav = getNestedTranslation(lang, ['navigation', 'contact'])
  let contactSubtitle = getNestedTranslation(lang, ['pages', 'contact', 'subtitle'])
  // Si le subtitle est une clé de traduction, utiliser une valeur par défaut en anglais
  if (!contactSubtitle || contactSubtitle === 'pages.contact.subtitle' || contactSubtitle.startsWith('pages.')) {
    contactSubtitle = 'Our team is here to help. We usually respond within 24 hours.'
  }
  
  const loginNav = getNestedTranslation(lang, ['navigation', 'login'])
  let loginSubtitle = getNestedTranslation(lang, ['auth', 'login', 'subtitle'])
  // Si le subtitle est une clé de traduction, utiliser une valeur par défaut en anglais
  if (!loginSubtitle || loginSubtitle === 'auth.login.subtitle' || loginSubtitle.startsWith('auth.')) {
    loginSubtitle = 'Sign in to your High5 account to participate in contests, vote and win prizes!'
  }
  
  const registerNav = getNestedTranslation(lang, ['navigation', 'register'])
  let registerSubtitle = getNestedTranslation(lang, ['auth', 'register', 'subtitle'])
  // Si le subtitle est une clé de traduction, utiliser une valeur par défaut en anglais
  if (!registerSubtitle || registerSubtitle === 'auth.register.subtitle' || registerSubtitle.startsWith('auth.')) {
    registerSubtitle = 'Create your High5 account and join the world\'s largest contest community. Start participating, voting and winning today!'
  }

  return {
    siteName,
    defaultTitle: 'MyHigh5 - Global Contest Platform',
    defaultDescription: heroDescription || 'Join contests, build your network, and earn through our 10-level affiliate program.',
    pages: {
      home: {
        title: 'MyHigh5 | Global Contest Platform',
        description: heroDescription || 'Join contests, build your network, and earn through our 10-level affiliate program. Every vote, every referral generates income.',
      },
      contests: {
        title: `${contestsNav || 'Concours'} - ${siteName}`,
        description: contestsSubtitle,
      },
      about: {
        title: `${aboutNav || 'About'} - ${siteName}`,
        description: aboutSubtitle,
      },
      contact: {
        title: `${contactNav || 'Contact'} - ${siteName}`,
        description: contactSubtitle,
      },
      login: {
        title: `${loginNav || 'Login'} - ${siteName}`,
        description: loginSubtitle,
      },
      register: {
        title: `${registerNav || 'Register'} - ${siteName}`,
        description: registerSubtitle,
      },
    },
  }
}

/**
 * Détecte la langue depuis les headers de la requête
 */
export function detectLanguageFromHeaders(headers: Headers): Language {
  const acceptLanguage = headers.get('accept-language') || ''
  const rawCookie = headers.get('cookie')?.match(
    new RegExp(`${LANGUAGE_PREFERENCE_KEY}=([^;]+)`)
  )?.[1]
  let cookieLanguage: string | undefined
  if (rawCookie) {
    try {
      cookieLanguage = decodeURIComponent(rawCookie)
    } catch {
      cookieLanguage = rawCookie
    }
  }

  if (cookieLanguage && (SUPPORTED_LANGUAGE_CODES as string[]).includes(cookieLanguage)) {
    return cookieLanguage as Language
  }

  if (acceptLanguage) {
    const langs = acceptLanguage.split(',').map((l) => l.split(';')[0].trim().toLowerCase())
    for (const lang of langs) {
      const prefix = lang.split('-')[0]
      if ((SUPPORTED_LANGUAGE_CODES as string[]).includes(prefix)) {
        return prefix as Language
      }
    }
  }

  return 'en'
}

/**
 * Retourne les mots-clés SEO traduits selon la langue.
 * Only a few hand-curated lists exist; other languages fall back to English.
 */
export function getKeywords(lang: Language = 'en'): string[] {
  const keywordsMap: Partial<Record<Language, string[]>> = {
    fr: ["concours", "beauté", "talents", "communauté", "votes", "compétition", "affiliation", "gagner de l'argent", "high5", "myhigh5"],
    en: ["contests", "beauty", "talents", "community", "votes", "competition", "affiliation", "earn money", "high5", "myhigh5"],
    es: ["concursos", "belleza", "talentos", "comunidad", "votos", "competición", "afiliación", "ganar dinero", "high5", "myhigh5"],
    de: ["Wettbewerbe", "Schönheit", "Talente", "Gemeinschaft", "Stimmen", "Wettbewerb", "Affiliate", "Geld verdienen", "high5", "myhigh5"],
  }
  return keywordsMap[lang] || keywordsMap.en!
}

