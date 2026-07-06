/**
 * SEO metadata translations.
 * Uses a small, dedicated catalog so server-side metadata generation does not
 * pull the full locale bundles into the chunk graph.
 */
import type { Language } from './locale-registry'
import { getSeoString } from './seo-translations'

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

export function getMetadataTranslations(lang: Language = 'en'): MetadataTranslations {
  const siteName = 'MyHigh5'

  const contestsNav = getSeoString(lang, ['navigation', 'contests'])
  const aboutNav = getSeoString(lang, ['navigation', 'about'])
  const contactNav = getSeoString(lang, ['navigation', 'contact'])
  const loginNav = getSeoString(lang, ['navigation', 'login'])
  const registerNav = getSeoString(lang, ['navigation', 'register'])

  const heroDescription = 'Join contests, build your network, and earn through our 10-level affiliate program. Every vote, every referral generates income.'

  return {
    siteName,
    defaultTitle: 'MyHigh5 - Global Contest Platform',
    defaultDescription: heroDescription,
    pages: {
      home: {
        title: 'MyHigh5 | Global Contest Platform',
        description: heroDescription,
      },
      contests: {
        title: `${contestsNav || 'Contests'} - ${siteName}`,
        description: getSeoString(lang, ['pages', 'contests', 'subtitle']),
      },
      about: {
        title: `${aboutNav || 'About'} - ${siteName}`,
        description: getSeoString(lang, ['pages', 'about', 'subtitle']),
      },
      contact: {
        title: `${contactNav || 'Contact'} - ${siteName}`,
        description: getSeoString(lang, ['pages', 'contact', 'subtitle']),
      },
      login: {
        title: `${loginNav || 'Login'} - ${siteName}`,
        description: getSeoString(lang, ['auth', 'login', 'subtitle']),
      },
      register: {
        title: `${registerNav || 'Register'} - ${siteName}`,
        description: getSeoString(lang, ['auth', 'register', 'subtitle']),
      },
    },
  }
}

/**
 * Détecte la langue depuis les headers de la requête
 */
export function detectLanguageFromHeaders(_headers: Headers): Language {
  // English-only site — ignore saved locale cookies.
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
