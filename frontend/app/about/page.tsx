"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/layout/header"
import { Footer } from "@/components/sections/footer"
import { useLanguage } from "@/contexts/language-context"
import { Button } from "@/components/ui/button"
import { 
  Heart, 
  Globe, 
  Users, 
  Trophy, 
  Target, 
  Sparkles,
  Shield,
  Award,
  ArrowRight,
  CheckCircle
} from "lucide-react"

export default function AboutPage() {
  const { t, language } = useLanguage()
  const router = useRouter()

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

  const timeline = [
    { year: "2024", titleKey: "timeline.launch", descKey: "timeline.launch_desc" },
    { year: "2024", titleKey: "timeline.expansion", descKey: "timeline.expansion_desc" },
    { year: "2025", titleKey: "timeline.innovation", descKey: "timeline.innovation_desc" },
    { year: "2025", titleKey: "timeline.growth", descKey: "timeline.growth_desc" },
  ]

  const timelineLabels: Record<string, Record<string, string>> = {
    en: {
      "timeline.launch": "Launch", "timeline.launch_desc": "Creation of MyHigh5 with a global vision",
      "timeline.expansion": "Expansion", "timeline.expansion_desc": "Opening in 50 countries simultaneously",
      "timeline.innovation": "Innovation", "timeline.innovation_desc": "Launch of unique MyHigh5 voting system",
      "timeline.growth": "Growth", "timeline.growth_desc": "1 million users reached"
    },
    fr: {
      "timeline.launch": "Lancement", "timeline.launch_desc": "Création de MyHigh5 avec une vision globale",
      "timeline.expansion": "Expansion", "timeline.expansion_desc": "Ouverture dans 50 pays simultanément",
      "timeline.innovation": "Innovation", "timeline.innovation_desc": "Lancement du système de vote MyHigh5 unique",
      "timeline.growth": "Croissance", "timeline.growth_desc": "1 million d'utilisateurs atteints"
    },
    es: {
      "timeline.launch": "Lanzamiento", "timeline.launch_desc": "Creación de MyHigh5 con una visión global",
      "timeline.expansion": "Expansión", "timeline.expansion_desc": "Apertura en 50 países simultáneamente",
      "timeline.innovation": "Innovación", "timeline.innovation_desc": "Lanzamiento del sistema de votación MyHigh5 único",
      "timeline.growth": "Crecimiento", "timeline.growth_desc": "1 millón de usuarios alcanzados"
    },
    de: {
      "timeline.launch": "Start", "timeline.launch_desc": "Gründung von MyHigh5 mit globaler Vision",
      "timeline.expansion": "Expansion", "timeline.expansion_desc": "Eröffnung in 50 Ländern gleichzeitig",
      "timeline.innovation": "Innovation", "timeline.innovation_desc": "Start des einzigartigen MyHigh5-Abstimmungssystems",
      "timeline.growth": "Wachstum", "timeline.growth_desc": "1 Million Nutzer erreicht"
    },
  }

  const team = [
    { name: "Alexandre Martin", roleKey: "team.ceo", emoji: "👨‍💼" },
    { name: "Sophie Dubois", roleKey: "team.cto", emoji: "👩‍💻" },
    { name: "Marc Laurent", roleKey: "team.product", emoji: "👨‍🎨" },
    { name: "Julie Chen", roleKey: "team.marketing", emoji: "👩‍💼" },
  ]

  const teamLabels: Record<string, Record<string, string>> = {
    en: { "team.ceo": "CEO & Founder", "team.cto": "CTO", "team.product": "Head of Product", "team.marketing": "Head of Marketing" },
    fr: { "team.ceo": "CEO & Fondateur", "team.cto": "CTO", "team.product": "Head of Product", "team.marketing": "Head of Marketing" },
    es: { "team.ceo": "CEO y Fundador", "team.cto": "CTO", "team.product": "Jefe de Producto", "team.marketing": "Jefe de Marketing" },
    de: { "team.ceo": "CEO & Gründer", "team.cto": "CTO", "team.product": "Produktleiter", "team.marketing": "Marketingleiter" },
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-myfav-blue-50 via-white to-myfav-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <Header />
      
      <main className="pt-24 pb-16">
        {/* Hero Section */}
        <section className="relative py-20 bg-gradient-to-r from-myfav-primary to-myfav-secondary overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(255,255,255,0.15),transparent_50%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_80%,rgba(255,255,255,0.1),transparent_40%)]" />
          <div className="container px-4 md:px-6 relative z-10">
            <div className="max-w-4xl mx-auto text-center text-white">
              <Heart className="w-16 h-16 mx-auto mb-6 animate-pulse" />
              <h1 className="text-4xl md:text-6xl font-black mb-6">
                {t('pages.about.title') || "À Propos de MyHigh5"}
              </h1>
              <p className="text-xl md:text-2xl opacity-90 leading-relaxed">
                {t('pages.about.subtitle') || "La première plateforme mondiale de concours qui connecte les talents du monde entier, du niveau local au niveau mondial."}
              </p>
            </div>
          </div>
        </section>

        {/* Stats Section */}
        <section className="container px-4 md:px-6 -mt-12 relative z-20">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
            {stats.map((stat, index) => (
              <div 
                key={index}
                className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-xl border border-gray-200 dark:border-gray-700 text-center hover:shadow-2xl transition-all duration-300 hover:-translate-y-1"
              >
                <stat.icon className="w-10 h-10 mx-auto mb-3 text-myfav-primary" />
                <div className="text-3xl md:text-4xl font-black text-gray-900 dark:text-white mb-1">
                  {stat.value}
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  {getLabel(statsLabels, stat.labelKey)}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Mission Section */}
        <section className="container px-4 md:px-6 py-20">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <Target className="w-12 h-12 text-myfav-primary mb-6" />
              <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-6">
                {t('pages.about.mission.title') || "Notre Mission"}
              </h2>
              <p className="text-lg text-gray-600 dark:text-gray-400 mb-6 leading-relaxed">
                {t('pages.about.mission.description') || "Démocratiser l'accès aux concours et permettre à chaque talent de briller sur la scène mondiale. Du concours de beauté local au championnat mondial, nous créons des opportunités pour tous."}
              </p>
              <ul className="space-y-4">
                {(missionFeatures[language] || missionFeatures.en).map((item, i) => (
                  <li key={i} className="flex items-center gap-3">
                    <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />
                    <span className="text-gray-700 dark:text-gray-300">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="relative">
              <div className="aspect-square rounded-3xl bg-gradient-to-br from-myfav-primary/20 to-myfav-secondary/20 flex items-center justify-center">
                <div className="w-3/4 h-3/4 rounded-2xl bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center shadow-2xl">
                  <Globe className="w-32 h-32 text-white/80" />
                </div>
              </div>
              {/* Floating elements */}
              <div className="absolute -top-4 -right-4 w-20 h-20 bg-amber-400 rounded-2xl flex items-center justify-center shadow-lg animate-bounce">
                <Trophy className="w-10 h-10 text-white" />
              </div>
              <div className="absolute -bottom-4 -left-4 w-16 h-16 bg-myfav-secondary rounded-xl flex items-center justify-center shadow-lg animate-pulse">
                <Heart className="w-8 h-8 text-white" />
              </div>
            </div>
          </div>
        </section>

        {/* Values Section */}
        <section className="py-20 bg-gray-50 dark:bg-gray-800/50">
          <div className="container px-4 md:px-6">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">
                {t('pages.about.values.title') || "Nos Valeurs"}
              </h2>
              <p className="text-lg text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
                {t('pages.about.values.subtitle') || "Les principes qui guident chacune de nos décisions"}
              </p>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
              {values.map((value, index) => (
                <div 
                  key={index}
                  className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-lg border border-gray-200 dark:border-gray-700 hover:shadow-xl transition-all duration-300 hover:-translate-y-1"
                >
                  <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center mb-4">
                    <value.icon className="w-7 h-7 text-white" />
                  </div>
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                    {getLabel(valuesLabels, value.titleKey)}
                  </h3>
                  <p className="text-gray-600 dark:text-gray-400">
                    {getLabel(valuesLabels, value.descKey)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Timeline Section */}
        <section className="container px-4 md:px-6 py-20">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">
              {t('pages.about.timeline.title') || "Notre Parcours"}
            </h2>
          </div>
          <div className="max-w-3xl mx-auto">
            <div className="relative">
              {/* Line */}
              <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-gradient-to-b from-myfav-primary to-myfav-secondary" />
              
              {/* Timeline items */}
              {timeline.map((item, index) => (
                <div key={index} className="relative pl-20 pb-12 last:pb-0">
                  <div className="absolute left-6 w-5 h-5 rounded-full bg-myfav-primary border-4 border-white dark:border-gray-900 shadow-lg" />
                  <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-lg border border-gray-200 dark:border-gray-700">
                    <span className="text-sm font-bold text-myfav-primary">{item.year}</span>
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white mt-1 mb-2">
                      {getLabel(timelineLabels, item.titleKey)}
                    </h3>
                    <p className="text-gray-600 dark:text-gray-400">
                      {getLabel(timelineLabels, item.descKey)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Team Section */}
        <section className="py-20 bg-gray-50 dark:bg-gray-800/50">
          <div className="container px-4 md:px-6">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">
                {t('pages.about.team.title') || "Notre Équipe"}
              </h2>
              <p className="text-lg text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
                {t('pages.about.team.subtitle') || "Des passionnés dédiés à votre succès"}
              </p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 max-w-4xl mx-auto">
              {team.map((member, index) => (
                <div 
                  key={index}
                  className="text-center group"
                >
                  <div className="w-24 h-24 mx-auto mb-4 rounded-full bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center text-4xl shadow-lg group-hover:scale-110 transition-transform duration-300">
                    {member.emoji}
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

        {/* CTA Section */}
        <section className="container px-4 md:px-6 py-20">
          <div className="bg-gradient-to-r from-myfav-primary to-myfav-secondary rounded-3xl p-8 md:p-12 text-center text-white">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">
              {t('pages.about.cta.title') || "Rejoignez l'Aventure MyHigh5"}
            </h2>
            <p className="text-lg opacity-90 mb-8 max-w-2xl mx-auto">
              {t('pages.about.cta.subtitle') || "Faites partie d'une communauté mondiale de talents et commencez votre parcours vers le sommet."}
            </p>
            <Button 
              size="lg"
              className="bg-white text-myfav-primary hover:bg-gray-100 font-bold px-8 py-6 text-lg"
            >
              <Users className="w-5 h-5 mr-2" />
              {t('pages.about.cta.button') || "Commencer Maintenant"}
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </div>
        </section>
      </main>
      
      <Footer />
    </div>
  )
}
