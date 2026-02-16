'use client'

import * as React from "react"
import { useState, useEffect, useMemo, Suspense, useRef, useCallback } from "react"
import dynamic from 'next/dynamic'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useSearchParams } from 'next/navigation'
import { useToast } from '@/components/ui/toast'
import { ContestsSkeleton } from '@/components/ui/skeleton'
import { Lightbulb, Loader2, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { logger } from '@/lib/logger'
import { LocationFilterBar } from '@/components/dashboard/location-filter-bar'

// GraphQL
// REST API
import ApiService, { Round } from '@/lib/api-service'

// Lazy load heavy components
const ContestCard = dynamic(() => import('@/components/dashboard/contest-card').then(mod => ({ default: mod.ContestCard })), {
  ssr: false,
  loading: () => <div className="h-64 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg" />
})

const SuggestContestDialog = dynamic(() => import('@/components/dashboard/suggest-contest-dialog').then(mod => ({ default: mod.SuggestContestDialog })), {
  ssr: false
})

const CONTESTS_PER_PAGE = 12
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes cache

// Simple in-memory cache for contests data
const contestsCache = new Map<string, { data: any; timestamp: number }>()

function getCacheKey(roundId: string, category: string, country: string, continent: string, search: string, skip: number) {
  return `${roundId}-${category}-${country}-${continent}-${search}-${skip}`
}

function getFromCache(key: string) {
  const cached = contestsCache.get(key)
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data
  }
  contestsCache.delete(key)
  return null
}

function setToCache(key: string, data: any) {
  contestsCache.set(key, { data, timestamp: Date.now() })
}

