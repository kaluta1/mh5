import type { Language } from './locale-registry'

/**
 * Lightweight SEO metadata catalog. Only covers the handful of strings needed
 * for OpenGraph / page metadata. Keeping this separate from the main
 * translation bundles avoids pulling all 44 locale JSONs into server chunks.
 */

const seoCatalog: Partial<Record<Language, { navigation: Record<string, string>; pages: Record<string, { subtitle: string }>; auth: { login: { subtitle: string }; register: { subtitle: string } } }>> = {
  en: {
    navigation: {
      contests: 'Contests',
      about: 'About',
      contact: 'Contact',
      login: 'Login',
      register: 'Register'
    },
    pages: {
      contests: { subtitle: 'Join exciting competitions from local to global level. Participate, nominate, or vote in exciting competitions that progress from the local level to the global level.' },
      about: { subtitle: 'The first global contest platform connecting talents worldwide, from local to global level.' },
      contact: { subtitle: 'Our team is here to help. We usually respond within 24 hours.' },
      login: { subtitle: 'Sign in to your High5 account to participate in contests, vote and win prizes!' },
      register: { subtitle: 'Create your High5 account and join the world\'s largest contest community. Start participating, voting and winning today!' }
    },
    auth: {
      login: { subtitle: 'Sign in to your High5 account to participate in contests, vote and win prizes!' },
      register: { subtitle: 'Create your High5 account and join the world\'s largest contest community. Start participating, voting and winning today!' }
    }
  },
  fr: {
    navigation: {
      contests: 'Concours',
      about: 'À propos',
      contact: 'Contact',
      login: 'Connexion',
      register: 'Inscription'
    },
    pages: {
      contests: { subtitle: 'Rejoignez des compétitions passionnantes du niveau local au niveau mondial. Participez, nominez ou votez dans des concours passionnants qui progressent du niveau local au niveau mondial.' },
      about: { subtitle: 'La première plateforme de concours mondiale connectant les talents du monde entier, du niveau local au niveau mondial.' },
      contact: { subtitle: 'Notre équipe est là pour vous aider. Nous répondons généralement sous 24 heures.' },
      login: { subtitle: 'Connectez-vous à votre compte High5 pour participer à des concours, voter et gagner des prix !' },
      register: { subtitle: 'Créez votre compte High5 et rejoignez la plus grande communauté de concours au monde. Commencez à participer, voter et gagner dès aujourd\'hui !' }
    },
    auth: {
      login: { subtitle: 'Connectez-vous à votre compte High5 pour participer à des concours, voter et gagner des prix !' },
      register: { subtitle: 'Créez votre compte High5 et rejoignez la plus grande communauté de concours au monde. Commencez à participer, voter et gagner dès aujourd\'hui !' }
    }
  },
  es: {
    navigation: {
      contests: 'Concursos',
      about: 'Acerca de',
      contact: 'Contacto',
      login: 'Iniciar sesión',
      register: 'Registrarse'
    },
    pages: {
      contests: { subtitle: 'Únete a emocionantes competiciones desde el nivel local hasta el global. Participa, nombra o vota en concursos emocionantes que progresan desde el nivel local hasta el global.' },
      about: { subtitle: 'La primera plataforma de concursos global que conecta talentos de todo el mundo, desde el nivel local hasta el global.' },
      contact: { subtitle: 'Nuestro equipo está aquí para ayudarte. Normalmente respondemos en 24 horas.' },
      login: { subtitle: 'Inicia sesión en tu cuenta High5 para participar en concursos, votar y ganar premios.' },
      register: { subtitle: 'Crea tu cuenta High5 y únete a la comunidad de concursos más grande del mundo. ¡Empieza a participar, votar y ganar hoy!' }
    },
    auth: {
      login: { subtitle: 'Inicia sesión en tu cuenta High5 para participar en concursos, votar y ganar premios.' },
      register: { subtitle: 'Crea tu cuenta High5 y únete a la comunidad de concursos más grande del mundo. ¡Empieza a participar, votar y ganar hoy!' }
    }
  },
  de: {
    navigation: {
      contests: 'Wettbewerbe',
      about: 'Über uns',
      contact: 'Kontakt',
      login: 'Anmelden',
      register: 'Registrieren'
    },
    pages: {
      contests: { subtitle: 'Nehmen Sie an spannenden Wettbewerben vom lokalen bis zum globalen Niveau teil. Nehmen Sie teil, nominieren oder stimmen Sie in aufregenden Wettbewerben ab, die vom lokalen zum globalen Niveau führen.' },
      about: { subtitle: 'Die erste globale Wettbewerbsplattform, die Talente weltweit verbindet, vom lokalen bis zum globalen Niveau.' },
      contact: { subtitle: 'Unser Team ist hier, um zu helfen. Wir antworten normalerweise innerhalb von 24 Stunden.' },
      login: { subtitle: 'Melden Sie sich in Ihrem High5-Konto an, um an Wettbewerben teilzunehmen, abzustimmen und Preise zu gewinnen!' },
      register: { subtitle: 'Erstellen Sie Ihr High5-Konto und treten Sie der weltweit größten Wettbewerbs-Community bei. Beginnen Sie noch heute mitmachen, abstimmen und gewinnen!' }
    },
    auth: {
      login: { subtitle: 'Melden Sie sich in Ihrem High5-Konto an, um an Wettbewerben teilzunehmen, abzustimmen und Preise zu gewinnen!' },
      register: { subtitle: 'Erstellen Sie Ihr High5-Konto und treten Sie der weltweit größten Wettbewerbs-Community bei. Beginnen Sie noch heute mitmachen, abstimmen und gewinnen!' }
    }
  }
}

function getBundle(lang: Language) {
  return seoCatalog[lang] ?? seoCatalog.en!
}

export function getSeoString(lang: Language, path: string[]): string {
  const bundle = getBundle(lang)
  let value: any = bundle
  for (const key of path) {
    if (value && typeof value === 'object' && key in value) {
      value = value[key]
    } else {
      // Fallback to English
      let enValue: any = seoCatalog.en
      for (const k of path) {
        if (enValue && typeof enValue === 'object' && k in enValue) {
          enValue = enValue[k]
        } else {
          return path.join('.')
        }
      }
      return typeof enValue === 'string' ? enValue : path.join('.')
    }
  }
  return typeof value === 'string' ? value : path.join('.')
}
