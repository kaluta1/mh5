"use client"

import * as React from "react"
import { useState, useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Header } from "@/components/layout/header"
import { Footer } from "@/components/sections/footer"
import { ContestCard } from "@/components/dashboard/contest-card"
import { contestService, Contest, ContestResponse } from "@/services/contest-service"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { Search, Trophy, Globe, MapPin, Users, Flame, Building2, Flag, Globe2, Lock, LogIn, UserPlus } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Skeleton, SkeletonButton } from "@/components/ui/skeleton"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoginModal } from "@/components/auth/login-modal"

// Contest Card Skeleton
function ContestCardSkeleton() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-3xl overflow-hidden border border-gray-100 dark:border-gray-700 shadow-sm">
      <Skeleton className="aspect-[4/3] w-full rounded-none" />
      <div className="p-4 space-y-3">
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <div className="flex justify-between items-center pt-2">
          <Skeleton className="h-6 w-20 rounded-full" />
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>
      </div>
    </div>
  )
}

export default function ContestsPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, isAuthenticated } = useAuth()
  const [contests, setContests] = useState<Contest[]>([])
  const [filteredContests, setFilteredContests] = useState<Contest[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedFilter, setSelectedFilter] = useState<string>("all")
  const [favorites, setFavorites] = useState<string[]>([])
  const [showAuthDialog, setShowAuthDialog] = useState(false)
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [selectedContestId, setSelectedContestId] = useState<string | null>(null)

  // Capturer le code de parrainage depuis l'URL
  useEffect(() => {
    const refCode = searchParams.get('ref') || searchParams.get('referral')
    if (refCode) {
      localStorage.setItem('referral_code', refCode)
    }
  }, [searchParams])

  useEffect(() => {
    loadContests()
  }, [])

  useEffect(() => {
    filterContests()
  }, [searchQuery, selectedFilter, contests])

  const loadContests = async () => {
    try {
      setIsLoading(true)
      const response = await contestService.getContests(0, 100)
      const mappedContests = response.map((c: ContestResponse) => 
        contestService.mapResponseToContest(c)
      )
      setContests(mappedContests)
      setFilteredContests(mappedContests)
    } catch (error) {
      console.error("Error loading contests:", error)
    } finally {
      setIsLoading(false)
    }
  }

  const filterContests = () => {
    let filtered = [...contests]
    
    if (searchQuery) {
      filtered = filtered.filter(c => 
        c.title.toLowerCase().includes(searchQuery.toLowerCase())
      )
    }
    
    if (selectedFilter !== "all") {
      filtered = filtered.filter(c => c.status === selectedFilter)
    }
    
    setFilteredContests(filtered)
  }

  const handleToggleFavorite = (contestId: string) => {
    setFavorites(prev => 
      prev.includes(contestId) 
        ? prev.filter(id => id !== contestId)
        : [...prev, contestId]
    )
  }

  // Show auth dialog if not authenticated, otherwise go to contest
  const handleContestClick = (contestId: string) => {
    if (isAuthenticated) {
      router.push(`/dashboard/contests/${contestId}`)
    } else {
      setSelectedContestId(contestId)
      setShowAuthDialog(true)
    }
  }

  const handleLoginClick = () => {
    setShowAuthDialog(false)
    setShowLoginModal(true)
  }

  const handleRegisterClick = () => {
    setShowAuthDialog(false)
    const refCode = localStorage.getItem('referral_code')
    router.push(refCode ? `/register?ref=${refCode}` : '/register')
  }

  const handleLoginSuccess = () => {
    setShowLoginModal(false)
    if (selectedContestId) {
      router.push(`/dashboard/contests/${selectedContestId}`)
    }
  }

  const filters = [
    { id: "all", label: t('pages.contests.filters.all') || "Tous", icon: Trophy, color: "bg-myhigh5-blue-600" },
    { id: "city", label: t('pages.contests.filters.city') || "Ville", icon: Building2, color: "bg-myhigh5-cyan-500" },
    { id: "country", label: t('pages.contests.filters.country') || "Pays", icon: Flag, color: "bg-myhigh5-blue-500" },
    { id: "regional", label: t('pages.contests.filters.regional') || "Régional", icon: MapPin, color: "bg-myhigh5-cyan-600" },
    { id: "continental", label: t('pages.contests.filters.continental') || "Continental", icon: Globe, color: "bg-myhigh5-primary" },
    { id: "global", label: t('pages.contests.filters.global') || "Global", icon: Globe2, color: "bg-myhigh5-blue-800" },
  ]

  const getFilterCount = (filterId: string) => {
    if (filterId === "all") return contests.length
    return contests.filter(c => c.status === filterId).length
  }

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900">
      <Header />
      
      <main className="pt-24 pb-16">
        {/* Hero Section */}
        <section className="relative py-20 overflow-hidden">  
          {/* Background gradient */}
          <div className="absolute inset-0 bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.15),transparent_50%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_80%,rgba(8,145,178,0.3),transparent_50%)]" />
          
          {/* Decorative elements */}
          <div className="absolute top-10 left-10 w-20 h-20 bg-white/10 rounded-full blur-xl animate-pulse" />
          <div className="absolute bottom-10 right-10 w-32 h-32 bg-myhigh5-cyan-400/20 rounded-full blur-2xl animate-pulse delay-700" />
          
          <div className="container px-4 md:px-6 relative z-10">
            <div className="max-w-4xl mx-auto text-center text-white">
              {/* Badge */}
              <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-sm border border-white/20 rounded-full px-4 py-2 mb-6">
                <Flame className="w-4 h-4 text-orange-400" />
                <span className="text-sm font-medium">Concours en cours</span>
              </div>
              
              <h1 className="text-4xl md:text-6xl font-black mb-6 leading-tight">
                {t('pages.contests.title') || "Découvrez nos Concours"}
              </h1>
              <p className="text-xl md:text-2xl opacity-90 mb-10 max-w-2xl mx-auto leading-relaxed">
                {t('pages.contests.subtitle') || "Participez à des compétitions passionnantes du niveau local au niveau mondial"}
              </p>
              
              {/* Stats Cards */}
              <div className="grid grid-cols-3 gap-4 md:gap-6 max-w-2xl mx-auto">
                <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-6 hover:bg-white/15 transition-all">
                  <Trophy className="w-8 h-8 mx-auto mb-2 text-amber-400" />
                  <div className="text-3xl md:text-4xl font-black">{contests.length}</div>
                  <div className="text-xs md:text-sm opacity-80 mt-1">{t('pages.contests.stats.active') || "Concours actifs"}</div>
                </div>
                <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-6 hover:bg-white/15 transition-all">
                  <Users className="w-8 h-8 mx-auto mb-2 text-myhigh5-cyan-400" />
                  <div className="text-3xl md:text-4xl font-black">
                    {contests.reduce((acc, c) => acc + c.contestants, 0).toLocaleString()}
                  </div>
                  <div className="text-xs md:text-sm opacity-80 mt-1">{t('pages.contests.stats.participants') || "Participants"}</div>
                </div>
                <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-6 hover:bg-white/15 transition-all">
                  <Globe className="w-8 h-8 mx-auto mb-2 text-myhigh5-cyan-300" />
                  <div className="text-3xl md:text-4xl font-black">5</div>
                  <div className="text-xs md:text-sm opacity-80 mt-1">{t('pages.contests.stats.levels') || "Niveaux"}</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Search & Filters */}
        <section className="container px-4 md:px-6 -mt-8 relative z-20">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl p-6 border border-gray-100 dark:border-gray-700">
            <div className="flex flex-col lg:flex-row gap-6">
              {/* Search */}
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  placeholder={t('pages.contests.search_placeholder') || "Rechercher un concours..."}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-12 h-14 text-lg rounded-xl border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-myhigh5-primary/20"
                />
              </div>
              
              {/* Filter buttons */}
              <div className="flex flex-wrap gap-2">
                {filters.map((filter) => (
                  <Button
                    key={filter.id}
                    variant={selectedFilter === filter.id ? "default" : "outline"}
                    onClick={() => setSelectedFilter(filter.id)}
                    className={`h-14 px-4 rounded-xl transition-all duration-200 ${
                      selectedFilter === filter.id 
                        ? `${filter.color} hover:opacity-90 text-white border-0 shadow-lg` 
                        : "hover:bg-gray-50 dark:hover:bg-gray-700"
                    }`}
                  >
                    <filter.icon className="w-4 h-4 mr-2" />
                    <span className="font-medium">{filter.label}</span>
                    <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
                      selectedFilter === filter.id 
                        ? "bg-white/20" 
                        : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
                    }`}>
                      {getFilterCount(filter.id)}
                    </span>
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Contests Grid */}
        <section className="container px-4 md:px-6 py-12">
          {/* Section Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white">
                {selectedFilter === "all" 
                  ? "Tous les concours" 
                  : `Concours ${filters.find(f => f.id === selectedFilter)?.label}`
                }
              </h2>
              <p className="text-gray-500 dark:text-gray-400 mt-1">
                {filteredContests.length} résultat{filteredContests.length > 1 ? "s" : ""}
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">
              {[...Array(6)].map((_, i) => (
                <ContestCardSkeleton key={i} />
              ))}
            </div>
          ) : filteredContests.length === 0 ? (
            <div className="text-center py-20 bg-gray-50 dark:bg-gray-800/50 rounded-3xl border border-gray-100 dark:border-gray-700">
              <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
                <Trophy className="w-10 h-10 text-gray-400" />
              </div>
              <h3 className="text-xl font-bold text-gray-700 dark:text-gray-300 mb-2">
                {t('pages.contests.no_results') || "Aucun concours trouvé"}
              </h3>
              <p className="text-gray-500 dark:text-gray-400 mb-6 max-w-md mx-auto">
                {t('pages.contests.try_different_filter') || "Essayez un autre filtre ou terme de recherche"}
              </p>
              <Button 
                variant="outline" 
                onClick={() => {
                  setSelectedFilter("all")
                  setSearchQuery("")
                }}
              >
                Réinitialiser les filtres
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">
              {filteredContests.map((contest, index) => (
                <ContestCard
                  key={contest.id}
                  id={contest.id}
                  title={contest.title}
                  coverImage={contest.coverImage}
                  startDate={contest.startDate}
                  status={contest.status}
                  received={contest.received}
                  contestants={contest.contestants}
                  likes={contest.likes}
                  comments={contest.comments}
                  isOpen={contest.isOpen}
                  isFeatured={index === 0}
                  genderRestriction={contest.genderRestriction}
                  participationStartDate={contest.participationStartDate}
                  participationEndDate={contest.participationEndDate}
                  votingStartDate={contest.votingStartDate}
                  isFavorite={favorites.includes(contest.id)}
                  onToggleFavorite={() => handleToggleFavorite(contest.id)}
                  onViewContestants={() => handleContestClick(contest.id)}
                  onParticipate={() => handleContestClick(contest.id)}
                />
              ))}
            </div>
          )}
        </section>

        {/* CTA Section */}
        <section className="container px-4 md:px-6 py-12">
          <div className="relative overflow-hidden bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary rounded-3xl p-8 md:p-16">
            {/* Decorative background */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_50%,rgba(255,255,255,0.1),transparent_40%)]" />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_20%,rgba(8,145,178,0.3),transparent_40%)]" />
            <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full blur-3xl" />
            <div className="absolute bottom-0 left-0 w-48 h-48 bg-myhigh5-cyan-400/10 rounded-full blur-2xl" />
            
            <div className="relative z-10 text-center text-white">
              <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-sm rounded-full px-4 py-2 mb-6">
                <Users className="w-4 h-4" />
                <span className="text-sm font-medium">Rejoignez la communauté</span>
              </div>
              
              <h2 className="text-3xl md:text-5xl font-black mb-6 leading-tight">
                {t('pages.contests.cta.title') || "Prêt à participer ?"}
              </h2>
              <p className="text-lg md:text-xl opacity-90 mb-10 max-w-2xl mx-auto leading-relaxed">
                {t('pages.contests.cta.subtitle') || "Créez votre compte gratuitement et commencez à participer aux concours dès aujourd'hui !"}
              </p>
              
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Button 
                  size="lg"
                  onClick={() => router.push('/register')}
                  className="bg-white text-myhigh5-primary hover:bg-gray-100 font-bold px-10 py-7 text-lg rounded-xl shadow-2xl hover:shadow-white/20 transition-all hover:-translate-y-1"
                >
                  <Users className="w-5 h-5 mr-2" />
                  {t('pages.contests.cta.button') || "Créer mon compte"}
                </Button>
                <Button 
                  size="lg"
                  variant="outline"
                  onClick={() => router.push('/about')}
                  className="border-2 border-white/30 text-white hover:bg-white/10 font-bold px-10 py-7 text-lg rounded-xl"
                >
                  En savoir plus
                </Button>
              </div>
            </div>
          </div>
        </section>
      </main>
      
      <Footer />

      {/* Auth Required Dialog */}
      <Dialog open={showAuthDialog} onOpenChange={setShowAuthDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-myhigh5-primary/10 flex items-center justify-center">
              <Lock className="w-8 h-8 text-myhigh5-primary" />
            </div>
            <DialogTitle className="text-2xl font-bold text-center">
              {t('pages.contests.auth_required_title') || "Connexion requise"}
            </DialogTitle>
            <DialogDescription className="text-center text-base mt-2">
              {t('pages.contests.auth_required_description') || "Vous devez être connecté pour participer aux concours ou voir les participants."}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 mt-6">
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <Users className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-blue-900 dark:text-blue-100">
                  <p className="font-semibold mb-1">
                    {t('pages.contests.auth_required_benefits_title') || "En vous connectant, vous pourrez :"}
                  </p>
                  <ul className="list-disc list-inside space-y-1 text-blue-800 dark:text-blue-200">
                    <li>{t('pages.contests.auth_required_benefit_participate') || "Participer aux concours"}</li>
                    <li>{t('pages.contests.auth_required_benefit_view_contestants') || "Voir les participants"}</li>
                    <li>{t('pages.contests.auth_required_benefit_vote') || "Voter pour vos favoris"}</li>
                    <li>{t('pages.contests.auth_required_benefit_comment') || "Commenter et interagir"}</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <Button
                onClick={handleLoginClick}
                className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white font-semibold h-12"
              >
                <LogIn className="w-5 h-5 mr-2" />
                {t('pages.contests.auth_required_login') || "Se connecter"}
              </Button>
              
              <Button
                onClick={handleRegisterClick}
                variant="outline"
                className="w-full border-2 border-myhigh5-primary text-myhigh5-primary hover:bg-myhigh5-primary/10 font-semibold h-12"
              >
                <UserPlus className="w-5 h-5 mr-2" />
                {t('pages.contests.auth_required_register') || "Créer un compte"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Login Modal */}
      <LoginModal
        open={showLoginModal}
        onOpenChange={setShowLoginModal}
        onLoginSuccess={handleLoginSuccess}
        onRegisterClick={handleRegisterClick}
      />
    </div>
  )
}
