"use client"

import * as React from "react"
import { Header } from "@/components/layout/header"
import { Footer } from "@/components/sections/footer"
import { useLanguage } from "@/contexts/language-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { 
  Users, 
  Crown, 
  Star, 
  Heart, 
  Search, 
  Lock, 
  Unlock,
  TrendingUp,
  Sparkles,
  Wallet,
  Shield,
  ArrowRight
} from "lucide-react"

// Données de démonstration pour les clubs
const demoClubs = [
  {
    id: "1",
    name: "Elite Beauty Club",
    description: "Club exclusif pour les passionnés de beauté et mode",
    memberCount: 1250,
    category: "beauty",
    isPrivate: true,
    monthlyPrice: 9.99,
    coverImage: "👑",
    owner: "Sarah M.",
    rating: 4.9
  },
  {
    id: "2", 
    name: "Sports Champions",
    description: "Communauté des champions sportifs du monde entier",
    memberCount: 3400,
    category: "sports",
    isPrivate: false,
    monthlyPrice: 0,
    coverImage: "🏆",
    owner: "Carlos R.",
    rating: 4.8
  },
  {
    id: "3",
    name: "Music Creators Hub",
    description: "Espace créatif pour les artistes musicaux émergents",
    memberCount: 2100,
    category: "music",
    isPrivate: true,
    monthlyPrice: 14.99,
    coverImage: "🎵",
    owner: "Emma L.",
    rating: 4.7
  },
  {
    id: "4",
    name: "Pet Lovers Paradise",
    description: "Le paradis des amoureux des animaux de compagnie",
    memberCount: 5600,
    category: "pets",
    isPrivate: false,
    monthlyPrice: 0,
    coverImage: "🐾",
    owner: "John D.",
    rating: 4.9
  },
  {
    id: "5",
    name: "Fashion Forward",
    description: "Tendances mode et style avant-gardiste",
    memberCount: 890,
    category: "fashion",
    isPrivate: true,
    monthlyPrice: 19.99,
    coverImage: "✨",
    owner: "Marie K.",
    rating: 4.6
  },
  {
    id: "6",
    name: "Talent Showcase",
    description: "Découvrez et partagez vos talents uniques",
    memberCount: 4200,
    category: "talent",
    isPrivate: false,
    monthlyPrice: 0,
    coverImage: "🌟",
    owner: "Alex T.",
    rating: 4.8
  }
]

