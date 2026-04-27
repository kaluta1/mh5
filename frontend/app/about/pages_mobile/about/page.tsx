"use client"

import * as React from "react"
import { useLanguage } from "@/contexts/language-context"
import { 
  Heart, 
  Globe, 
  Users, 
  Trophy, 
  Target, 
  Sparkles,
  Shield,
  Award,
  CheckCircle
} from "lucide-react"

export default function AboutMobilePage() {
  const { t, language } = useLanguage()

  const stats = [
    { icon: Users, value: "1M+", labelKey: "stats.users" },
    { icon: Globe, value: "200+", labelKey: "stats.countries" },
    { icon: Trophy, value: "50K+", labelKey: "stats.contests" },
    { icon: Award, value: "10M+", labelKey: "stats.votes" },
  ]

  const statsLabels: Record<string, Record<string, string>> = {
    en: { "stats.users": "Active users", "stats.countries": "Countries", "stats.contests": "Contests organized", "stats.votes": "Votes recorded" },
    fr: { "stats.users": "Utilisateurs actifs", "stats.countries": "Pays représentés", "stats.contests": "Concours organisés", "stats.votes": "Votes enregistrés" },
    es: { "stats.users": "Usuarios activos", "stats.countries": "Países representados", "stats.contests": "Concursos organizados", "stats.votes": "Votos registrados" },
    de: { "stats.users": "Aktive Nutzer", "stats.countries": "Länder vertreten", "stats.contests": "Wettbewerbe organisiert", "stats.votes": "Stimmen registriert" },
  }

  const values = [
    { icon: Shield, titleKey: "values.transparency", descKey: "values.transparency_desc" },
    { icon: Globe, titleKey: "values.inclusivity", descKey: "values.inclusivity_desc" },
    { icon: Sparkles, titleKey: "values.innovation", descKey: "values.innovation_desc" },
    { icon: Heart, titleKey: "values.community", descKey: "values.community_desc" },
  ]

  const valuesLabels: Record<string, Record<string, string>> = {
    en: {
      "values.transparency": "Transparency", "values.transparency_desc": "A fair and transparent voting system where every voice counts.",
      "values.inclusivity": "Inclusivity", "values.inclusivity_desc": "A platform open to all, regardless of gender, origin or location.",
      "values.innovation": "Innovation", "values.innovation_desc": "Cutting-edge technologies for an exceptional user experience.",
      "values.community": "Community", "values.community_desc": "Creating connections between talents from around the world."
    },
    fr: {
      "values.transparency": "Transparence", "values.transparency_desc": "Un système de vote équitable et transparent où chaque voix compte.",
      "values.inclusivity": "Inclusivité", "values.inclusivity_desc": "Une plateforme ouverte à tous, sans distinction de genre, d'origine ou de localisation.",
      "values.innovation": "Innovation", "values.innovation_desc": "Des technologies de pointe pour une expérience utilisateur exceptionnelle.",
      "values.community": "Communauté", "values.community_desc": "Créer des liens entre les talents du monde entier."
    },
    es: {
      "values.transparency": "Transparencia", "values.transparency_desc": "Un sistema de votación justo y transparente donde cada voz cuenta.",
      "values.inclusivity": "Inclusividad", "values.inclusivity_desc": "Una plataforma abierta a todos, sin distinción de género, origen o ubicación.",
      "values.innovation": "Innovación", "values.innovation_desc": "Tecnologías de vanguardia para una experiencia de usuario excepcional.",
      "values.community": "Comunidad", "values.community_desc": "Crear conexiones entre talentos de todo el mundo."
    },
    de: {
      "values.transparency": "Transparenz", "values.transparency_desc": "Ein faires und transparentes Abstimmungssystem, bei dem jede Stimme zählt.",
      "values.inclusivity": "Inklusivität", "values.inclusivity_desc": "Eine Plattform für alle, unabhängig von Geschlecht, Herkunft oder Standort.",
      "values.innovation": "Innovation", "values.innovation_desc": "Modernste Technologien für ein außergewöhnliches Benutzererlebnis.",
      "values.community": "Gemeinschaft", "values.community_desc": "Verbindungen zwischen Talenten aus aller Welt schaffen."
    },
  }

  const getLabel = (labels: Record<string, Record<string, string>>, key: string) => {
    return labels[language]?.[key] || labels.en[key] || key
  }

  const missionFeatures: Record<string, string[]> = {
    en: ["City to global level progression", "Fair MyHigh5 voting system (5-4-3-2-1)", "10-level affiliate program", "AI moderation for a safe environment"],
    fr: ["Progression du niveau ville au niveau mondial", "Système de vote équitable MyHigh5 (5-4-3-2-1)", "Programme d'affiliation à 10 niveaux", "Modération IA pour un environnement sûr"],
    es: ["Progresión del nivel ciudad al global", "Sistema de votación justo MyHigh5 (5-4-3-2-1)", "Programa de afiliados de 10 niveles", "Moderación IA para un entorno seguro"],
    de: ["Aufstieg von Stadt- zu Globalebene", "Faires MyHigh5-Abstimmungssystem (5-4-3-2-1)", "10-stufiges Partnerprogramm", "KI-Moderation für eine sichere Umgebung"],
  }

  const team = [
    { name: "Shafi Kaluta Abedi", roleKey: "team.founder_president", image: "/team/shafi-kaluta-abedi.png" },
    { name: "Morice Wangwe", roleKey: "team.director_ict", image: "/team/morice-wangwe.png" },
  ]

  const teamLabels: Record<string, Record<string, string>> = {
    en: {
      "team.founder_president": "Founder and President",
      "team.director_ict": "Director of ICT"
    },
    fr: {
      "team.founder_president": "Fondateur et Président",
      "team.director_ict": "Directeur des TIC"
    },
    es: {
      "team.founder_president": "Fundador y Presidente",
      "team.director_ict": "Director de TIC"
    },
    de: {
      "team.founder_president": "Gründer und Präsident",
      "team.director_ict": "Direktor für IKT"
    },
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-myhigh5-blue-50 via-white to-myhigh5-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <main className="py-8">
        {/* Hero Section */}
        <section className="relative py-12 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(255,255,255,0.15),transparent_50%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_80%,rgba(255,255,255,0.1),transparent_40%)]" />
          <div className="container px-4 md:px-6 relative z-10">
            <div className="max-w-4xl mx-auto text-center text-white">
              <Heart className="w-12 h-12 mx-auto mb-4 animate-pulse" />
              <h1 className="text-3xl md:text-4xl font-black mb-4">
                {t('pages.about.title') || "À Propos de MyHigh5"}
              </h1>
              <p className="text-lg md:text-xl opacity-90 leading-relaxed">
                {t('pages.about.subtitle') || "La première plateforme mondiale de concours qui connecte les talents du monde entier, du niveau local au niveau mondial."}
              </p>
            </div>
          </div>
        </section>

        {/* Mission Section */}
        <section className="container px-4 md:px-6 py-12">
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div>
              <Target className="w-10 h-10 text-myhigh5-primary mb-4" />
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-4">
                {t('pages.about.mission.title') || "Notre Mission"}
              </h2>
              <p className="text-base text-gray-600 dark:text-gray-400 mb-4 leading-relaxed">
                {t('pages.about.mission.description') || "Démocratiser l'accès aux concours et permettre à chaque talent de briller sur la scène mondiale. Du concours de beauté local au championnat mondial, nous créons des opportunités pour tous."}
              </p>
              <ul className="space-y-3">
                {(missionFeatures[language] || missionFeatures.en).map((item, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                    <span className="text-sm text-gray-700 dark:text-gray-300">{item}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-800/60 p-3">
                <p className="text-xs font-semibold text-gray-900 dark:text-white leading-relaxed">
                  Registered Office: 77 HIGH STREET, #10-12B HIGH STREET PLAZA, SINGAPORE 179433.
                </p>
              </div>
            </div>
            <div className="relative">
              <div className="aspect-square rounded-3xl bg-gradient-to-br from-myhigh5-primary/20 to-myhigh5-secondary/20 flex items-center justify-center">
                <div className="w-3/4 h-3/4 rounded-2xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center shadow-2xl">
                  <Globe className="w-24 h-24 text-white/80" />
                </div>
              </div>
              <div className="absolute -top-4 -right-4 w-16 h-16 bg-amber-400 rounded-2xl flex items-center justify-center shadow-lg animate-bounce">
                <Trophy className="w-8 h-8 text-white" />
              </div>
              <div className="absolute -bottom-4 -left-4 w-14 h-14 bg-myhigh5-secondary rounded-xl flex items-center justify-center shadow-lg animate-pulse">
                <Heart className="w-7 h-7 text-white" />
              </div>
            </div>
          </div>
        </section>

        {/* Values Section */}
        <section className="py-12 bg-gray-50 dark:bg-gray-800/50">
          <div className="container px-4 md:px-6">
            <div className="text-center mb-8">
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-3">
                {t('pages.about.values.title') || "Nos Valeurs"}
              </h2>
              <p className="text-base text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
                {t('pages.about.values.subtitle') || "Les principes qui guident chacune de nos décisions"}
              </p>
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              {values.map((value, index) => (
                <div 
                  key={index}
                  className="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow-lg border border-gray-200 dark:border-gray-700"
                >
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center mb-3">
                    <value.icon className="w-6 h-6 text-white" />
                  </div>
                  <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                    {getLabel(valuesLabels, value.titleKey)}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {getLabel(valuesLabels, value.descKey)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Team Section */}
        <section className="py-12 bg-gray-50 dark:bg-gray-800/50">
          <div className="container px-4 md:px-6">
            <div className="text-center mb-8">
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-3">
                {t('pages.about.team.title') || "Notre Équipe"}
              </h2>
              <p className="text-base text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
                {t('pages.about.team.subtitle') || "Des passionnés dédiés à votre succès"}
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto">
              {team.map((member, index) => (
                <div
                  key={index}
                  className="text-center group"
                >
                  <div className="w-20 h-20 mx-auto mb-3 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center text-3xl shadow-lg group-hover:scale-110 transition-transform duration-300 overflow-hidden">
                    {member.image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={member.image}
                        alt={member.name}
                        className="w-full h-full object-cover object-top"
                      />
                    ) : (
                      member.emoji
                    )}
                  </div>
                  <h3 className="font-bold text-gray-900 dark:text-white">
                    {member.name}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {getLabel(teamLabels, member.roleKey)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
