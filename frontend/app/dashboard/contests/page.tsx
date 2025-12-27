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
import { AlertCircle, UserCircle, Fingerprint, ChevronRight, X, Lightbulb, Search, ArrowUpDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ContestCard } from '@/components/dashboard/contest-card'
import { SuggestContestDialog } from '@/components/dashboard/suggest-contest-dialog'

export default function ContestsPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const { addToast } = useToast()
  const [allContests, setAllContests] = useState<Contest[]>([])
  const [displayedContests, setDisplayedContests] = useState<Contest[]>([])
  const [favorites, setFavorites] = useState<string[]>([])
  const [searchTerm, setSearchTerm] = useState('') // Terme de recherche dans l'input
  const [activeSearchTerm, setActiveSearchTerm] = useState('') // Terme de recherche actif (utilisé pour l'API)
  const [pageLoading, setPageLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [showMobileAlert, setShowMobileAlert] = useState(true)
  const [activeTab, setActiveTab] = useState<string>('all')
  const [showSuggestDialog, setShowSuggestDialog] = useState(false)
  const [categoryTab, setCategoryTab] = useState<'nomination' | 'participations'>('participations')
  const [sortBy, setSortBy] = useState<string>('participants') // participants, votes, date, name
  const ITEMS_PER_PAGE = 9
  const observerTarget = React.useRef(null)
  const isLoadingDataRef = React.useRef(false)
  const isMountedRef = React.useRef(true)

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
    
    // Éviter les appels multiples simultanés
    if (isLoadingDataRef.current) {
      return
    }
    
    // Réinitialiser les données quand searchTerm ou categoryTab change
    // (mais seulement si on a déjà des données, pour éviter de réinitialiser au premier chargement)
    if (allContests.length > 0) {
      setAllContests([])
      setDisplayedContests([])
      setCurrentPage(1)
    }
    
    const loadData = async () => {
      isLoadingDataRef.current = true
      
      try {
        setPageLoading(true)
        
        // Récupérer les contests du backend avec filtres
        // Pour l'onglet Nominations : filtrer les contests qui ont un voting_type (has_voting_type = true)
        // Pour l'onglet Participations : filtrer les contests qui n'ont pas de voting_type (has_voting_type = false)
        const hasVotingType = categoryTab === 'nomination' ? true : categoryTab === 'participations' ? false : undefined
        const apiContests = await contestService.getContests(
          0, 
          100,
          activeSearchTerm || undefined,
          undefined, // votingLevel n'est plus utilisé, on utilise has_voting_type à la place
          undefined, // votingTypeId
          hasVotingType
        )
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
          
          // Trier les contests selon l'option de tri sélectionnée
          const sortedContests = [...contests].sort((a, b) => {
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
                // Par défaut : participants puis votes
            if (b.contestants !== a.contestants) {
              return b.contestants - a.contestants
            }
            return b.received - a.received
            }
          })
          
          console.log('[ContestsPage] Setting state with', sortedContests.length, 'contests')
          if (isMountedRef.current) {
            setAllContests(sortedContests)
            // Le filtrage par catégorie est maintenant fait côté backend via has_voting_type
          // On garde ce filtre pour compatibilité, mais il devrait déjà être appliqué par le backend
            const categoryFiltered = sortedContests.filter(contest => {
              if (categoryTab === 'nomination') {
                return contest.votingType != null
              } else {
                return contest.votingType == null
              }
            })
            setDisplayedContests(categoryFiltered.slice(0, ITEMS_PER_PAGE))
            setHasMore(categoryFiltered.length > ITEMS_PER_PAGE)
            setCurrentPage(1) // Réinitialiser la page
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
  }, [isLoading, isAuthenticated, activeSearchTerm, categoryTab])

  // Mettre à jour displayedContests quand categoryTab ou sortBy change
  useEffect(() => {
    if (allContests.length === 0) return
    
    // Le filtrage par catégorie est maintenant fait côté backend via has_voting_type
    let categoryFiltered = allContests.filter(contest => {
      if (categoryTab === 'nomination') {
        return contest.votingType != null
      } else {
        return contest.votingType == null
      }
    })
    
    // Appliquer le tri
    const sorted = [...categoryFiltered].sort((a, b) => {
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
    
    setDisplayedContests(sorted.slice(0, ITEMS_PER_PAGE))
    setHasMore(sorted.length > ITEMS_PER_PAGE)
    setCurrentPage(1)
  }, [categoryTab, allContests, sortBy])

  // Infinite scroll avec Intersection Observer
  useEffect(() => {
    if (activeSearchTerm !== '' || activeTab !== 'all') return // Ne pas observer si on est en mode recherche ou filtre par type
    
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore && activeSearchTerm === '' && activeTab === 'all') {
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
  }, [hasMore, isLoadingMore, searchTerm, activeTab, allContests.length])

  const loadMore = React.useCallback(() => {
    if (isLoadingMore || !hasMore || activeSearchTerm !== '' || activeTab !== 'all') return
    
    setIsLoadingMore(true)
    try {
      // Filtrer selon la catégorie active
      // Le filtrage est maintenant fait côté backend via has_voting_type
      let categoryFiltered = allContests.filter(contest => {
        if (categoryTab === 'nomination') {
          return contest.votingType != null
        } else {
          return contest.votingType == null
        }
      })
      
      // Appliquer le tri
      const sorted = [...categoryFiltered].sort((a, b) => {
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
      
      const nextPage = currentPage + 1
      const startIndex = currentPage * ITEMS_PER_PAGE
      const endIndex = startIndex + ITEMS_PER_PAGE
      const newContests = sorted.slice(startIndex, endIndex)
      
      if (newContests.length > 0) {
        setDisplayedContests(prev => [...prev, ...newContests])
        setCurrentPage(nextPage)
        setHasMore(endIndex < sorted.length)
      } else {
        setHasMore(false)
      }
    } catch (error) {
      console.error('Error loading more contests:', error)
    } finally {
      setIsLoadingMore(false)
    }
  }, [currentPage, allContests, hasMore, isLoadingMore, searchTerm, activeTab, categoryTab, sortBy])


  // Filtrer et trier les contests selon la catégorie (Nomination/Participations), la recherche et l'onglet actif
  const filteredContests = React.useMemo(() => {
    let contests = allContests
    
    // Filtrer par catégorie (Nomination ou Participations)
    // Le filtrage est maintenant fait côté backend via has_voting_type
    // On garde ce filtre pour compatibilité, mais il devrait déjà être appliqué par le backend
    if (categoryTab === 'nomination') {
      // Nomination : contests avec voting_type défini
      contests = contests.filter(contest => contest.votingType != null)
    } else {
      // Participations : contests sans voting_type
      contests = contests.filter(contest => contest.votingType == null)
    }
    
    // Filtrer par type si un onglet est sélectionné
    if (activeTab !== 'all') {
      const selectedType = contestTypes.find(t => t.id === activeTab)
      if (selectedType && selectedType.value) {
        contests = contests.filter(contest => contest.contestType === selectedType.value)
      }
    }
    
    // La recherche est maintenant gérée côté backend, pas besoin de filtrer ici
    
    // Trier les contests selon l'option sélectionnée
    const sortedContests = [...contests].sort((a, b) => {
      switch (sortBy) {
        case 'participants':
          // Trier par nombre de participants (décroissant)
          if (b.contestants !== a.contestants) {
            return b.contestants - a.contestants
          }
          return b.received - a.received
        case 'votes':
          // Trier par nombre de votes (décroissant)
          if (b.received !== a.received) {
            return b.received - a.received
          }
          return b.contestants - a.contestants
        case 'date':
          // Trier par date de début (décroissant - plus récent en premier)
          return new Date(b.startDate).getTime() - new Date(a.startDate).getTime()
        case 'name':
          // Trier par nom (alphabétique)
          return a.title.localeCompare(b.title)
        default:
          // Par défaut : participants puis votes
          if (b.contestants !== a.contestants) {
            return b.contestants - a.contestants
          }
          return b.received - a.received
      }
    })
    
    // Limiter pour l'infinite scroll (seulement si pas de recherche et pas de filtre par type)
    if (activeSearchTerm === '' && activeTab === 'all') {
      return displayedContests
    }
    
    return sortedContests.slice(0, ITEMS_PER_PAGE * currentPage)
  }, [searchTerm, displayedContests, allContests, currentPage, activeTab, contestTypes, categoryTab, sortBy])

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

  // Fonction pour déclencher la recherche
  const handleSearch = () => {
    // Si la recherche est vide, réinitialiser pour afficher toute la liste
    if (searchTerm.trim() === '') {
      setActiveSearchTerm('')
    } else {
      setActiveSearchTerm(searchTerm)
    }
    setCurrentPage(1)
    setDisplayedContests([])
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
      setCurrentPage(1)
      setDisplayedContests([])
    }
  }, [searchTerm, activeSearchTerm])

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
    <div className="min-h-screen bg-gray-900 dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header avec bouton de suggestion */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex-1" />
          <Button
            onClick={() => setShowSuggestDialog(true)}
            className="bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white shadow-lg hover:shadow-xl transition-all font-semibold"
          >
            <Lightbulb className="w-4 h-4 mr-2" />
            {t('dashboard.contests.suggest_contest.button') || 'Suggérer un concours'}
          </Button>
        </div>
       
        {/* Barre d'onglets principaux (Nomination / Participations) */}
        <div className="mb-6 border-b border-gray-800">
          <div className="flex space-x-1">
            <button
              onClick={() => {
                setCategoryTab('nomination')
                setActiveTab('all')
                setCurrentPage(1)
                setDisplayedContests([])
              }}
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${
                categoryTab === 'nomination'
                  ? 'border-blue-500 text-blue-500'
                  : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-600'
              }`}
            >
              {t('dashboard.contests.nomination') || 'Nomination'}
            </button>
            <button
              onClick={() => {
                setCategoryTab('participations')
                setActiveTab('all')
                setCurrentPage(1)
                setDisplayedContests([])
              }}
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${
                categoryTab === 'participations'
                  ? 'border-blue-500 text-blue-500'
                  : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-600'
              }`}
            >
              {t('dashboard.contests.participations') || 'Participations'}
            </button>
          </div>
        </div>

        {/* Barre de recherche et tri */}
        <div className="mb-6 flex flex-col sm:flex-row gap-4">
          {/* Barre de recherche */}
          <div className="flex-1 flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
              <Input
                type="text"
                placeholder={t('dashboard.contests.search_placeholder') || 'Rechercher un concours...'}
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value)
                }}
                onKeyPress={handleSearchKeyPress}
                className="pl-10 bg-gray-800 border-gray-700 text-white placeholder-gray-400 focus:border-blue-500"
              />
            </div>
            <Button
              onClick={handleSearch}
              className="bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white px-6"
            >
              <Search className="w-4 h-4 mr-2" />
              {t('dashboard.contests.search_button') || 'Rechercher'}
            </Button>
          </div>
          
          {/* Sélecteur de tri */}
          <div className="w-full sm:w-48">
            <Select value={sortBy} onValueChange={(value) => {
              setSortBy(value)
              setCurrentPage(1)
              setDisplayedContests([])
            }}>
              <SelectTrigger className="bg-gray-800 border-gray-700 text-white">
                <ArrowUpDown className="w-4 h-4 mr-2" />
                <SelectValue placeholder={t('dashboard.contests.sort') || 'Trier par'} />
              </SelectTrigger>
              <SelectContent className="bg-gray-800 border-gray-700">
                <SelectItem value="participants">
                  {t('dashboard.contests.sort_participants') || 'Plus de participants'}
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
        <div className="mb-8 border-b border-gray-800">
          <div className="flex space-x-1 overflow-x-auto scrollbar-hide">
            {contestTypes.map((type) => (
              <button
                key={type.id}
                onClick={() => {
                  setActiveTab(type.id)
                  setCurrentPage(1)
                  setDisplayedContests([])
                }}
                className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                  activeTab === type.id
                    ? 'border-white text-white'
                    : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-600'
                }`}
              >
                {type.label}
              </button>
            ))}
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
                  <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg">
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
                <Button size="sm" className="w-full bg-blue-500 hover:bg-blue-600 text-white rounded-xl text-sm">
                  {t('contests.complete_profile') || 'Compléter mon profil'}
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </Link>
            </div>
          </div>
        )}

        {/* Affichage en grille simple */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6">
          {filteredContests.map((contest) => (
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
              isFavorite={favorites.includes(contest.id)}
              genderRestriction={contest.genderRestriction}
              participationStartDate={contest.participationStartDate}
              participationEndDate={contest.participationEndDate}
              votingStartDate={contest.votingStartDate}
              userGender={(user as any)?.gender as 'male' | 'female' | 'other' | 'prefer_not_to_say' | null | undefined}
              canParticipate={canParticipate}
              isKycVerified={isKycVerified}
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
              onToggleFavorite={() => handleToggleFavorite(contest.id)}
              onViewContestants={() => handleViewContestants(contest.id)}
              onParticipate={() => handleParticipate(contest.id)}
              onOpenDetails={() => handleViewContestants(contest.id)}
            />
          ))}
        </div>

        {/* Loader pour infinite scroll */}
        <ContestsLoader
          isLoading={isLoadingMore}
          hasMore={hasMore && activeSearchTerm === ''}
          observerTarget={observerTarget}
        />

        {/* Dialog de suggestion de concours */}
        <SuggestContestDialog
          open={showSuggestDialog}
          onOpenChange={setShowSuggestDialog}
        />
      </div>
    </div>
  )
}
