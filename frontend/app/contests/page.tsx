"use client"

import * as React from "react"
import { useState, useEffect, useMemo, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Header } from "@/components/layout/header"
import { Footer } from "@/components/sections/footer"
import { ContestCard } from "@/components/dashboard/contest-card"
import { contestService, Contest, ContestResponse } from "@/services/contest-service"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { Search, Trophy, Globe, MapPin, Users, Flame, Building2, Flag, Globe2, Lock, LogIn, UserPlus, ArrowUpDown } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Skeleton, SkeletonButton } from "@/components/ui/skeleton"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
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

function ContestsPageContent() {
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, isAuthenticated } = useAuth()
  const [allContests, setAllContests] = useState<Contest[]>([])
  const [filteredContests, setFilteredContests] = useState<Contest[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState("") // Terme de recherche dans l'input
  const [activeSearchTerm, setActiveSearchTerm] = useState("") // Terme de recherche actif (utilisé pour l'API)
  // FIXED: Start with 'participations' as default since most users want to see regular contests first
  // Users can switch to 'nomination' tab if they want
  const [categoryTab, setCategoryTab] = useState<'nomination' | 'participations'>('participations')
  const [activeTab, setActiveTab] = useState<string>('all')
  const [sortBy, setSortBy] = useState<string>('participants') // participants, votes, date, name
  const [favorites, setFavorites] = useState<string[]>([])
  const [showAuthDialog, setShowAuthDialog] = useState(false)
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [selectedContestId, setSelectedContestId] = useState<string | null>(null)
  const [shouldGoToParticipate, setShouldGoToParticipate] = useState(false)

  // Extraire les types de contests disponibles depuis les données du backend
  const contestTypes = React.useMemo(() => {
    const types = new Set<string>()
    
    // Parcourir tous les contests pour extraire les types uniques
    allContests.forEach(contest => {
      if (contest.contestType) {
        types.add(contest.contestType)
      }
    })
    
    // Créer la liste des types avec "Tout" en premier
    const typeList: Array<{ id: string, label: string, value: string | null }> = [
      { id: 'all', label: t('dashboard.contests.all') || 'Tout', value: null }
    ]
    
    // Ajouter chaque type unique trouvé
    Array.from(types).sort().forEach(type => {
      // Normaliser le type en minuscules pour la traduction
      const normalizedType = type.toLowerCase()
      // Chercher la traduction avec le type normalisé
      const translationKey = `dashboard.contests.contest_type.${normalizedType}`
      let label = t(translationKey)
      
      // Si pas de traduction trouvée (la fonction t retourne la clé si non trouvée)
      // ou si le label contient "dashboard.contests.contest_type" (signe qu'il n'a pas été trouvé)
      if (!label || label === translationKey || label.includes('dashboard.contests.contest_type')) {
        // Utiliser le type original formaté
        label = type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, ' ')
      }
      
      typeList.push({ id: type, label, value: type })
    })
    
    return typeList
  }, [allContests, t])

  // Capturer le code de parrainage depuis l'URL
  useEffect(() => {
    const refCode = searchParams.get('ref') || searchParams.get('referral')
    if (refCode) {
      localStorage.setItem('referral_code', refCode)
    }
  }, [searchParams])

  // Charger les contests
  useEffect(() => {
    loadContests()
  }, [activeSearchTerm, categoryTab])

  // Filtrer et trier les contests
  useEffect(() => {
    if (allContests.length === 0) return
    
    // FIXED: Backend already filters by has_voting_type, so we don't need to filter again here
    // The backend returns only the contests matching the categoryTab (nomination or participations)
    // However, we keep a safety check in case the backend filter didn't work
    let categoryFiltered = allContests.filter(contest => {
      if (categoryTab === 'nomination') {
        return contest.votingType != null
      } else {
        return contest.votingType == null
      }
    })
    
    // FIXED: Don't exclude contests with 0 contestants - they might have contestants but the count might be wrong
    // Instead, only filter if we're sure there are no contestants (contestants === 0 AND we've verified)
    // For now, show all contests - the backend should return accurate counts
    // categoryFiltered = categoryFiltered.filter(contest => contest.contestants > 0)
    
    // Filtrer par type si un onglet est sélectionné (mais pas "all")
    if (activeTab !== 'all') {
      const selectedType = contestTypes.find(t => t.id === activeTab)
      if (selectedType && selectedType.value) {
        categoryFiltered = categoryFiltered.filter(contest => contest.contestType === selectedType.value)
      }
    }
    
    // La recherche est maintenant gérée côté backend, pas besoin de filtrer ici
    
    // Trier les contests selon l'option sélectionnée
    const sortedContests = [...categoryFiltered].sort((a, b) => {
      switch (sortBy) {
        case 'participants':
          if (b.contestants !== a.contestants) {
            return b.contestants - a.contestants
          }
          return b.received - a.received
        case 'votes':
          if (b.received !== a.received) {
            return b.received - a.received
          }
          return b.contestants - a.contestants
        case 'date':
          return new Date(b.startDate).getTime() - new Date(a.startDate).getTime()
        case 'name':
          return a.title.localeCompare(b.title)
        default:
          if (b.contestants !== a.contestants) {
            return b.contestants - a.contestants
          }
          return b.received - a.received
      }
    })
    
    setFilteredContests(sortedContests)
  }, [allContests, categoryTab, activeTab, sortBy, contestTypes])

  const loadContests = async () => {
    try {
      setIsLoading(true)
      console.log(`[ContestsPage] Loading contests for categoryTab: ${categoryTab}`)
      
      // Pour l'onglet Nominations : filtrer les contests qui ont un voting_type (has_voting_type = true)
      // Pour l'onglet Participations : filtrer les contests qui n'ont pas de voting_type (has_voting_type = false)
      const hasVotingType = categoryTab === 'nomination' ? true : categoryTab === 'participations' ? false : undefined
      
      console.log(`[ContestsPage] Calling API with hasVotingType: ${hasVotingType}`)
      
      const response = await contestService.getContests(
        0, 
        500, // FIXED: Increased limit to get all contests (we have 178 total)
        activeSearchTerm || undefined,
        undefined, // votingLevel n'est plus utilisé
        undefined, // votingTypeId
        hasVotingType
      )
      
      console.log(`[ContestsPage] API returned ${response?.length || 0} contests`)
      console.log(`[ContestsPage] Response sample:`, response?.slice(0, 2))
      
      if (!response || !Array.isArray(response)) {
        console.error("[ContestsPage] Invalid response format:", response)
        setAllContests([])
        return
      }
      
      const mappedContests = response
        .map((c: ContestResponse) => {
          try {
            const mapped = contestService.mapResponseToContest(c)
            console.log(`[ContestsPage] Mapped contest ${c?.id}:`, {
              id: mapped.id,
              title: mapped.title,
              contestants: mapped.contestants,
              votingType: mapped.votingType,
              categoryTab: categoryTab
            })
            return mapped
          } catch (error) {
            console.error(`[ContestsPage] Error mapping contest ${c?.id}:`, error)
            console.error(`[ContestsPage] Contest data:`, c)
            return null
          }
        })
        .filter((c: any) => c !== null)
      
      console.log(`[ContestsPage] Successfully mapped ${mappedContests.length} contests`)
      console.log(`[ContestsPage] Sample mapped contest:`, mappedContests[0])
      
      // DEBUG: Check filtering
      console.log(`[ContestsPage] Category tab: ${categoryTab}`)
      console.log(`[ContestsPage] Contests with votingType:`, mappedContests.filter(c => c.votingType != null).length)
      console.log(`[ContestsPage] Contests without votingType:`, mappedContests.filter(c => c.votingType == null).length)
      
      setAllContests(mappedContests)
    } catch (error: any) {
      console.error("[ContestsPage] Error loading contests:", error)
      console.error("[ContestsPage] Error details:", {
        message: error?.message,
        stack: error?.stack,
        response: error?.response?.data
      })
      // FIXED: Set empty array on error so UI shows proper message
      setAllContests([])
    } finally {
      setIsLoading(false)
    }
  }

  // Fonction pour déclencher la recherche
  const handleSearch = () => {
    // Si la recherche est vide, réinitialiser pour afficher toute la liste
    if (searchTerm.trim() === '') {
      setActiveSearchTerm('')
    } else {
      setActiveSearchTerm(searchTerm)
    }
  }

  // Gérer l'appui sur Entrée dans l'input de recherche
  const handleSearchKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  // Détecter quand la barre de recherche est vidée
  useEffect(() => {
    if (searchTerm === '' && activeSearchTerm !== '') {
      // La barre de recherche a été vidée, réinitialiser la recherche active
      setActiveSearchTerm('')
    }
  }, [searchTerm, activeSearchTerm])

  const handleToggleFavorite = (contestId: string) => {
    setFavorites(prev => 
      prev.includes(contestId) 
        ? prev.filter(id => id !== contestId)
        : [...prev, contestId]
    )
  }

  // Show auth dialog if not authenticated, otherwise go to contest details
  const handleContestClick = (contestId: string) => {
    if (isAuthenticated) {
      router.push(`/dashboard/contests/${contestId}`)
    } else {
      setSelectedContestId(contestId)
      setShowAuthDialog(true)
    }
  }

  // Handle participation/nomination click - redirect to apply page
  const handleParticipateClick = (contestId: string) => {
    if (isAuthenticated) {
      router.push(`/dashboard/contests/${contestId}/apply`)
    } else {
      setSelectedContestId(contestId)
      setShouldGoToParticipate(true)
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
      if (shouldGoToParticipate) {
        router.push(`/dashboard/contests/${selectedContestId}/apply`)
        setShouldGoToParticipate(false)
      } else {
      router.push(`/dashboard/contests/${selectedContestId}`)
      }
      setSelectedContestId(null)
    }
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
                <span className="text-sm font-medium">{t('pages.contests.badge') || "Concours en cours"}</span>
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
                  <div className="text-3xl md:text-4xl font-black">{allContests.length}</div>
                  <div className="text-xs md:text-sm opacity-80 mt-1">{t('pages.contests.stats.active') || "Concours actifs"}</div>
                </div>
                <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-6 hover:bg-white/15 transition-all">
                  <Users className="w-8 h-8 mx-auto mb-2 text-myhigh5-cyan-400" />
                  <div className="text-3xl md:text-4xl font-black">
                    {allContests.reduce((acc, c) => acc + c.contestants, 0).toLocaleString()}
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
            {/* Barre d'onglets principaux (Nomination / Participations) */}
            <div className="mb-6 border-b border-gray-200 dark:border-gray-700">
              <div className="flex space-x-1">
                <button
                  onClick={() => {
                    setCategoryTab('nomination')
                    setActiveTab('all')
                  }}
                  className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${
                    categoryTab === 'nomination'
                      ? 'border-blue-500 text-blue-500'
                      : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
                  }`}
                >
                  {t('dashboard.contests.nomination') || 'Nomination'}
                </button>
                <button
                  onClick={() => {
                    setCategoryTab('participations')
                    setActiveTab('all')
                  }}
                  className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${
                    categoryTab === 'participations'
                      ? 'border-blue-500 text-blue-500'
                      : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
                  }`}
                >
                  {t('dashboard.contests.participations') || 'Participations'}
                </button>
              </div>
            </div>
            
            {/* Hint explicatif pour l'onglet actif */}
            <div className="mb-6 px-4 py-3 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-lg">
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {categoryTab === 'nomination' 
                  ? (t('dashboard.contests.nomination_hint') || 'Nominate others to enter into competitions. Vote for contestants who have been nominated by their fans.')
                  : (t('dashboard.contests.participations_hint') || 'Participate yourself in competitions. Contestants sign up directly to compete.')}
              </p>
            </div>

            <div className="flex flex-col lg:flex-row gap-6">
              {/* Search */}
              <div className="flex-1 flex gap-2">
              <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                <Input
                    type="text"
                    placeholder={t('dashboard.contests.search_placeholder') || 'Rechercher un concours...'}
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    onKeyPress={handleSearchKeyPress}
                    className="pl-10 h-14 text-lg rounded-xl border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-myhigh5-primary/20"
                  />
                </div>
                <Button
                  onClick={handleSearch}
                  className="bg-blue-500 hover:bg-blue-600 text-white px-6 h-14 rounded-xl"
                >
                  <Search className="w-4 h-4 mr-2" />
                  {t('dashboard.contests.search_button') || 'Rechercher'}
                </Button>
              </div>
              
              {/* Sélecteur de tri */}
              <div className="w-full lg:w-48">
                <Select value={sortBy} onValueChange={(value) => setSortBy(value)}>
                  <SelectTrigger className="h-14 text-lg rounded-xl border-gray-200 dark:border-gray-600">
                    <ArrowUpDown className="w-4 h-4 mr-2" />
                    <SelectValue placeholder={t('dashboard.contests.sort') || 'Trier par'} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="participants">
                      {t('dashboard.contests.sort_participants') || 'Plus de participants'}
                    </SelectItem>
                    <SelectItem value="votes">
                      {t('dashboard.contests.sort_votes') || 'Plus de votes'}
                    </SelectItem>
                    <SelectItem value="date">
                      {t('dashboard.contests.sort_date') || 'Plus récent'}
                    </SelectItem>
                    <SelectItem value="name">
                      {t('dashboard.contests.sort_name') || 'Nom (A-Z)'}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              </div>
              
            {/* Barre d'onglets de navigation par type */}
            {contestTypes.length > 1 && (
              <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <div className="flex space-x-1 overflow-x-auto scrollbar-hide">
                  {contestTypes.map((type) => (
                    <button
                      key={type.id}
                      onClick={() => setActiveTab(type.id)}
                      className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                        activeTab === type.id
                          ? 'border-blue-500 text-blue-500'
                          : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
                      }`}
                    >
                      {type.label}
                    </button>
                ))}
              </div>
            </div>
            )}
          </div>
        </section>

        {/* Contests Grid */}
        <section className="container px-4 md:px-6 py-12">
          {/* Section Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white">
                {activeTab === "all" 
                  ? t('pages.contests.all_contests') || "Tous les concours"
                  : `${t('pages.contests.contests_filter') || "Concours"} ${contestTypes.find(t => t.id === activeTab)?.label}`
                }
              </h2>
              <p className="text-gray-500 dark:text-gray-400 mt-1">
                {filteredContests.length} {t('pages.contests.results') || "résultat"}{filteredContests.length > 1 ? "s" : ""}
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
              <p className="text-gray-500 dark:text-gray-400 mb-2">
                {t('pages.contests.try_different_filter') || "Essayez un autre filtre ou terme de recherche"}
              </p>
              {/* DEBUG INFO */}
              <div className="mt-4 p-4 bg-gray-100 dark:bg-gray-900 rounded text-left text-xs text-gray-600 dark:text-gray-400 max-w-md mx-auto">
                <p><strong>Debug Info:</strong></p>
                <p>All Contests: {allContests.length}</p>
                <p>Filtered Contests: {filteredContests.length}</p>
                <p>Category Tab: {categoryTab}</p>
                <p>Active Tab: {activeTab}</p>
                <p>Is Loading: {isLoading ? 'Yes' : 'No'}</p>
                <p>Search Term: {activeSearchTerm || 'None'}</p>
              </div>
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
                  setActiveTab("all")
                  setSearchTerm("")
                  setActiveSearchTerm("")
                }}
              >
                {t('pages.contests.reset_filters') || "Réinitialiser les filtres"}
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">
              {filteredContests.map((contest, index) => (
                <ContestCard
                  key={contest.id}
                  id={contest.id}
                  title={contest.title}
                  description={contest.description}
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
                  userGender={(user as any)?.gender as 'male' | 'female' | 'other' | 'prefer_not_to_say' | null | undefined}
                  canParticipate={true}
                  isKycVerified={user?.identity_verified || false}
                  topContestants={contest.topContestants}
                  requiresKyc={contest.requiresKyc}
                  verificationType={contest.verificationType}
                  participantType={contest.participantType}
                  requiresVisualVerification={contest.requiresVisualVerification}
                  requiresVoiceVerification={contest.requiresVoiceVerification}
                  requiresBrandVerification={contest.requiresBrandVerification}
                  requiresContentVerification={contest.requiresContentVerification}
                  minAge={contest.minAge}
                  maxAge={contest.maxAge}
                  isNomination={categoryTab === 'nomination'}
                  votingType={contest.votingType}
                  isFavorite={favorites.includes(contest.id)}
                  onToggleFavorite={() => handleToggleFavorite(contest.id)}
                  onViewContestants={() => handleContestClick(contest.id)}
                  onParticipate={() => handleParticipateClick(contest.id)}
                  onOpenDetails={() => handleContestClick(contest.id)}
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
                <span className="text-sm font-medium">{t('pages.contests.join_community') || "Rejoignez la communauté"}</span>
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
                  {t('pages.contests.learn_more') || "En savoir plus"}
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

export default function ContestsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-white dark:bg-gray-900" />}>
      <ContestsPageContent />
    </Suspense>
  )
}
