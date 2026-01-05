"use client"

import * as React from "react"
import { useLanguage } from "@/contexts/language-context"
import { 
  Shield, 
  Database, 
  Eye, 
  Share2, 
  Lock, 
  Cookie, 
  UserCheck, 
  Clock, 
  ExternalLink,
  RefreshCw,
  Mail
} from "lucide-react"

export default function PrivacyMobilePage() {
  const { language } = useLanguage()

  const content: Record<string, {
    title: string
    lastUpdated: string
    intro: string
    sections: { title: string; icon: React.ElementType; content: string | string[] }[]
    contact: string
  }> = {
    en: {
      title: "Privacy Policy",
      lastUpdated: "Last Updated: December 2024",
      intro: "At MyHigh5.com, we value your privacy. This policy explains how we collect, use, and protect your personal information.",
      sections: [
        {
          title: "1. Information We Collect",
          icon: Database,
          content: [
            "Personal Information: Name, email, date of birth, payment details (if applicable).",
            "Usage Data: IP address, browser type, device information.",
            "User-Generated Content: Photos, videos, and other submissions."
          ]
        },
        {
          title: "2. How We Use Your Information",
          icon: Eye,
          content: [
            "Facilitate contest participation and voting.",
            "Process payments and prize distributions.",
            "Improve user experience and security.",
            "Comply with legal obligations."
          ]
        },
        {
          title: "3. Sharing of Information",
          icon: Share2,
          content: [
            "We do not sell your personal information.",
            "Service providers assisting in contest management.",
            "Law enforcement if required by legal authorities.",
            "Sponsors or partners, with your consent.",
            "Displaying ads."
          ]
        },
        {
          title: "4. Data Security",
          icon: Lock,
          content: "We implement strict security measures to protect your data but cannot guarantee absolute security."
        },
        {
          title: "5. Cookies & Tracking Technologies",
          icon: Cookie,
          content: "We use cookies to enhance functionality and analyze traffic. You can manage cookie preferences in your browser settings."
        },
        {
          title: "6. Your Rights",
          icon: UserCheck,
          content: [
            "Request access to your personal data.",
            "Correct or delete your information.",
            "Withdraw consent for data processing."
          ]
        },
        {
          title: "7. Data Retention",
          icon: Clock,
          content: "We retain personal data only as long as necessary for the purposes outlined in this policy."
        },
        {
          title: "8. Third-Party Links",
          icon: ExternalLink,
          content: "Our website may contain links to third-party sites. We are not responsible for their privacy practices."
        },
        {
          title: "9. Updates to This Policy",
          icon: RefreshCw,
          content: "We may update this Privacy Policy from time to time. Significant changes will be communicated on our website."
        }
      ],
      contact: "For inquiries about your data, contact:"
    },
    fr: {
      title: "Politique de Confidentialité",
      lastUpdated: "Dernière mise à jour : Décembre 2024",
      intro: "Chez MyHigh5.com, nous accordons une grande importance à votre vie privée. Cette politique explique comment nous collectons, utilisons et protégeons vos informations personnelles.",
      sections: [
        {
          title: "1. Informations que nous collectons",
          icon: Database,
          content: [
            "Informations personnelles : Nom, email, date de naissance, détails de paiement (si applicable).",
            "Données d'utilisation : Adresse IP, type de navigateur, informations sur l'appareil.",
            "Contenu généré par l'utilisateur : Photos, vidéos et autres soumissions."
          ]
        },
        {
          title: "2. Comment nous utilisons vos informations",
          icon: Eye,
          content: [
            "Faciliter la participation aux concours et le vote.",
            "Traiter les paiements et la distribution des prix.",
            "Améliorer l'expérience utilisateur et la sécurité.",
            "Se conformer aux obligations légales."
          ]
        },
        {
          title: "3. Partage des informations",
          icon: Share2,
          content: [
            "Nous ne vendons pas vos informations personnelles.",
            "Prestataires de services assistant à la gestion des concours.",
            "Forces de l'ordre si requis par les autorités légales.",
            "Sponsors ou partenaires, avec votre consentement.",
            "Affichage de publicités."
          ]
        },
        {
          title: "4. Sécurité des données",
          icon: Lock,
          content: "Nous mettons en œuvre des mesures de sécurité strictes pour protéger vos données, mais ne pouvons garantir une sécurité absolue."
        },
        {
          title: "5. Cookies et technologies de suivi",
          icon: Cookie,
          content: "Nous utilisons des cookies pour améliorer les fonctionnalités et analyser le trafic. Vous pouvez gérer vos préférences de cookies dans les paramètres de votre navigateur."
        },
        {
          title: "6. Vos droits",
          icon: UserCheck,
          content: [
            "Demander l'accès à vos données personnelles.",
            "Corriger ou supprimer vos informations.",
            "Retirer votre consentement au traitement des données."
          ]
        },
        {
          title: "7. Conservation des données",
          icon: Clock,
          content: "Nous conservons les données personnelles uniquement aussi longtemps que nécessaire aux fins décrites dans cette politique."
        },
        {
          title: "8. Liens vers des tiers",
          icon: ExternalLink,
          content: "Notre site peut contenir des liens vers des sites tiers. Nous ne sommes pas responsables de leurs pratiques en matière de confidentialité."
        },
        {
          title: "9. Mises à jour de cette politique",
          icon: RefreshCw,
          content: "Nous pouvons mettre à jour cette Politique de confidentialité de temps à autre. Les changements importants seront communiqués sur notre site."
        }
      ],
      contact: "Pour toute question concernant vos données, contactez :"
    },
    es: {
      title: "Política de Privacidad",
      lastUpdated: "Última actualización: Diciembre 2024",
      intro: "En MyHigh5.com, valoramos tu privacidad. Esta política explica cómo recopilamos, usamos y protegemos tu información personal.",
      sections: [
        {
          title: "1. Información que recopilamos",
          icon: Database,
          content: [
            "Información personal: Nombre, email, fecha de nacimiento, detalles de pago (si aplica).",
            "Datos de uso: Dirección IP, tipo de navegador, información del dispositivo.",
            "Contenido generado por el usuario: Fotos, videos y otras presentaciones."
          ]
        },
        {
          title: "2. Cómo usamos tu información",
          icon: Eye,
          content: [
            "Facilitar la participación en concursos y votaciones.",
            "Procesar pagos y distribución de premios.",
            "Mejorar la experiencia del usuario y la seguridad.",
            "Cumplir con obligaciones legales."
          ]
        },
        {
          title: "3. Compartir información",
          icon: Share2,
          content: [
            "No vendemos tu información personal.",
            "Proveedores de servicios que ayudan en la gestión de concursos.",
            "Autoridades legales si lo requieren.",
            "Patrocinadores o socios, con tu consentimiento.",
            "Mostrar anuncios."
          ]
        },
        {
          title: "4. Seguridad de datos",
          icon: Lock,
          content: "Implementamos medidas de seguridad estrictas para proteger tus datos, pero no podemos garantizar una seguridad absoluta."
        },
        {
          title: "5. Cookies y tecnologías de seguimiento",
          icon: Cookie,
          content: "Usamos cookies para mejorar la funcionalidad y analizar el tráfico. Puedes gestionar las preferencias de cookies en la configuración de tu navegador."
        },
        {
          title: "6. Tus derechos",
          icon: UserCheck,
          content: [
            "Solicitar acceso a tus datos personales.",
            "Corregir o eliminar tu información.",
            "Retirar el consentimiento para el procesamiento de datos."
          ]
        },
        {
          title: "7. Retención de datos",
          icon: Clock,
          content: "Retenemos los datos personales solo el tiempo necesario para los fines descritos en esta política."
        },
        {
          title: "8. Enlaces de terceros",
          icon: ExternalLink,
          content: "Nuestro sitio web puede contener enlaces a sitios de terceros. No somos responsables de sus prácticas de privacidad."
        },
        {
          title: "9. Actualizaciones de esta política",
          icon: RefreshCw,
          content: "Podemos actualizar esta Política de Privacidad de vez en cuando. Los cambios significativos se comunicarán en nuestro sitio web."
        }
      ],
      contact: "Para consultas sobre tus datos, contáctanos en:"
    },
    de: {
      title: "Datenschutzrichtlinie",
      lastUpdated: "Zuletzt aktualisiert: Dezember 2024",
      intro: "Bei MyHigh5.com schätzen wir Ihre Privatsphäre. Diese Richtlinie erklärt, wie wir Ihre persönlichen Informationen sammeln, verwenden und schützen.",
      sections: [
        {
          title: "1. Informationen, die wir sammeln",
          icon: Database,
          content: [
            "Persönliche Informationen: Name, E-Mail, Geburtsdatum, Zahlungsdetails (falls zutreffend).",
            "Nutzungsdaten: IP-Adresse, Browsertyp, Geräteinformationen.",
            "Vom Benutzer erstellte Inhalte: Fotos, Videos und andere Einreichungen."
          ]
        },
        {
          title: "2. Wie wir Ihre Informationen verwenden",
          icon: Eye,
          content: [
            "Erleichterung der Wettbewerbsteilnahme und Abstimmung.",
            "Verarbeitung von Zahlungen und Preisverteilungen.",
            "Verbesserung der Benutzererfahrung und Sicherheit.",
            "Einhaltung gesetzlicher Verpflichtungen."
          ]
        },
        {
          title: "3. Weitergabe von Informationen",
          icon: Share2,
          content: [
            "Wir verkaufen Ihre persönlichen Informationen nicht.",
            "Dienstleister, die bei der Wettbewerbsverwaltung helfen.",
            "Strafverfolgungsbehörden, wenn von Behörden verlangt.",
            "Sponsoren oder Partner, mit Ihrer Zustimmung.",
            "Anzeige von Werbung."
          ]
        },
        {
          title: "4. Datensicherheit",
          icon: Lock,
          content: "Wir implementieren strenge Sicherheitsmaßnahmen zum Schutz Ihrer Daten, können jedoch keine absolute Sicherheit garantieren."
        },
        {
          title: "5. Cookies und Tracking-Technologien",
          icon: Cookie,
          content: "Wir verwenden Cookies, um die Funktionalität zu verbessern und den Verkehr zu analysieren. Sie können die Cookie-Einstellungen in Ihren Browsereinstellungen verwalten."
        },
        {
          title: "6. Ihre Rechte",
          icon: UserCheck,
          content: [
            "Zugang zu Ihren persönlichen Daten anfordern.",
            "Ihre Informationen korrigieren oder löschen.",
            "Die Einwilligung zur Datenverarbeitung widerrufen."
          ]
        },
        {
          title: "7. Datenspeicherung",
          icon: Clock,
          content: "Wir speichern personenbezogene Daten nur so lange, wie es für die in dieser Richtlinie beschriebenen Zwecke erforderlich ist."
        },
        {
          title: "8. Links zu Drittanbietern",
          icon: ExternalLink,
          content: "Unsere Website kann Links zu Websites Dritter enthalten. Wir sind nicht für deren Datenschutzpraktiken verantwortlich."
        },
        {
          title: "9. Aktualisierungen dieser Richtlinie",
          icon: RefreshCw,
          content: "Wir können diese Datenschutzrichtlinie von Zeit zu Zeit aktualisieren. Wesentliche Änderungen werden auf unserer Website mitgeteilt."
        }
      ],
      contact: "Für Anfragen zu Ihren Daten kontaktieren Sie uns unter:"
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
              <Shield className="w-12 h-12 mx-auto mb-4" />
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
