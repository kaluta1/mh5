/**
 * Traductions pour les métadonnées SEO
 * Utilisé côté serveur pour générer les métadonnées selon la langue
 */
import { Language, translations } from './translations'

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

export function getMetadataTranslations(lang: Language = 'fr'): MetadataTranslations {
  const siteName = 'High5'
  
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
  const heroDescription = getNestedTranslation(lang, ['hero', 'description'])
  
  const contestsNav = getNestedTranslation(lang, ['navigation', 'contests'])
  const contestsSubtitle = getNestedTranslation(lang, ['pages', 'contests', 'subtitle'])
  
  const aboutNav = getNestedTranslation(lang, ['navigation', 'about'])
  const aboutSubtitle = getNestedTranslation(lang, ['pages', 'about', 'subtitle'])
  
  const contactNav = getNestedTranslation(lang, ['navigation', 'contact'])
  const contactSubtitle = getNestedTranslation(lang, ['pages', 'contact', 'subtitle'])
  
  const loginNav = getNestedTranslation(lang, ['navigation', 'login'])
  const loginSubtitle = getNestedTranslation(lang, ['auth', 'login', 'subtitle'])
  
  const registerNav = getNestedTranslation(lang, ['navigation', 'register'])
  const registerSubtitle = getNestedTranslation(lang, ['auth', 'register', 'subtitle'])

  return {
    siteName,
    defaultTitle: heroTitle || 'High5 - Compete & Earn',
    defaultDescription: heroDescription || 'Join contests, build your network, and earn through our 10-level affiliate program.',
    pages: {
      home: {
        title: `${heroTitle || 'Compete & Earn'} | ${heroSubtitle || 'Global Contest Platform'}`,
        description: heroDescription || 'Join contests, build your network, and earn through our 10-level affiliate program. Every vote, every referral generates income.',
      },
      contests: {
        title: `${contestsNav || 'Concours'} - ${siteName}`,
        description: contestsSubtitle || 'Explorez tous les concours disponibles sur High5. Participez à des concours de beauté, talents, photographie et bien plus encore.',
      },
      about: {
        title: `${aboutNav || 'À Propos'} - ${siteName}`,
        description: aboutSubtitle || 'Découvrez High5, la première plateforme mondiale de concours qui connecte les talents du monde entier.',
      },
      contact: {
        title: `${contactNav || 'Contact'} - ${siteName}`,
        description: contactSubtitle || 'Contactez l\'équipe High5. Nous sommes là pour vous aider avec vos questions sur la plateforme, les concours, les paiements et plus encore.',
      },
      login: {
        title: `${loginNav || 'Connexion'} - ${siteName}`,
        description: loginSubtitle || 'Connectez-vous à votre compte High5 pour participer aux concours, voter et gagner des prix !',
      },
      register: {
        title: `${registerNav || 'Inscription'} - ${siteName}`,
        description: registerSubtitle || 'Créez votre compte High5 et rejoignez la plus grande communauté de concours au monde. Commencez à participer, voter et gagner dès aujourd\'hui !',
      },
    },
  }
}

/**
 * Détecte la langue depuis les headers de la requête
 */
export function detectLanguageFromHeaders(headers: Headers): Language {
  const acceptLanguage = headers.get('accept-language') || ''
  const cookieLanguage = headers.get('cookie')?.match(/myhigh5-language=([^;]+)/)?.[1]
  
  // Priorité: cookie > accept-language > défaut (fr)
  if (cookieLanguage && ['en', 'fr', 'es', 'de'].includes(cookieLanguage)) {
    return cookieLanguage as Language
  }
  
  // Parser accept-language
  if (acceptLanguage) {
    const languages = acceptLanguage.split(',').map(lang => lang.split(';')[0].trim().toLowerCase())
    for (const lang of languages) {
      if (lang.startsWith('fr')) return 'fr'
      if (lang.startsWith('en')) return 'en'
      if (lang.startsWith('es')) return 'es'
      if (lang.startsWith('de')) return 'de'
    }
  }
  
  return 'fr' // Défaut
}