export default function ClubsPage() {
  const { t, language } = useLanguage()

  const categoryLabels: Record<string, Record<string, string>> = {
    en: { all: "All", beauty: "Beauty", sports: "Sports", music: "Music", pets: "Pets", fashion: "Fashion", members: "members", free: "Free", join: "Join", access: "Access", by: "By", month: "/month" },
    fr: { all: "Tous", beauty: "Beauté", sports: "Sports", music: "Musique", pets: "Animaux", fashion: "Mode", members: "membres", free: "Gratuit", join: "Rejoindre", access: "Accéder", by: "Par", month: "/mois" },
    es: { all: "Todos", beauty: "Belleza", sports: "Deportes", music: "Música", pets: "Mascotas", fashion: "Moda", members: "miembros", free: "Gratis", join: "Unirse", access: "Acceder", by: "Por", month: "/mes" },
    de: { all: "Alle", beauty: "Schönheit", sports: "Sport", music: "Musik", pets: "Haustiere", fashion: "Mode", members: "Mitglieder", free: "Kostenlos", join: "Beitreten", access: "Zugriff", by: "Von", month: "/Monat" }
  }
  const cl = categoryLabels[language] || categoryLabels.en

  const categories = [
    { id: "all", label: cl.all, icon: Users },
    { id: "beauty", label: cl.beauty, icon: Crown },
    { id: "sports", label: cl.sports, icon: TrendingUp },
    { id: "music", label: cl.music, icon: Sparkles },
    { id: "pets", label: cl.pets, icon: Heart },
    { id: "fashion", label: cl.fashion, icon: Star },
  ]
  const [searchQuery, setSearchQuery] = React.useState("")
  const [selectedCategory, setSelectedCategory] = React.useState("all")
  const [showPremiumOnly, setShowPremiumOnly] = React.useState(false)

  const filteredClubs = demoClubs.filter(club => {
    const matchesSearch = club.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         club.description.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = selectedCategory === "all" || club.category === selectedCategory
    const matchesPremium = !showPremiumOnly || club.isPrivate
    return matchesSearch && matchesCategory && matchesPremium
  })

  return (
    <div className="min-h-screen bg-gradient-to-br from-myfav-blue-50 via-white to-myfav-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <Header />
      
      <main className="pt-24 pb-16">
        {/* Hero Section */}
        <section className="relative py-16 bg-gradient-to-r from-myfav-primary to-myfav-secondary overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_50%,rgba(255,255,255,0.1),transparent_50%)]" />
          <div className="container px-4 md:px-6 relative z-10">
            <div className="max-w-3xl mx-auto text-center text-white">
              <Crown className="w-16 h-16 mx-auto mb-6 animate-pulse" />
              <h1 className="text-4xl md:text-5xl font-black mb-4">
                {t('pages.clubs.title') || "Fan Clubs Exclusifs"}
              </h1>
              <p className="text-xl opacity-90 mb-8">
                {t('pages.clubs.subtitle') || "Rejoignez des communautés passionnées et accédez à du contenu exclusif"}
              </p>
              
              {/* Features */}
              <div className="flex flex-wrap justify-center gap-6 mt-8">
                <div className="flex items-center gap-2 bg-white/10 backdrop-blur-sm rounded-full px-4 py-2">
                  <Wallet className="w-5 h-5" />
                  <span className="text-sm">{t('pages.clubs.features.dsp') || "Paiement DSP"}</span>
                </div>
                <div className="flex items-center gap-2 bg-white/10 backdrop-blur-sm rounded-full px-4 py-2">
                  <Shield className="w-5 h-5" />
                  <span className="text-sm">{t('pages.clubs.features.multi_admin') || "Multi-Admin"}</span>
                </div>
                <div className="flex items-center gap-2 bg-white/10 backdrop-blur-sm rounded-full px-4 py-2">
                  <TrendingUp className="w-5 h-5" />
                  <span className="text-sm">{t('pages.clubs.features.affiliate') || "Programme Affilié"}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Search & Filters */}
        <section className="container px-4 md:px-6 -mt-8 relative z-20">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex flex-col lg:flex-row gap-4">
              {/* Search */}
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  placeholder={t('pages.clubs.search_placeholder') || "Rechercher un club..."}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 h-12"
                />
              </div>
              
              {/* Category filters */}
              <div className="flex flex-wrap gap-2">
                {categories.map((cat) => (
                  <Button
                    key={cat.id}
                    variant={selectedCategory === cat.id ? "default" : "outline"}
                    onClick={() => setSelectedCategory(cat.id)}
                    className={`${
                      selectedCategory === cat.id 
                        ? "bg-myfav-primary hover:bg-myfav-blue-700 text-white" 
                        : ""
                    }`}
                  >
                    <cat.icon className="w-4 h-4 mr-2" />
                    {cat.label}
                  </Button>
                ))}
              </div>

              {/* Premium toggle */}
              <Button
                variant={showPremiumOnly ? "default" : "outline"}
                onClick={() => setShowPremiumOnly(!showPremiumOnly)}
                className={showPremiumOnly ? "bg-amber-500 hover:bg-amber-600" : ""}
              >
                <Crown className="w-4 h-4 mr-2" />
                Premium
              </Button>
            </div>
          </div>
        </section>

        {/* Clubs Grid */}
        <section className="container px-4 md:px-6 py-12">
          {filteredClubs.length === 0 ? (
            <div className="text-center py-16">
              <Users className="w-16 h-16 mx-auto text-gray-300 mb-4" />
              <h3 className="text-xl font-semibold text-gray-600 dark:text-gray-400 mb-2">
                {t('pages.clubs.no_results') || "Aucun club trouvé"}
              </h3>
              <p className="text-gray-500">
                {t('pages.clubs.try_different_filter') || "Essayez un autre filtre"}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredClubs.map((club) => (
                <div 
                  key={club.id}
                  className="group bg-white dark:bg-gray-800 rounded-2xl overflow-hidden border border-gray-200 dark:border-gray-700 shadow-lg hover:shadow-2xl transition-all duration-300 hover:-translate-y-1"
                >
                  {/* Cover */}
                  <div className="relative h-32 bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center">
                    <span className="text-6xl">{club.coverImage}</span>
                    {club.isPrivate && (
                      <Badge className="absolute top-3 right-3 bg-amber-500 text-white border-0">
                        <Lock className="w-3 h-3 mr-1" />
                        Premium
                      </Badge>
                    )}
                  </div>
                  
                  {/* Content */}
                  <div className="p-5">
                    <div className="flex items-start justify-between mb-3">
                      <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                        {club.name}
                      </h3>
                      <div className="flex items-center gap-1 text-amber-500">
                        <Star className="w-4 h-4 fill-current" />
                        <span className="text-sm font-semibold">{club.rating}</span>
                      </div>
                    </div>
                    
                    <p className="text-gray-600 dark:text-gray-400 text-sm mb-4 line-clamp-2">
                      {club.description}
                    </p>
                    
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-2 text-sm text-gray-500">
                        <Users className="w-4 h-4" />
                        <span>{club.memberCount.toLocaleString()} {cl.members}</span>
                      </div>
                      <div className="text-sm text-gray-500">
                        {cl.by} <span className="font-semibold text-myfav-primary">{club.owner}</span>
                      </div>
                    </div>
                    
                    <div className="flex items-center justify-between pt-4 border-t border-gray-100 dark:border-gray-700">
                      {club.isPrivate ? (
                        <div className="text-lg font-bold text-myfav-primary">
                          {club.monthlyPrice}$ <span className="text-sm font-normal text-gray-500">{cl.month}</span>
                        </div>
                      ) : (
                        <Badge className="text-green-600 border border-green-600 bg-green-50 dark:bg-green-900/20">
                          <Unlock className="w-3 h-3 mr-1" />
                          {cl.free}
                        </Badge>
                      )}
                      <Button className="bg-myfav-primary hover:bg-myfav-primary-dark">
                        {club.isPrivate ? cl.join : cl.access}
                        <ArrowRight className="w-4 h-4 ml-2" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Create Club CTA */}
        <section className="container px-4 md:px-6 py-12">
          <div className="bg-gradient-to-r from-myfav-primary to-myfav-secondary rounded-3xl p-8 md:p-12">
            <div className="grid md:grid-cols-2 gap-8 items-center">
              <div className="text-white">
                <h2 className="text-3xl md:text-4xl font-bold mb-4">
                  {t('pages.clubs.cta.title') || "Créez votre propre Club"}
                </h2>
                <p className="text-lg opacity-90 mb-6">
                  {t('pages.clubs.cta.subtitle') || "Monétisez votre contenu, gérez votre communauté et gagnez grâce au programme d'affiliation."}
                </p>
                <ul className="space-y-3 mb-8">
                  <li className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-white/20 flex items-center justify-center">
                      <Wallet className="w-3 h-3" />
                    </div>
                    <span>{t('pages.clubs.cta.feature1') || "Paiements sécurisés via DSP"}</span>
                  </li>
                  <li className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-white/20 flex items-center justify-center">
                      <Shield className="w-3 h-3" />
                    </div>
                    <span>{t('pages.clubs.cta.feature2') || "Gestion multi-administrateurs"}</span>
                  </li>
                  <li className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-white/20 flex items-center justify-center">
                      <TrendingUp className="w-3 h-3" />
                    </div>
                    <span>{t('pages.clubs.cta.feature3') || "20% de commission sur les ventes"}</span>
                  </li>
                </ul>
                <Button 
                  size="lg"
                  className="bg-white text-myfav-primary hover:bg-gray-100 font-bold px-8 py-6 text-lg"
                >
                  <Crown className="w-5 h-5 mr-2" />
                  {t('pages.clubs.cta.button') || "Créer mon Club"}
                </Button>
              </div>
              <div className="hidden md:flex justify-center">
                <div className="w-64 h-64 rounded-full bg-white/10 backdrop-blur-sm flex items-center justify-center">
                  <Crown className="w-32 h-32 text-white/80" />
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
      
      <Footer />
    </div>
  )
}
