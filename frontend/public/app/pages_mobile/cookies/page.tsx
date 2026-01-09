"use client"

import * as React from "react"
import { useLanguage } from "@/contexts/language-context"
import { 
  Cookie, 
  Settings, 
  BarChart, 
  Target,
  Shield,
  ToggleLeft,
  Mail
} from "lucide-react"

export default function CookiesMobilePage() {
  const { language } = useLanguage()

  const content: Record<string, {
    title: string
    lastUpdated: string
    intro: string
    sections: { title: string; icon: React.ElementType; content: string | string[] }[]
    contact: string
  }> = {
    en: {
      title: "Cookie Policy",
      lastUpdated: "Last Updated: December 2024",
      intro: "This Cookie Policy explains how MyHigh5.com uses cookies and similar technologies to recognize you when you visit our website.",
      sections: [
        {
          title: "What are cookies?",
          icon: Cookie,
          content: "Cookies are small data files that are placed on your computer or mobile device when you visit a website. They are widely used to make websites work more efficiently and provide information to website owners."
        },
        {
          title: "Essential Cookies",
          icon: Shield,
          content: [
            "These cookies are necessary for the website to function properly.",
            "They enable basic functions like page navigation and access to secure areas.",
            "The website cannot function properly without these cookies."
          ]
        },
        {
          title: "Analytics Cookies",
          icon: BarChart,
          content: [
            "These cookies help us understand how visitors interact with our website.",
            "They collect information about the number of visitors, bounce rate, traffic source, etc.",
            "This data helps us improve our website and user experience."
          ]
        },
        {
          title: "Advertising Cookies",
          icon: Target,
          content: [
            "These cookies are used to deliver relevant advertisements to you.",
            "They track your browsing habits to show you personalized ads.",
            "They may be set by our advertising partners."
          ]
        },
        {
          title: "Managing Cookies",
          icon: Settings,
          content: [
            "You can control and manage cookies through your browser settings.",
            "Most browsers allow you to refuse or accept cookies.",
            "Note that disabling certain cookies may affect website functionality."
          ]
        },
        {
          title: "Your Choices",
          icon: ToggleLeft,
          content: "You can choose to accept or decline cookies. Most web browsers automatically accept cookies, but you can usually modify your browser setting to decline cookies if you prefer."
        }
      ],
      contact: "For questions about our cookie policy, contact:"
    },
    fr: {
      title: "Politique des Cookies",
      lastUpdated: "Dernière mise à jour : Décembre 2024",
      intro: "Cette Politique des Cookies explique comment MyHigh5.com utilise les cookies et technologies similaires pour vous reconnaître lorsque vous visitez notre site web.",
      sections: [
        {
          title: "Que sont les cookies ?",
          icon: Cookie,
          content: "Les cookies sont de petits fichiers de données placés sur votre ordinateur ou appareil mobile lorsque vous visitez un site web. Ils sont largement utilisés pour faire fonctionner les sites web plus efficacement et fournir des informations aux propriétaires de sites."
        },
        {
          title: "Cookies essentiels",
          icon: Shield,
          content: [
            "Ces cookies sont nécessaires au bon fonctionnement du site web.",
            "Ils permettent des fonctions de base comme la navigation entre les pages et l'accès aux zones sécurisées.",
            "Le site web ne peut pas fonctionner correctement sans ces cookies."
          ]
        },
        {
          title: "Cookies analytiques",
          icon: BarChart,
          content: [
            "Ces cookies nous aident à comprendre comment les visiteurs interagissent avec notre site web.",
            "Ils collectent des informations sur le nombre de visiteurs, le taux de rebond, la source du trafic, etc.",
            "Ces données nous aident à améliorer notre site web et l'expérience utilisateur."
          ]
        },
        {
          title: "Cookies publicitaires",
          icon: Target,
          content: [
            "Ces cookies sont utilisés pour vous proposer des publicités pertinentes.",
            "Ils suivent vos habitudes de navigation pour vous montrer des annonces personnalisées.",
            "Ils peuvent être définis par nos partenaires publicitaires."
          ]
        },
        {
          title: "Gestion des cookies",
          icon: Settings,
          content: [
            "Vous pouvez contrôler et gérer les cookies via les paramètres de votre navigateur.",
            "La plupart des navigateurs vous permettent de refuser ou d'accepter les cookies.",
            "Notez que la désactivation de certains cookies peut affecter les fonctionnalités du site."
          ]
        },
        {
          title: "Vos choix",
          icon: ToggleLeft,
          content: "Vous pouvez choisir d'accepter ou de refuser les cookies. La plupart des navigateurs web acceptent automatiquement les cookies, mais vous pouvez généralement modifier les paramètres de votre navigateur pour refuser les cookies si vous préférez."
        }
      ],
      contact: "Pour toute question sur notre politique de cookies, contactez :"
    },
    es: {
      title: "Política de Cookies",
      lastUpdated: "Última actualización: Diciembre 2024",
      intro: "Esta Política de Cookies explica cómo MyHigh5.com utiliza cookies y tecnologías similares para reconocerte cuando visitas nuestro sitio web.",
      sections: [
        {
          title: "¿Qué son las cookies?",
          icon: Cookie,
          content: "Las cookies son pequeños archivos de datos que se colocan en tu computadora o dispositivo móvil cuando visitas un sitio web. Se utilizan ampliamente para hacer que los sitios web funcionen de manera más eficiente y proporcionar información a los propietarios del sitio."
        },
        {
          title: "Cookies esenciales",
          icon: Shield,
          content: [
            "Estas cookies son necesarias para que el sitio web funcione correctamente.",
            "Permiten funciones básicas como la navegación de páginas y el acceso a áreas seguras.",
            "El sitio web no puede funcionar correctamente sin estas cookies."
          ]
        },
        {
          title: "Cookies analíticas",
          icon: BarChart,
          content: [
            "Estas cookies nos ayudan a entender cómo interactúan los visitantes con nuestro sitio web.",
            "Recopilan información sobre el número de visitantes, tasa de rebote, fuente de tráfico, etc.",
            "Estos datos nos ayudan a mejorar nuestro sitio web y la experiencia del usuario."
          ]
        },
        {
          title: "Cookies publicitarias",
          icon: Target,
          content: [
            "Estas cookies se utilizan para mostrarte anuncios relevantes.",
            "Rastrean tus hábitos de navegación para mostrarte anuncios personalizados.",
            "Pueden ser establecidas por nuestros socios publicitarios."
          ]
        },
        {
          title: "Gestión de cookies",
          icon: Settings,
          content: [
            "Puedes controlar y gestionar las cookies a través de la configuración de tu navegador.",
            "La mayoría de los navegadores te permiten rechazar o aceptar cookies.",
            "Ten en cuenta que deshabilitar ciertas cookies puede afectar la funcionalidad del sitio."
          ]
        },
        {
          title: "Tus opciones",
          icon: ToggleLeft,
          content: "Puedes elegir aceptar o rechazar las cookies. La mayoría de los navegadores web aceptan cookies automáticamente, pero generalmente puedes modificar la configuración de tu navegador para rechazar cookies si lo prefieres."
        }
      ],
      contact: "Para preguntas sobre nuestra política de cookies, contacta:"
    },
    de: {
      title: "Cookie-Richtlinie",
      lastUpdated: "Zuletzt aktualisiert: Dezember 2024",
      intro: "Diese Cookie-Richtlinie erklärt, wie MyHigh5.com Cookies und ähnliche Technologien verwendet, um Sie zu erkennen, wenn Sie unsere Website besuchen.",
      sections: [
        {
          title: "Was sind Cookies?",
          icon: Cookie,
          content: "Cookies sind kleine Datendateien, die auf Ihrem Computer oder Mobilgerät gespeichert werden, wenn Sie eine Website besuchen. Sie werden häufig verwendet, um Websites effizienter zu machen und Informationen an Website-Besitzer zu liefern."
        },
        {
          title: "Essentielle Cookies",
          icon: Shield,
          content: [
            "Diese Cookies sind für das ordnungsgemäße Funktionieren der Website erforderlich.",
            "Sie ermöglichen grundlegende Funktionen wie Seitennavigation und Zugang zu sicheren Bereichen.",
            "Die Website kann ohne diese Cookies nicht richtig funktionieren."
          ]
        },
        {
          title: "Analyse-Cookies",
          icon: BarChart,
          content: [
            "Diese Cookies helfen uns zu verstehen, wie Besucher mit unserer Website interagieren.",
            "Sie sammeln Informationen über die Anzahl der Besucher, Absprungrate, Verkehrsquelle usw.",
            "Diese Daten helfen uns, unsere Website und die Benutzererfahrung zu verbessern."
          ]
        },
        {
          title: "Werbe-Cookies",
          icon: Target,
          content: [
            "Diese Cookies werden verwendet, um Ihnen relevante Werbung zu zeigen.",
            "Sie verfolgen Ihre Surfgewohnheiten, um Ihnen personalisierte Anzeigen zu zeigen.",
            "Sie können von unseren Werbepartnern gesetzt werden."
          ]
        },
        {
          title: "Cookie-Verwaltung",
          icon: Settings,
          content: [
            "Sie können Cookies über Ihre Browsereinstellungen steuern und verwalten.",
            "Die meisten Browser ermöglichen es Ihnen, Cookies abzulehnen oder zu akzeptieren.",
            "Beachten Sie, dass das Deaktivieren bestimmter Cookies die Website-Funktionalität beeinträchtigen kann."
          ]
        },
        {
          title: "Ihre Wahlmöglichkeiten",
          icon: ToggleLeft,
          content: "Sie können wählen, ob Sie Cookies akzeptieren oder ablehnen möchten. Die meisten Webbrowser akzeptieren Cookies automatisch, aber Sie können normalerweise Ihre Browsereinstellungen ändern, um Cookies abzulehnen, wenn Sie dies bevorzugen."
        }
      ],
      contact: "Bei Fragen zu unserer Cookie-Richtlinie kontaktieren Sie uns unter:"
    }
  }

  const c = content[language] || content.en

  return (
    <div className="min-h-screen bg-gradient-to-br from-myhigh5-blue-50 via-white to-myhigh5-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <main className="py-8">
        {/* Hero Section */}
        <section className="relative py-12 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(255,255,255,0.15),transparent_50%)]" />
          <div className="container px-4 md:px-6 relative z-10">
            <div className="max-w-3xl mx-auto text-center text-white">
              <Cookie className="w-12 h-12 mx-auto mb-4" />
              <h1 className="text-3xl md:text-4xl font-black mb-3">
                {c.title}
              </h1>
              <p className="text-base opacity-90">
                {c.lastUpdated}
              </p>
            </div>
          </div>
        </section>

        {/* Content */}
        <section className="container px-4 md:px-6 py-8">
          <div className="max-w-4xl mx-auto">
            {/* Intro */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl p-5 md:p-6 shadow-lg border border-gray-200 dark:border-gray-700 mb-6">
              <p className="text-base text-gray-700 dark:text-gray-300 leading-relaxed">
                {c.intro}
              </p>
            </div>

            {/* Sections */}
            <div className="space-y-4">
              {c.sections.map((section, index) => {
                const Icon = section.icon
                return (
                  <div 
                    key={index}
                    className="bg-white dark:bg-gray-800 rounded-2xl p-5 md:p-6 shadow-lg border border-gray-200 dark:border-gray-700"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center flex-shrink-0">
                        <Icon className="w-5 h-5 text-white" />
                      </div>
                      <div className="flex-1">
                        <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                          {section.title}
                        </h2>
                        {Array.isArray(section.content) ? (
                          <ul className="space-y-2">
                            {section.content.map((item, i) => (
                              <li key={i} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
                                <span className="text-myhigh5-primary mt-1">•</span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                            {section.content}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Contact */}
            <div className="mt-8 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary rounded-2xl p-6 text-center text-white">
              <Mail className="w-10 h-10 mx-auto mb-3 opacity-80" />
              <p className="text-base mb-3">{c.contact}</p>
              <a 
                href="mailto:infos@myhigh5.com" 
                className="inline-flex items-center gap-2 bg-white text-myhigh5-primary px-5 py-2.5 rounded-xl font-semibold hover:bg-gray-100 transition-colors text-sm"
              >
                <Mail className="w-4 h-4" />
                infos@myhigh5.com
              </a>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
