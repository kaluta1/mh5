import type { Language } from './locale-registry'

type MaintenanceMessages = {
  maintenance: {
    title: string
    message: string
    backSoon: string
  }
}

const catalog: Partial<Record<Language, MaintenanceMessages>> = {
  en: {
    maintenance: {
      title: "We'll be back soon",
      message: "We are refining our contest migration functionality and adding more features to enhance user experience. We will be back soon.",
      backSoon: "Back soon"
    }
  },
  fr: {
    maintenance: {
      title: "Nous revenons bientôt",
      message: "Nous peaufinons notre fonctionnalité de migration de concours et ajoutons plus de fonctionnalités pour améliorer l'expérience utilisateur. Nous serons de retour bientôt.",
      backSoon: "De retour bientôt"
    }
  },
  es: {
    maintenance: {
      title: "Volveremos pronto",
      message: "Estamos perfeccionando nuestra funcionalidad de migración de concursos y agregando más características para mejorar la experiencia del usuario. Volveremos pronto.",
      backSoon: "Volveremos pronto"
    }
  },
  de: {
    maintenance: {
      title: "Wir sind bald zurück",
      message: "Wir verfeinern unsere Wettbewerbsmigrationsfunktion und fügen weitere Funktionen hinzu, um die Benutzererfahrung zu verbessern. Wir sind bald wieder zurück.",
      backSoon: "Bald zurück"
    }
  }
}

export function getMaintenanceTranslations(lang: Language): MaintenanceMessages {
  return catalog[lang] ?? catalog.en!
}

export { catalog as maintenanceTranslations }