function ContestsPageContent() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { addToast } = useToast()

  // State
  const [activeRoundId, setActiveRoundId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<string>('all') // Contest Type tab
  const [categoryTab, setCategoryTab] = useState<'nomination' | 'participations'>(() => {
    if (typeof window !== 'undefined') {
      const savedTab = localStorage.getItem('contests_category_tab')
      if (savedTab === 'nomination' || savedTab === 'participations') {
        return savedTab as 'nomination' | 'participations'
      }
    }
    return 'nomination'
  })
  const [showSuggestDialog, setShowSuggestDialog] = useState(false)

  // Filter States
  const [searchTerm, setSearchTerm] = useState('')
  const [committedSearch, setCommittedSearch] = useState('') // New state for executed search
  const [sortBy, setSortBy] = useState<string>('participants')
  const [filterContinent, setFilterContinent] = useState<string>('all')
  const [filterCountry, setFilterCountry] = useState<string>('')
  const [filterLevel, setFilterLevel] = useState<string>('city') // Level filter for participations: 'city', 'country', 'all'

  // Data States
  const [rounds, setRounds] = useState<Round[]>([])
  const [roundsLoading, setRoundsLoading] = useState(true)
  const [contestsData, setContestsData] = useState<Round | null>(null)
  const [contestsLoading, setContestsLoading] = useState(false)
  const [initialLoadComplete, setInitialLoadComplete] = useState(false)

  // Infinite scroll states
  const [allContests, setAllContests] = useState<any[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [totalContests, setTotalContests] = useState(0)
  const loaderRef = useRef<HTMLDivElement>(null)

  // 1. Fetch Rounds for Selector
  useEffect(() => {
    if (!isAuthenticated) return

    const fetchRounds = async () => {
      try {
        setRoundsLoading(true)
        const data = await ApiService.getRounds({ isActive: false })
        setRounds(data)

        // Set default active round
        if (data.length > 0 && !activeRoundId) {
          setActiveRoundId(String(data[0].id))
        }
      } catch (error) {
        console.error('Failed to fetch rounds:', error)
        addToast("Failed to load rounds", "error")
      } finally {
        setRoundsLoading(false)
      }
    }

    fetchRounds()
  }, [isAuthenticated, addToast, activeRoundId])

  // Save category tab preference
  useEffect(() => {
    if (typeof window !== 'undefined') localStorage.setItem('contests_category_tab', categoryTab)
  }, [categoryTab])

  // Set default filters based on category tab and user location (only when no filter is set yet)
  useEffect(() => {
    if (!user) return

    if (categoryTab === 'nomination') {
      // Only set default country when user has not selected a filter (avoid overwriting e.g. Uganda with user.country)
      if (user.country && !filterCountry) {
        setFilterCountry(user.country)
      }
      if (filterLevel !== 'all') {
        setFilterLevel('all')
      }
    } else if (categoryTab === 'participations') {
      if (filterLevel !== 'city') {
        setFilterLevel('city')
      }
      if (filterCountry) {
        setFilterCountry('')
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryTab, user?.country])

  // Handle Search Execution
  const handleSearch = () => {
    setCommittedSearch(searchTerm)
  }

  // Reset pagination when filters change
  useEffect(() => {
    setAllContests([])
    setHasMore(true)
    setInitialLoadComplete(false)
  }, [activeRoundId, categoryTab, filterCountry, filterContinent, filterLevel, committedSearch])

  // 2. Fetch Contests for Selected Round (Initial load)
  useEffect(() => {
    if (!activeRoundId || !isAuthenticated) return

    const fetchContestsForRound = async () => {
      setContestsLoading(true)
      const hasVotingType = categoryTab === 'nomination'
      const activeCountry = filterCountry !== 'all' ? filterCountry : undefined
      const activeContinent = filterContinent !== 'all' ? filterContinent : undefined
      const activeSearch = committedSearch || undefined

      // Check cache first
      const cacheKey = getCacheKey(activeRoundId, categoryTab, activeCountry || 'all', activeContinent || 'all', activeSearch || '', 0)
      const cached = getFromCache(cacheKey)
      if (cached) {
        setContestsData(cached)
        setAllContests(cached.contests || [])
        setTotalContests(cached.contests_count || cached.contests?.length || 0)
        setHasMore((cached.contests?.length || 0) < (cached.contests_count || 0))
        setContestsLoading(false)
        setInitialLoadComplete(true)
        return
      }

      try {
        const data = await ApiService.getRounds({
          roundId: parseInt(activeRoundId),
          isActive: false,
          hasVotingType,
          filterCountry: activeCountry,
          filterContinent: activeContinent,
          searchTerm: activeSearch,
          contestLimit: CONTESTS_PER_PAGE
        })

        if (data && data.length > 0) {
          setContestsData(data[0])
          setAllContests(data[0].contests || [])
          setTotalContests(data[0].contests_count || data[0].contests?.length || 0)
          setHasMore((data[0].contests?.length || 0) < (data[0].contests_count || 0))
          // Cache the result
          setToCache(cacheKey, data[0])
        } else {
          setContestsData(null)
          setAllContests([])
          setTotalContests(0)
          setHasMore(false)
        }
      } catch (error) {
        console.error('Failed to fetch contests:', error)
      } finally {
        setContestsLoading(false)
        setInitialLoadComplete(true)
      }
    }

    fetchContestsForRound()
  }, [activeRoundId, isAuthenticated, categoryTab, filterCountry, filterContinent, committedSearch])

  // Load more contests function
  const loadMoreContests = useCallback(async () => {
    if (loadingMore || !hasMore || !activeRoundId) return

    setLoadingMore(true)
    const hasVotingType = categoryTab === 'nomination'
    const activeCountry = filterCountry !== 'all' ? filterCountry : undefined
    const activeContinent = filterContinent !== 'all' ? filterContinent : undefined
    const activeSearch = committedSearch || undefined

    try {
      const data = await ApiService.getRounds({
        roundId: parseInt(activeRoundId),
        isActive: false,
        hasVotingType,
        filterCountry: activeCountry,
        filterContinent: activeContinent,
        searchTerm: activeSearch,
        contestLimit: CONTESTS_PER_PAGE,
        contestSkip: allContests.length  // Skip already loaded contests
      })

      if (data && data.length > 0 && data[0].contests) {
        const newContests = data[0].contests
        // Append new contests to existing ones
        setAllContests(prev => [...prev, ...newContests])
        // Check if there are more by comparing total loaded vs total count
        setHasMore(allContests.length + newContests.length < (data[0].contests_count || 0))
      } else {
        setHasMore(false)
      }
    } catch (error) {
      console.error('Failed to load more contests:', error)
    } finally {
      setLoadingMore(false)
    }
  }, [loadingMore, hasMore, activeRoundId, categoryTab, filterCountry, filterContinent, committedSearch, allContests.length])

  // Intersection Observer for infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore) {
          loadMoreContests()
        }
      },
      { threshold: 0.1 }
    )

    if (loaderRef.current) {
      observer.observe(loaderRef.current)
    }

    return () => observer.disconnect()
  }, [hasMore, loadingMore, loadMoreContests])

  // Raw Contests List (Before filtering by type) - Now uses allContests for infinite scroll
  const rawContests = useMemo(() => {
    if (!allContests || allContests.length === 0) return []

    return allContests.map((c: any) => {
      // Stats are now directly on the contest object in the new schema
      // Fallback multiple pour l'image
      const rawImage = c.cover_image_url || c.image_url || '/placeholder.png'

      const isEmoji = rawImage?.length <= 4 && rawImage?.codePointAt(0) > 0x1F000
      let coverImage = rawImage

      if (!isEmoji && coverImage && !coverImage.startsWith('http') && !coverImage.startsWith('data:') && !coverImage.startsWith('/')) {
        const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        coverImage = `${API_BASE_URL}/${coverImage}`
      }

      return {
        id: String(c.id),
        title: c.name,
        description: c.description,
        coverImage: coverImage,
        startDate: new Date(),
        status: c.level || 'country',
        received: Number(c.votes_count) || 0,
        contestants: Number(c.participants_count) || Number(c.entries_count) || 0,
        isOpen: contestsData?.is_submission_open || contestsData?.is_voting_open || false,
        contestType: c.contest_type,
        isSubmissionOpen: contestsData?.is_submission_open,
        isVotingOpen: contestsData?.is_voting_open,
        // Pass dates for countdown in ContestCard
        participationStartDate: contestsData?.submission_start_date,
        participationEndDate: contestsData?.submission_end_date,
        votingStartDate: contestsData?.voting_start_date,
        votingEndDate: contestsData?.voting_end_date,
        currentUserParticipated: c.current_user_contesting || false,
        currentUserContesting: c.current_user_contesting || false,
        topContestants: [] // Not fetching top contestants per contest in new query yet
      }
    })
  }, [allContests, contestsData])

  // Extract contest types from ALL loaded contests (so tabs don't disappear)
  const contestTypes = useMemo(() => {
    const types = new Set<string>()
    rawContests.forEach((c: any) => c.contestType && types.add(c.contestType))

    const list = [{ id: 'all', label: t('dashboard.contests.all') || 'All', value: null }]
    Array.from(types).sort().forEach(type => {
      list.push({ id: type, label: type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, ' '), value: type })
    })
    return list
  }, [rawContests, t])

  // Filter and Sort Contests for Display
  const displayedContests = useMemo(() => {
    let filtered = rawContests.slice()

    // 1. Filter by Tab (Type)
    if (activeTab !== 'all') {
      filtered = filtered.filter(c => c.contestType === activeTab)
    }

    // 2. Filter by Search
    if (committedSearch) {
      const lower = committedSearch.toLowerCase()
      filtered = filtered.filter(c => c.title.toLowerCase().includes(lower))
    }

    // 3. Filter by Level (for participations tab)
    if (categoryTab === 'participations' && filterLevel !== 'all') {
      filtered = filtered.filter(c => c.status === filterLevel)
    }

    // 4. Sort - Backend already pre-sorts by participants, but we re-sort here for user's sort choice
    // This is fast because it's just reordering an already-filtered small array
    if (sortBy !== 'participants') {
      // Only sort if user selected a different sort option (not the default)
      filtered.sort((a, b) => {
        switch (sortBy) {
          case 'votes': 
            const aVotes = Number(a.received) || 0
            const bVotes = Number(b.received) || 0
            if (bVotes !== aVotes) {
              return bVotes - aVotes
            }
            // Secondary sort by participants if votes are equal
            return (Number(b.contestants) || 0) - (Number(a.contestants) || 0)
          case 'name': 
            return a.title.localeCompare(b.title)
          default: 
            // Fallback to participants (backend already sorted this way)
            const aContestants = Number(a.contestants) || 0
            const bContestants = Number(b.contestants) || 0
            return bContestants - aContestants
        }
      })
    }
    // If sortBy is 'participants' (default), backend already sorted correctly, no need to re-sort

    return filtered
  }, [rawContests, activeTab, committedSearch, sortBy, categoryTab, filterLevel])

  // Handlers
  const handleParticipate = (id: string, isEditing: boolean) => {
    router.push(isEditing ? `/dashboard/contests/${id}/apply?edit=true` : `/dashboard/contests/${id}/apply`)
  }

  if (isLoading || (roundsLoading && rounds.length === 0)) return <ContestsSkeleton />
  if (!isAuthenticated) return null

  return (
    <div className="min-h-screen bg-gray-900 dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Header & Suggest Button */}
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-2xl font-bold text-white">Contests</h1>
          <Button onClick={() => setShowSuggestDialog(true)} className="bg-blue-600 hover:bg-blue-700 text-white">
            <Lightbulb className="w-4 h-4 mr-2" /> Suggest
          </Button>
        </div>

        {/* Round Selector (Top Tabs) */}
        <div className="mb-6">
          <div className="flex space-x-2 overflow-x-auto pb-2 scrollbar-hide">
            {rounds.map((round: any) => (
              <button
                key={round.id}
                onClick={() => setActiveRoundId(String(round.id))}
                className={`px-5 py-2.5 rounded-full text-sm font-medium transition-all whitespace-nowrap ${activeRoundId === String(round.id)
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
                  }`}
              >
                {round.name} <span className="ml-1 opacity-70">({round.contests_count !== undefined ? round.contests_count : (round.contests?.length || 0)})</span>
              </button>
            ))}
          </div>
        </div>

        {/* Location Filter Bar */}
        <div className="mb-6">
          <LocationFilterBar
            user={user}
            searchTerm={searchTerm}
            onSearchChange={setSearchTerm}
            onSearch={handleSearch}
            searchPlaceholder={t('dashboard.contests.search_placeholder') || 'Search...'}
            filterContinent={filterContinent}
            onContinentChange={setFilterContinent}
            filterCountry={filterCountry}
            onCountryChange={setFilterCountry}
            sortBy={sortBy}
            onSortChange={setSortBy}
            showCountryFilter={categoryTab === 'nomination'} // Only show country filter for nominations
            className="mb-4"
          />
          
          {/* Level Filter for Participations */}
          {categoryTab === 'participations' && (
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-300 whitespace-nowrap">
                {t('dashboard.contests.filter_level') || 'Level:'}
              </label>
              <Select value={filterLevel} onValueChange={setFilterLevel}>
                <SelectTrigger className="w-48 bg-gray-800 border-gray-700 text-white">
                  <MapPin className="w-4 h-4 mr-2" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-gray-800 border-gray-700">
                  <SelectItem value="city">
                    {t('dashboard.contests.level_city') || 'City'}
                  </SelectItem>
                  <SelectItem value="country">
                    {t('dashboard.contests.level_country') || 'Country'}
                  </SelectItem>
                  <SelectItem value="all">
                    {t('dashboard.contests.all_levels') || 'All Levels'}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {/* Main Category Tabs (Nomination / Participations) */}
        <div className="mb-6 border-b border-gray-800">
          <div className="flex space-x-1">
            <button
              onClick={() => {
                setCategoryTab('nomination');
                setActiveTab('all');
                setSearchTerm('');
                setCommittedSearch('');
                setFilterContinent('all');
                // Set country filter to user's country for nominations
                if (user?.country) {
                  setFilterCountry(user.country);
                } else {
                  setFilterCountry('');
                }
                setFilterLevel('all'); // Reset level filter
              }}
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${categoryTab === 'nomination' ? 'border-blue-500 text-blue-500' : 'border-transparent text-gray-400 hover:text-gray-300'}`}
            >
              {t('dashboard.contests.nomination') || 'Nomination'}
            </button>
            <button
              onClick={() => {
                setCategoryTab('participations');
                setActiveTab('all');
                setSearchTerm('');
                setCommittedSearch('');
                setFilterCountry(''); // Reset country filter for participations
                setFilterContinent('all');
                setFilterLevel('city'); // Default to city level for participations
              }}
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${categoryTab === 'participations' ? 'border-blue-500 text-blue-500' : 'border-transparent text-gray-400 hover:text-gray-300'}`}
            >
              {t('dashboard.contests.participations') || 'Participations'}
            </button>
          </div>
        </div>

        {/* Type Tabs (Generated from ALL contests in round) */}
        {contestTypes.length > 1 && (
          <div className="mb-8 border-b border-gray-800">
            <div className="flex space-x-6 overflow-x-auto scrollbar-hide">
              {contestTypes.map((type) => (
                <button
                  key={type.id}
                  onClick={() => setActiveTab(type.id || 'all')}
                  className={`pb-4 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${activeTab === (type.id || 'all')
                    ? 'border-blue-500 text-blue-500'
                    : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-700'
                    }`}
                >
                  {type.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Contests Grid */}
        {contestsLoading && !contestsData ? (
          <ContestsSkeleton />
        ) : displayedContests.length > 0 ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {displayedContests.map((contest: any) => (
                <ContestCard
                  key={contest.id}
                  {...contest}
                  canParticipate={true}
                  isKycVerified={!!user?.identity_verified}
                  isFavorite={false}
                  isNomination={categoryTab === 'nomination'}
                  onToggleFavorite={() => { }}
                  onParticipate={() => handleParticipate(contest.id, contest.currentUserContesting || false)}
                  onViewContestants={() => {
                    const params = new URLSearchParams()
                    if (filterCountry && filterCountry !== 'all') params.set('country', filterCountry)
                    params.set('continent', filterContinent !== 'all' ? filterContinent : 'all')
                    const q = params.toString()
                    router.push(`/dashboard/contests/${contest.id}${q ? `?${q}` : ''}`)
                  }}
                  onOpenDetails={() => {
                    const params = new URLSearchParams()
                    if (filterCountry && filterCountry !== 'all') params.set('country', filterCountry)
                    params.set('continent', filterContinent !== 'all' ? filterContinent : 'all')
                    const q = params.toString()
                    router.push(`/dashboard/contests/${contest.id}${q ? `?${q}` : ''}`)
                  }}
                />
              ))}
            </div>

            {/* Infinite scroll loader */}
            <div ref={loaderRef} className="flex justify-center py-8">
              {loadingMore && (
                <div className="flex items-center gap-2 text-gray-400">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Loading more...</span>
                </div>
              )}
              {!hasMore && allContests.length > 0 && (
                <span className="text-gray-500">
                  {t('admin.contests.all_loaded') || `Showing all ${totalContests} contests`}
                </span>
              )}
            </div>
          </>
        ) : !initialLoadComplete ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            <p className="text-gray-500">{t('common.loading') || 'Loading...'}</p>
          </div>
        ) : (
          <div className="text-center py-20">
            <p className="text-gray-500">{t('contests.no_contests') || 'No contests found matching criteria.'}</p>
          </div>
        )}

        <SuggestContestDialog open={showSuggestDialog} onOpenChange={setShowSuggestDialog} />
      </div>
    </div>
  )
}

export default function ContestsPage() {
  return (
    <Suspense fallback={<ContestsSkeleton />}>
      <ContestsPageContent />
    </Suspense>
  )
}
