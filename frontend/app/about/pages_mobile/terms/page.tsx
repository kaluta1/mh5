"use client"

import * as React from "react"
import { useLanguage } from "@/contexts/language-context"
import { 
  FileText, 
  CheckCircle, 
  Users, 
  Trophy, 
  CreditCard, 
  Image, 
  UserCheck, 
  XCircle, 
  AlertTriangle,
  RefreshCw,
  Mail
} from "lucide-react"

export default function TermsMobilePage() {
  const { language } = useLanguage()

  const content: Record<string, {
    title: string
    lastUpdated: string
    intro: string
    sections: { title: string; icon: React.ElementType; content: string | string[] }[]
    contact: string
  }> = {
    en: {
      title: "Terms of Service",
      lastUpdated: "Last Updated: December 2024",
      intro: "Welcome to MyHigh5.com! By using our platform, you agree to comply with these Terms of Service. Please read them carefully.",
      sections: [
        {
          title: "1. Acceptance of Terms",
          icon: CheckCircle,
          content: "By accessing or using MyHigh5.com (\"the Website\"), you agree to be bound by these Terms of Service and all applicable laws and regulations. If you do not agree, please do not use the Website."
        },
        {
          title: "2. Eligibility",
          icon: Users,
          content: "To participate in contests, you must be at least 18 years old or have parental consent if you are a minor. Some contests may have additional eligibility criteria."
        },
        {
          title: "3. Account Registration",
          icon: UserCheck,
          content: [
            "You must provide accurate information when creating an account.",
            "You are responsible for maintaining the confidentiality of your account credentials.",
            "We reserve the right to suspend or terminate accounts that violate our policies."
          ]
        },
        {
          title: "4. Contest Rules & Fair Play",
          icon: Trophy,
          content: [
            "Each contest has its own rules, which must be followed.",
            "Cheating, fraudulent votes, or unethical conduct will result in disqualification.",
            "Our decisions regarding contest results are final."
          ]
        },
        {
          title: "5. Payments & Prizes",
          icon: CreditCard,
          content: [
            "Prizes are awarded based on competition outcomes and are subject to verification.",
            "We may require additional information before processing payments.",
            "Taxes, if applicable, are the winner's responsibility."
          ]
        },
        {
          title: "6. Content Ownership & Usage",
          icon: Image,
          content: [
            "By submitting content (photos, videos, etc.), you grant us a worldwide, royalty-free license to use, display, and promote your content.",
            "You must own or have the right to use any content you upload."
          ]
        },
        {
          title: "7. User Conduct",
          icon: XCircle,
          content: [
            "Violate any laws or third-party rights.",
            "Post harmful, offensive, or inappropriate content.",
            "Attempt to manipulate contest outcomes unfairly."
          ]
        },
        {
          title: "8. Termination",
          icon: AlertTriangle,
          content: "We reserve the right to terminate or suspend accounts for violations of these terms, without prior notice."
        },
        {
          title: "9. Limitation of Liability",
          icon: AlertTriangle,
          content: [
            "Technical errors or interruptions.",
            "User actions or content posted by participants.",
            "Contest cancellations or modifications."
          ]
        },
        {
          title: "10. Changes to Terms",
          icon: RefreshCw,
          content: "We may update these Terms of Service at any time. Continued use of the Website constitutes acceptance of the updated terms."
        }
      ],
      contact: "For questions or concerns, contact us at:"
    },
    fr: {
      title: "Conditions d'utilisation",
      lastUpdated: "Dernière mise à jour : Décembre 2024",
      intro: "Bienvenue sur MyHigh5.com ! En utilisant notre plateforme, vous acceptez de respecter ces Conditions d'utilisation. Veuillez les lire attentivement.",
      sections: [
        {
          title: "1. Acceptation des conditions",
          icon: CheckCircle,
          content: "En accédant ou en utilisant MyHigh5.com (« le Site »), vous acceptez d'être lié par ces Conditions d'utilisation et par toutes les lois et réglementations applicables. Si vous n'êtes pas d'accord, veuillez ne pas utiliser le Site."
        },
        {
          title: "2. Éligibilité",
          icon: Users,
          content: "Pour participer aux concours, vous devez avoir au moins 18 ans ou avoir le consentement parental si vous êtes mineur. Certains concours peuvent avoir des critères d'éligibilité supplémentaires."
        },
        {
          title: "3. Inscription au compte",
          icon: UserCheck,
          content: [
            "Vous devez fournir des informations exactes lors de la création d'un compte.",
            "Vous êtes responsable du maintien de la confidentialité de vos identifiants de compte.",
            "Nous nous réservons le droit de suspendre ou de résilier les comptes qui enfreignent nos politiques."
          ]
        },
        {
          title: "4. Règles des concours et fair-play",
          icon: Trophy,
          content: [
            "Chaque concours a ses propres règles, qui doivent être respectées.",
            "La triche, les votes frauduleux ou les comportements contraires à l'éthique entraîneront une disqualification.",
            "Nos décisions concernant les résultats des concours sont définitives."
          ]
        },
        {
          title: "5. Paiements et prix",
          icon: CreditCard,
          content: [
            "Les prix sont attribués en fonction des résultats des compétitions et sont soumis à vérification.",
            "Nous pouvons demander des informations supplémentaires avant de traiter les paiements.",
            "Les taxes, le cas échéant, sont à la charge du gagnant."
          ]
        },
        {
          title: "6. Propriété et utilisation du contenu",
          icon: Image,
          content: [
            "En soumettant du contenu (photos, vidéos, etc.), vous nous accordez une licence mondiale et gratuite pour utiliser, afficher et promouvoir votre contenu.",
            "Vous devez posséder ou avoir le droit d'utiliser tout contenu que vous téléchargez."
          ]
        },
        {
          title: "7. Conduite des utilisateurs",
          icon: XCircle,
          content: [
            "Violer les lois ou les droits de tiers.",
            "Publier du contenu nuisible, offensant ou inapproprié.",
            "Tenter de manipuler les résultats des concours de manière déloyale."
          ]
        },
        {
          title: "8. Résiliation",
          icon: AlertTriangle,
          content: "Nous nous réservons le droit de résilier ou de suspendre les comptes pour violation de ces conditions, sans préavis."
        },
        {
          title: "9. Limitation de responsabilité",
          icon: AlertTriangle,
          content: [
            "Erreurs techniques ou interruptions.",
            "Actions des utilisateurs ou contenu publié par les participants.",
            "Annulations ou modifications de concours."
          ]
        },
        {
          title: "10. Modifications des conditions",
          icon: RefreshCw,
          content: "Nous pouvons mettre à jour ces Conditions d'utilisation à tout moment. L'utilisation continue du Site constitue l'acceptation des conditions mises à jour."
        }
      ],
      contact: "Pour toute question ou préoccupation, contactez-nous à :"
    },
    es: {
      title: "Términos de Servicio",
      lastUpdated: "Última actualización: Diciembre 2024",
      intro: "¡Bienvenido a MyHigh5.com! Al usar nuestra plataforma, aceptas cumplir con estos Términos de Servicio. Por favor, léelos detenidamente.",
      sections: [
        {
          title: "1. Aceptación de los términos",
          icon: CheckCircle,
          content: "Al acceder o usar MyHigh5.com (\"el Sitio Web\"), aceptas estar sujeto a estos Términos de Servicio y a todas las leyes y regulaciones aplicables. Si no estás de acuerdo, por favor no uses el Sitio Web."
        },
        {
          title: "2. Elegibilidad",
          icon: Users,
          content: "Para participar en concursos, debes tener al menos 18 años o contar con el consentimiento de tus padres si eres menor. Algunos concursos pueden tener criterios de elegibilidad adicionales."
        },
        {
          title: "3. Registro de cuenta",
          icon: UserCheck,
          content: [
            "Debes proporcionar información precisa al crear una cuenta.",
            "Eres responsable de mantener la confidencialidad de tus credenciales de cuenta.",
            "Nos reservamos el derecho de suspender o cancelar cuentas que violen nuestras políticas."
          ]
        },
        {
          title: "4. Reglas del concurso y juego limpio",
          icon: Trophy,
          content: [
            "Cada concurso tiene sus propias reglas, que deben seguirse.",
            "El engaño, los votos fraudulentos o la conducta poco ética resultarán en descalificación.",
            "Nuestras decisiones sobre los resultados del concurso son definitivas."
          ]
        },
        {
          title: "5. Pagos y premios",
          icon: CreditCard,
          content: [
            "Los premios se otorgan según los resultados de la competencia y están sujetos a verificación.",
            "Podemos requerir información adicional antes de procesar los pagos.",
            "Los impuestos, si corresponden, son responsabilidad del ganador."
          ]
        },
        {
          title: "6. Propiedad y uso del contenido",
          icon: Image,
          content: [
            "Al enviar contenido (fotos, videos, etc.), nos otorgas una licencia mundial y libre de regalías para usar, mostrar y promocionar tu contenido.",
            "Debes poseer o tener derecho a usar cualquier contenido que subas."
          ]
        },
        {
          title: "7. Conducta del usuario",
          icon: XCircle,
          content: [
            "Violar leyes o derechos de terceros.",
            "Publicar contenido dañino, ofensivo o inapropiado.",
            "Intentar manipular los resultados del concurso de manera injusta."
          ]
        },
        {
          title: "8. Terminación",
          icon: AlertTriangle,
          content: "Nos reservamos el derecho de terminar o suspender cuentas por violaciones de estos términos, sin previo aviso."
        },
        {
          title: "9. Limitación de responsabilidad",
          icon: AlertTriangle,
          content: [
            "Errores técnicos o interrupciones.",
            "Acciones del usuario o contenido publicado por participantes.",
            "Cancelaciones o modificaciones de concursos."
          ]
        },
        {
          title: "10. Cambios en los términos",
          icon: RefreshCw,
          content: "Podemos actualizar estos Términos de Servicio en cualquier momento. El uso continuado del Sitio Web constituye la aceptación de los términos actualizados."
        }
      ],
      contact: "Para preguntas o inquietudes, contáctenos en:"
    },
    de: {
      title: "Nutzungsbedingungen",
      lastUpdated: "Zuletzt aktualisiert: Dezember 2024",
      intro: "Willkommen bei MyHigh5.com! Durch die Nutzung unserer Plattform erklären Sie sich mit diesen Nutzungsbedingungen einverstanden. Bitte lesen Sie sie sorgfältig durch.",
      sections: [
        {
          title: "1. Annahme der Bedingungen",
          icon: CheckCircle,
          content: "Durch den Zugriff auf oder die Nutzung von MyHigh5.com (\"die Website\") erklären Sie sich mit diesen Nutzungsbedingungen und allen geltenden Gesetzen und Vorschriften einverstanden. Wenn Sie nicht einverstanden sind, nutzen Sie die Website bitte nicht."
        },
        {
          title: "2. Teilnahmeberechtigung",
          icon: Users,
          content: "Um an Wettbewerben teilzunehmen, müssen Sie mindestens 18 Jahre alt sein oder die Zustimmung der Eltern haben, wenn Sie minderjährig sind. Einige Wettbewerbe können zusätzliche Teilnahmekriterien haben."
        },
        {
          title: "3. Kontoregistrierung",
          icon: UserCheck,
          content: [
            "Sie müssen bei der Erstellung eines Kontos genaue Informationen angeben.",
            "Sie sind für die Wahrung der Vertraulichkeit Ihrer Kontodaten verantwortlich.",
            "Wir behalten uns das Recht vor, Konten zu sperren oder zu kündigen, die gegen unsere Richtlinien verstoßen."
          ]
        },
        {
          title: "4. Wettbewerbsregeln und Fair Play",
          icon: Trophy,
          content: [
            "Jeder Wettbewerb hat seine eigenen Regeln, die befolgt werden müssen.",
            "Betrug, betrügerische Stimmen oder unethisches Verhalten führen zur Disqualifikation.",
            "Unsere Entscheidungen bezüglich der Wettbewerbsergebnisse sind endgültig."
          ]
        },
        {
          title: "5. Zahlungen und Preise",
          icon: CreditCard,
          content: [
            "Preise werden basierend auf Wettbewerbsergebnissen vergeben und unterliegen der Überprüfung.",
            "Wir können vor der Bearbeitung von Zahlungen zusätzliche Informationen anfordern.",
            "Steuern, falls zutreffend, liegen in der Verantwortung des Gewinners."
          ]
        },
        {
          title: "6. Eigentum und Nutzung von Inhalten",
          icon: Image,
          content: [
            "Durch das Einreichen von Inhalten (Fotos, Videos usw.) gewähren Sie uns eine weltweite, gebührenfreie Lizenz zur Nutzung, Anzeige und Bewerbung Ihrer Inhalte.",
            "Sie müssen Eigentümer sein oder das Recht haben, alle Inhalte zu verwenden, die Sie hochladen."
          ]
        },
        {
          title: "7. Benutzerverhalten",
          icon: XCircle,
          content: [
            "Gesetze oder Rechte Dritter verletzen.",
            "Schädliche, beleidigende oder unangemessene Inhalte veröffentlichen.",
            "Versuchen, Wettbewerbsergebnisse unfair zu manipulieren."
          ]
        },
        {
          title: "8. Kündigung",
          icon: AlertTriangle,
          content: "Wir behalten uns das Recht vor, Konten wegen Verstößen gegen diese Bedingungen ohne vorherige Ankündigung zu kündigen oder zu sperren."
        },
        {
          title: "9. Haftungsbeschränkung",
          icon: AlertTriangle,
          content: [
            "Technische Fehler oder Unterbrechungen.",
            "Benutzeraktionen oder von Teilnehmern gepostete Inhalte.",
            "Absagen oder Änderungen von Wettbewerben."
          ]
        },
        {
          title: "10. Änderungen der Bedingungen",
          icon: RefreshCw,
          content: "Wir können diese Nutzungsbedingungen jederzeit aktualisieren. Die fortgesetzte Nutzung der Website gilt als Annahme der aktualisierten Bedingungen."
        }
      ],
      contact: "Bei Fragen oder Bedenken kontaktieren Sie uns unter:"
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
              <FileText className="w-12 h-12 mx-auto mb-4" />
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
