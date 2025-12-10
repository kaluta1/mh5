'use client'

import * as React from "react"
import { useState, useEffect, useMemo } from "react"
import Link from 'next/link'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import { useToast } from '@/components/ui/toast'
import { ContestsSkeleton } from '@/components/ui/skeleton'
import { ContestsHeader } from '@/components/dashboard/contests-header'
import { ContestsGrid } from '@/components/dashboard/contests-grid'
import { ContestsLoader } from '@/components/dashboard/contests-loader'
import { contestService, Contest } from '@/services/contest-service'
import { AlertCircle, UserCircle, Fingerprint, ChevronRight, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function ContestsPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const { addToast } = useToast()
  const [allContests, setAllContests] = useState<Contest[]>([])
  const [displayedContests, setDisplayedContests] = useState<Contest[]>([])
  const [favorites, setFavorites] = useState<string[]>([])
  const [searchTerm, setSearchTerm] = useState('')
  const [pageLoading, setPageLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [showMobileAlert, setShowMobileAlert] = useState(true)
  const ITEMS_PER_PAGE = 9
  const observerTarget = React.useRef(null)
  const isLoadingDataRef = React.useRef(false)
  const isMountedRef = React.useRef(true)

  // Redirection si non authentifié
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  // Gérer le montage/démontage du composant
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Charger les contests et les favoris
  useEffect(() => {
    console.log('[ContestsPage] useEffect triggered', { isLoading, isAuthenticated, allContestsLength: allContests.length, isLoadingData: isLoadingDataRef.current, pageLoading })
    
    // Ne charger que si l'authentification est confirmée
    if (isLoading) {
      console.log('[ContestsPage] Still loading auth, waiting...')
      // Ne pas mettre pageLoading à false ici, on attend que l'auth soit chargée
      return
    }
    
    if (!isAuthenticated) {
      console.log('[ContestsPage] Not authenticated, stopping loading')
      setPageLoading(false)
      return
    }
    
    // Si on a déjà des données, arrêter le loading
    if (allContests.length > 0) {
      console.log('[ContestsPage] Already have contests, stopping loading')
      setPageLoading(false)
      return
    }
    
    // Éviter les appels multiples simultanés
    if (isLoadingDataRef.current) {
      console.log('[ContestsPage] Already loading data, skipping...')
      return
    }
    
    console.log('[ContestsPage] Starting to load contests...')
    
    const loadData = async () => {
      isLoadingDataRef.current = true
      
      try {
        setPageLoading(true)
        console.log('[ContestsPage] Calling getContests API...')
        
        // Récupérer les contests du backend (jusqu'à 100)
        const apiContests = await contestService.getContests(0, 100)
        console.log('[ContestsPage] API response received:', apiContests?.length || 0, 'contests')
        // Debug: Log first contest's top_contestants
        if (apiContests?.length > 0) {
          console.log('[ContestsPage] First contest raw data:', {
            id: apiContests[0].id,
            name: apiContests[0].name,
            top_contestants: apiContests[0].top_contestants
          })
        }
        
        if (!isMountedRef.current) {
          console.log('[ContestsPage] Component unmounted, aborting')
          return
        }
        
        if (!apiContests || apiContests.length === 0) {
          console.warn('[ContestsPage] Aucun contest reçu du backend')
          if (isMountedRef.current) {
            setAllContests([])
            setDisplayedContests([])
            setHasMore(false)
            setCurrentPage(1)
          }
        } else {
          // Convertir les réponses API en objets Contest
          const contests: Contest[] = apiContests.map(apiContest => 
            contestService.mapResponseToContest(apiContest)
          )
          console.log('[ContestsPage] Converted to Contest objects:', contests.length)
          
          // Trier les contests par nombre de participants (le plus suivi en premier)
          const sortedContests = [...contests].sort((a, b) => {
            // Priorité: nombre de participants, puis votes reçus
            if (b.contestants !== a.contestants) {
              return b.contestants - a.contestants
            }
            return b.received - a.received
          })
          
          console.log('[ContestsPage] Setting state with', sortedContests.length, 'contests')
          if (isMountedRef.current) {
            setAllContests(sortedContests)
            setDisplayedContests(sortedContests.slice(0, ITEMS_PER_PAGE))
            setHasMore(sortedContests.length > ITEMS_PER_PAGE)
            setCurrentPage(1) // Réinitialiser la page
            
            console.log(`[ContestsPage] Chargé ${contests.length} contests du backend`)
            console.log(`[ContestsPage] displayedContests: ${sortedContests.slice(0, ITEMS_PER_PAGE).length} contests`)
            console.log(`[ContestsPage] First contest:`, sortedContests[0])
          }
        }
        
        // Charger les favoris depuis l'API
        if (isMountedRef.current) {
          try {
            console.log('[ContestsPage] Loading favorites...')
            const favoritesContests = await contestService.getFavoritesContests(0, 100)
            const favoriteIds = favoritesContests.map(c => c.id)
            setFavorites(favoriteIds)
            console.log('[ContestsPage] Favorites loaded:', favoriteIds.length)
          } catch (error) {
            console.error('[ContestsPage] Erreur lors du chargement des favoris:', error)
            if (isMountedRef.current) {
              setFavorites([])
            }
          }
        }
      } catch (error) {
        console.error('[ContestsPage] Erreur lors du chargement des contests:', error)
        if (isMountedRef.current) {
          setAllContests([])
          setDisplayedContests([])
          setHasMore(false)
          setCurrentPage(1)
        }
      } finally {
        console.log('[ContestsPage] Finally block executed, isMounted:', isMountedRef.current)
        // Toujours mettre pageLoading à false, même si le composant est démonté
        // pour éviter qu'il reste bloqué
        if (isMountedRef.current) {
          setPageLoading(false)
        }
        isLoadingDataRef.current = false
        console.log('[ContestsPage] Loading completed, pageLoading set to false')
      }
    }

    loadData()
  }, [isLoading, isAuthenticated])

  // Infinite scroll avec Intersection Observer
  useEffect(() => {
    if (searchTerm !== '') return // Ne pas observer si on est en mode recherche
    
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore && searchTerm === '') {
          loadMore()
        }
      },
      { threshold: 0.1 }
    )

    const currentTarget = observerTarget.current
    if (currentTarget) {
      observer.observe(currentTarget)
    }

    return () => {
      if (currentTarget) {
        observer.unobserve(currentTarget)
      }
    }
  }, [hasMore, isLoadingMore, searchTerm, allContests.length])

  const loadMore = React.useCallback(() => {
    if (isLoadingMore || !hasMore || searchTerm !== '') return
    
    setIsLoadingMore(true)
    try {
      const nextPage = currentPage + 1
      const startIndex = currentPage * ITEMS_PER_PAGE
      const endIndex = startIndex + ITEMS_PER_PAGE
      const newContests = allContests.slice(startIndex, endIndex)
      
      if (newContests.length > 0) {
        setDisplayedContests(prev => [...prev, ...newContests])
        setCurrentPage(nextPage)
        setHasMore(endIndex < allContests.length)
      } else {
        setHasMore(false)
      }
    } catch (error) {
      console.error('Error loading more contests:', error)
    } finally {
      setIsLoadingMore(false)
    }
  }, [currentPage, allContests, hasMore, isLoadingMore, searchTerm])

  // Filtrer les contests selon la recherche
  const filteredContests = React.useMemo(() => {
    if (searchTerm === '') {
      console.log('[ContestsPage] filteredContests (no search):', displayedContests.length, 'contests')
      return displayedContests
    }
    const filtered = allContests.filter(contest =>
      contest.title.toLowerCase().includes(searchTerm.toLowerCase())
    ).slice(0, ITEMS_PER_PAGE * currentPage)
    console.log('[ContestsPage] filteredContests (with search):', filtered.length, 'contests')
    return filtered
  }, [searchTerm, displayedContests, allContests, currentPage])

  const handleToggleFavorite = async (contestId: string) => {
    try {
      if (favorites.includes(contestId)) {
        // Retirer des favoris
        await contestService.removeContestFavorite(contestId)
        setFavorites(prevFavorites => prevFavorites.filter(id => id !== contestId))
        addToast('❤️ ' + t('dashboard.contests.removed_from_favorites'), 'success')
      } else {
        // Ajouter aux favoris
        if (favorites.length >= 5) {
          addToast('⚠️ ' + t('dashboard.contests.favorite_limit_reached'), 'error')
          return
        }
        await contestService.addContestFavorite(contestId)
        setFavorites(prevFavorites => [...prevFavorites, contestId])
        addToast('❤️ ' + t('dashboard.contests.added_to_favorites'), 'success')
      }
    } catch (error) {
      console.error('Erreur lors de la modification des favoris:', error)
      addToast('❌ ' + t('common.error'), 'error')
    }
  }

  const handleViewContestants = (contestId: string) => {
    router.push(`/dashboard/contests/${contestId}`)
  }

  const handleParticipate = (contestId: string) => {
    router.push(`/dashboard/contests/${contestId}/participate`)
  }

  // Debug log pour vérifier l'état
  React.useEffect(() => {
    console.log('[ContestsPage] Render state:', {
      isLoading,
      pageLoading,
      isAuthenticated,
      allContestsLength: allContests.length,
      displayedContestsLength: displayedContests.length,
      filteredContestsLength: filteredContests.length,
      filteredContests: filteredContests.slice(0, 2) // Log first 2
    })
  }, [isLoading, pageLoading, isAuthenticated, allContests.length, displayedContests.length, filteredContests])

  if (isLoading || pageLoading) {
    return <ContestsSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  // Vérifier si le profil est complet
  const isProfileComplete = !!(user.first_name && user.last_name && user.avatar_url && user.bio && user.gender && user.date_of_birth && user.country && user.city)
  
  // Vérifier si le KYC est passé
  const isKycVerified = !!user.identity_verified
  
  // L'utilisateur peut participer si le profil est complet
  // Le KYC sera vérifié par concours (certains concours n'exigent pas le KYC)
  const canParticipate = isProfileComplete

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8 space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <h1 className="text-4xl font-bold bg-gradient-to-r from-myfav-primary to-myfav-primary-dark bg-clip-text text-transparent">
                {t('dashboard.contests.title')}
              </h1>
              <p className="text-lg text-gray-600 dark:text-gray-400">
                {t('dashboard.contests.description')}
              </p>
            </div>
          </div>
        </div>

        {/* Alertes profil/KYC - Desktop */}
        {!canParticipate && (
          <div className="hidden md:block mb-6 space-y-3">
            {!isProfileComplete && (
              <div className="flex items-center justify-between gap-4 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-amber-100 dark:bg-amber-800/50 rounded-lg">
                    <UserCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <div>
                    <p className="font-medium text-amber-900 dark:text-amber-200">
                      {t('contests.profile_incomplete_title') || 'Profil incomplet'}
                    </p>
                    <p className="text-sm text-amber-700 dark:text-amber-300">
                      {t('contests.profile_incomplete_message') || 'Complétez votre profil pour pouvoir participer aux concours.'}
                    </p>
                  </div>
                </div>
                <Link href="/dashboard/settings">
                  <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white rounded-lg">
                    {t('contests.complete_profile') || 'Compléter'}
                    <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                </Link>
              </div>
            )}

          </div>
        )}

        {/* Alerte KYC informative (non bloquante) - certains concours peuvent l'exiger */}
        {isProfileComplete && !isKycVerified && (
          <div className="hidden md:block mb-6">
            <div className="flex items-center justify-between gap-4 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700/50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-800/50 rounded-lg">
                  <Fingerprint className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <p className="font-medium text-blue-900 dark:text-blue-200">
                    {t('contests.kyc_recommended_title') || 'Vérification d\'identité recommandée'}
                  </p>
                  <p className="text-sm text-blue-700 dark:text-blue-300">
                    {t('contests.kyc_recommended_message') || 'Certains concours exigent la vérification KYC pour participer.'}
                  </p>
                </div>
              </div>
              <Link href="/dashboard/kyc">
                <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg">
                  {t('contests.verify_identity') || 'Vérifier'}
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </Link>
            </div>
          </div>
        )}

        {/* Notification flottante - Mobile - Profil incomplet */}
        {!canParticipate && showMobileAlert && (
          <div className="md:hidden fixed bottom-4 left-4 right-4 z-50 animate-in slide-in-from-bottom duration-300">
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-xl shrink-0">
                  <UserCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-900 dark:text-white text-sm">
                    {t('contests.profile_incomplete_title') || 'Profil incomplet'}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">
                    {t('contests.profile_incomplete_message') || 'Complétez votre profil pour participer.'}
                  </p>
                </div>
                <button
                  onClick={() => setShowMobileAlert(false)}
                  className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg shrink-0"
                >
                  <X className="w-4 h-4 text-gray-400" />
                </button>
              </div>
              <Link href="/dashboard/settings" className="block mt-3">
                <Button size="sm" className="w-full bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-sm">
                  {t('contests.complete_profile') || 'Compléter mon profil'}
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </Link>
            </div>
          </div>
        )}

        {/* Grille de contests */}
        <ContestsGrid
          contests={filteredContests}
          favorites={favorites}
          onToggleFavorite={handleToggleFavorite}
          onViewContestants={handleViewContestants}
          onParticipate={handleParticipate}
          isLoading={false}
          userGender={(user as any)?.gender as 'male' | 'female' | 'other' | 'prefer_not_to_say' | null | undefined}
          canParticipate={canParticipate}
          isKycVerified={isKycVerified}
        />

        {/* Loader pour infinite scroll */}
        <ContestsLoader
          isLoading={isLoadingMore}
          hasMore={hasMore && searchTerm === ''}
          observerTarget={observerTarget}
        />
      </div>
    </div>
  )
}
