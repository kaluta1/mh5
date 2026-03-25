'use client'

import * as React from "react"
import { useState, useEffect, useMemo, Suspense, useRef, useCallback } from "react"
import dynamic from 'next/dynamic'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useSearchParams } from 'next/navigation'
import { useToast } from '@/components/ui/toast'
import { ContestsSkeleton } from '@/components/ui/skeleton'
import { Lightbulb, Loader2, MapPin, Lock } from 'lucide-react'
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

const CONTESTS_PER_PAGE = 9 // Reduced from 12 for faster initial load
const INITIAL_CONTESTS = 9 // 8 contests per load
const CACHE_TTL = 5 * 1000 // 5 seconds cache, preventing stale states for participants

// Simple in-memory cache for contests data
const contestsCache = new Map<string, { data: any; timestamp: number }>()

function getCacheKey(roundId: string, category: string, country: string, continent: string, search: string, skip: number, userId?: string | number) {
  return `${roundId}-${category}-${country}-${continent}-${search}-${skip}-${userId || 'anon'}`
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
  const [filterContinent, setFilterContinent] = useState<string>(() => {
    const urlContinent = searchParams.get('continent')
    return urlContinent || 'all'
  })
  const [filterCountry, setFilterCountry] = useState<string>(() => {
    const urlCountry = searchParams.get('country')
    return urlCountry || ''
  })
  const [filterLevel, setFilterLevel] = useState<string>('all') // Level filter for participations: 'city', 'country', 'all'

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

  // 1. Fetch Rounds for Selector (allow unauthenticated users) - Optimized for speed
  useEffect(() => {
    const abortController = new AbortController()
    
    const fetchRounds = async () => {
      try {
        setRoundsLoading(true)
        // Fetch rounds with minimal data for faster response
        const data = await ApiService.getRounds({ contestLimit: 1 }) // Minimal data for round selector
        
        // Check if aborted
        if (abortController.signal.aborted) return
        
        setRounds(data)

        // Set default to current month's round
        if (data.length > 0 && !activeRoundId) {
          const now = new Date()
          const currentMonthName = now.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
          const currentRound = data.find((r: any) => r.name?.includes(currentMonthName))
          setActiveRoundId(String(currentRound ? currentRound.id : data[0].id))
        }
      } catch (error: any) {
        if (error.name === 'AbortError' || abortController.signal.aborted) {
          return
        }
        // Silently handle timeout errors
        if (error?.code === 'ECONNABORTED' || error?.message?.includes('timeout')) {
          logger.warn('Rounds fetch timeout, showing empty state')
          setRounds([])
          return
        }
        logger.error('Failed to fetch rounds:', error)
        addToast("Failed to load rounds", "error")
      } finally {
        if (!abortController.signal.aborted) {
          setRoundsLoading(false)
        }
      }
    }

    fetchRounds()
    
    return () => {
      abortController.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Save category tab preference
  useEffect(() => {
    if (typeof window !== 'undefined') localStorage.setItem('contests_category_tab', categoryTab)
  }, [categoryTab])

  // Sync filters to URL for persistence on refresh
  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString())
    if (filterCountry && filterCountry !== 'all') {
      params.set('country', filterCountry)
    } else {
      params.delete('country')
    }
    if (filterContinent && filterContinent !== 'all') {
      params.set('continent', filterContinent)
    } else {
      params.delete('continent')
    }
    const newUrl = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname
    window.history.replaceState(null, '', newUrl)
  }, [filterCountry, filterContinent, searchParams])

  // Set default filters based on category tab and user location (only when no filter is set yet)
  useEffect(() => {
    if (!user) return

    if (categoryTab === 'nomination') {
      // Set user's country for nominations only if no country already set (from URL or manual selection)
      if (user.country && !filterCountry) {
        setFilterCountry(user.country)
      }
      if (filterLevel !== 'all') {
        setFilterLevel('all')
      }
    } else if (categoryTab === 'participations') {
      if (filterLevel !== 'all') {
        setFilterLevel('all')
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
  }, [activeRoundId, categoryTab, filterCountry, filterContinent, committedSearch])

  // 2. Fetch Contests for Selected Round (Initial load) - allow unauthenticated users
  // Use a ref to track current user id without triggering re-fetches
  const userIdRef = useRef<number | null>(null)
  useEffect(() => {
    userIdRef.current = user?.id ?? null
  }, [user?.id])

  useEffect(() => {
    if (!activeRoundId) return

    // AbortController for request cancellation
    const abortController = new AbortController()

    const fetchContestsForRound = async () => {
      setContestsLoading(true)
      const contestMode = categoryTab === 'nomination' ? 'nomination' : categoryTab === 'participations' ? 'participation' : undefined
      const activeCountry = (filterCountry && filterCountry !== 'all') ? filterCountry : undefined
      const activeContinent = (filterContinent && filterContinent !== 'all') ? filterContinent : undefined
      const activeSearch = committedSearch || undefined

      // Check cache first
      const authKey = userIdRef.current || 'anon'
      const cacheKey = getCacheKey(activeRoundId, categoryTab, activeCountry || 'all', activeContinent || 'all', activeSearch || '', 0, authKey)
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
          contestMode,
          filterCountry: activeCountry,
          filterContinent: activeContinent,
          searchTerm: activeSearch,
          contestLimit: INITIAL_CONTESTS
        })

        // Check if request was aborted
        if (abortController.signal.aborted) return

        if (data && data.length > 0) {
          setContestsData(data[0])
          const contests = data[0].contests || []
          if (contests.length > 1) {
            contests.sort((a: any, b: any) => {
              const aCount = Number(a.participants_count) || 0
              const bCount = Number(b.participants_count) || 0
              return bCount - aCount
            })
          }
          setAllContests(contests)
          setTotalContests(data[0].contests_count || contests.length || 0)
          setHasMore(contests.length < (data[0].contests_count || 0))
          setToCache(cacheKey, data[0])
        } else {
          setContestsData(null)
          setAllContests([])
          setTotalContests(0)
          setHasMore(false)
        }
      } catch (error: any) {
        if (error.name === 'AbortError' || abortController.signal.aborted) {
          return
        }
        // On timeout (Render cold start), retry once automatically
        if (error?.code === 'ECONNABORTED' || error?.message?.includes('timeout')) {
          logger.warn('Request timeout, retrying once...')
          try {
            const retryData = await ApiService.getRounds({
              roundId: parseInt(activeRoundId),
              contestMode,
              filterCountry: activeCountry,
              filterContinent: activeContinent,
              searchTerm: activeSearch,
              contestLimit: INITIAL_CONTESTS
            })
            if (!abortController.signal.aborted && retryData && retryData.length > 0) {
              setContestsData(retryData[0])
              const contests = retryData[0].contests || []
              setAllContests(contests)
              setTotalContests(retryData[0].contests_count || contests.length || 0)
              setHasMore(contests.length < (retryData[0].contests_count || 0))
              setContestsLoading(false)
              setInitialLoadComplete(true)
              return
            }
          } catch {
            // Retry also failed
          }
          setContestsData(null)
          setAllContests([])
          setTotalContests(0)
          setHasMore(false)
          setContestsLoading(false)
          setInitialLoadComplete(true)
          return
        }
        logger.error('Failed to fetch contests:', error)
        setContestsData(null)
        setAllContests([])
        setTotalContests(0)
        setHasMore(false)
      } finally {
        if (!abortController.signal.aborted) {
          setContestsLoading(false)
          setInitialLoadComplete(true)
        }
      }
    }

    fetchContestsForRound()

    return () => {
      abortController.abort()
    }
    // isAuthenticated/user removed: prevents race condition where auth resolve
    // aborts in-flight request. userIdRef handles cache key without re-triggering.
  }, [activeRoundId, categoryTab, filterCountry, filterContinent, committedSearch])

  // Load more contests function
  const loadMoreContests = useCallback(async () => {
    if (loadingMore || !hasMore || !activeRoundId) return

    setLoadingMore(true)
    const contestMode = categoryTab === 'nomination' ? 'nomination' : categoryTab === 'participations' ? 'participation' : undefined
    const activeCountry = (filterCountry && filterCountry !== 'all') ? filterCountry : undefined
    const activeContinent = filterContinent !== 'all' ? filterContinent : undefined
    const activeSearch = committedSearch || undefined

    try {
      const data = await ApiService.getRounds({
        roundId: parseInt(activeRoundId),
        contestMode,
        filterCountry: activeCountry,
        filterContinent: activeContinent,
        searchTerm: activeSearch,
        contestLimit: CONTESTS_PER_PAGE,
        contestSkip: allContests.length  // Skip already loaded contests
      })

      if (data && data.length > 0 && data[0].contests) {
        const newContests = data[0].contests
        const totalCount = data[0].contests_count || 0
        // Append new contests and re-sort entire list by participants (descending)
        setAllContests(prev => {
          const combined = [...prev, ...newContests]
          // Sort by participants_count descending (most participants first)
          combined.sort((a, b) => {
            const aCount = Number(a.participants_count) || 0
            const bCount = Number(b.participants_count) || 0
            return bCount - aCount
          })
          // Check if there are more by comparing total loaded vs total count
          setHasMore(combined.length < totalCount)
          return combined
        })
      } else {
        setHasMore(false)
      }
    } catch (error: any) {
      logger.error('Failed to load more contests:', error)
      // Handle API errors gracefully
      if (error?.response?.status === 404 || error?.response?.status === 500 || error?.response?.status === 503) {
        logger.warn('Backend unavailable, stopping pagination')
        setHasMore(false) // Stop trying to load more
      }
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

  // Cache API_BASE_URL to avoid repeated lookups
  const API_BASE_URL = useMemo(() => process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000', [])

  // Raw Contests List (Before filtering by type) - Now uses allContests for infinite scroll
  const rawContests = useMemo(() => {
    if (!allContests || allContests.length === 0) return []

    return allContests.map((c: any) => {
      // Stats are now directly on the contest object in the new schema
      // Fallback multiple pour l'image
      // Use emoji as fallback instead of missing placeholder.png
      const rawImage = c.cover_image_url || c.image_url || '💎'

      const isEmoji = rawImage?.length <= 4 && rawImage?.codePointAt(0) > 0x1F000
      let coverImage = rawImage

      if (!isEmoji && coverImage && !coverImage.startsWith('http') && !coverImage.startsWith('data:') && !coverImage.startsWith('/')) {
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
        currentUserParticipated: Boolean(c.currentUserParticipated || c.current_user_participated || c.current_user_contesting),
        // Explicitly check for true value - default to false if undefined/null
        currentUserContesting: Boolean(c.currentUserContesting === true || c.current_user_contesting === true),
        topContestants: [] // Not fetching top contestants per contest in new query yet
      }
    })

    // Removed debug logs for performance
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

    // 4. Always sort - ensure consistent ordering
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'participants':
          // Sort by participants (descending - most first)
          const aContestants = Number(a.contestants) || 0
          const bContestants = Number(b.contestants) || 0
          if (bContestants !== aContestants) {
            return bContestants - aContestants
          }
          // Secondary sort by votes if participants are equal
          return (Number(b.received) || 0) - (Number(a.received) || 0)
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
          // Default: sort by participants (descending - most first)
          const aContestantsDefault = Number(a.contestants) || 0
          const bContestantsDefault = Number(b.contestants) || 0
          if (bContestantsDefault !== aContestantsDefault) {
            return bContestantsDefault - aContestantsDefault
          }
          return (Number(b.received) || 0) - (Number(a.received) || 0)
      }
    })

    return filtered
  }, [rawContests, activeTab, committedSearch, sortBy, categoryTab, filterLevel])

  // Déterminer si le round actif est fermé (soumissions terminées)
  const activeRoundData = rounds.find((r: any) => String(r.id) === activeRoundId)
  const isRoundClosed = activeRoundData ? new Date(activeRoundData.submission_end_date + 'T23:59:59') < new Date() : false

  const handleParticipate = (id: string, isEditing: boolean, roundId: string | null) => {
    const params = new URLSearchParams()
    if (isEditing) params.set('edit', 'true')
    if (roundId) params.set('roundId', roundId)
    // Passer le type d'entrée selon l'onglet actif
    const entryType = categoryTab === 'nomination' ? 'nomination' : 'participation'
    params.set('entryType', entryType)
    const q = params.toString()
    router.push(`/dashboard/contests/${id}/apply${q ? `?${q}` : ''}`)
  }

  // Show skeleton only if we have no data at all
  if (isLoading || (roundsLoading && rounds.length === 0 && !allContests.length)) {
    return <ContestsSkeleton />
  }
  // Allow unauthenticated users to view contests (they just can't participate)

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Header & Suggest Button */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">{t('dashboard.contests.title') || 'Contests'}</h1>
            <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t('dashboard.contests.subtitle') || 'Discover and participate in contests'}</p>
          </div>
          <Button onClick={() => setShowSuggestDialog(true)} className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20">
            <Lightbulb className="w-4 h-4 mr-2" /> {t('dashboard.contests.suggest_contest.button') || 'Suggest'}
          </Button>
        </div>

        {/* Round Selector (Top Tabs) */}
        <div className="mb-6">
          <div className="flex space-x-2 overflow-x-auto pb-2 scrollbar-hide">
            {rounds.map((round: any) => (
              <button
                key={round.id}
                onClick={() => setActiveRoundId(String(round.id))}
                className={`px-5 py-2.5 rounded-full text-sm font-medium transition-all duration-200 whitespace-nowrap ${activeRoundId === String(round.id)
                  ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg shadow-blue-500/30 scale-105'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:bg-gray-800/80 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-white hover:scale-[1.02]'
                  }`}
              >
                {(() => {
                  const isPast = new Date(round.submission_end_date + 'T23:59:59') < new Date()
                  return (
                    <>
                      {isPast && <Lock className="w-3 h-3 mr-1 inline opacity-60" />}
                      {round.name} <span className="ml-1 opacity-70">({round.contests_count !== undefined ? round.contests_count : (round.contests?.length || 0)})</span>
                    </>
                  )
                })()}
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
            showCountryFilter={true}
            className="mb-4"
          />

          {/* Level Filter for Participations */}
          {categoryTab === 'participations' && (
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-gray-400 dark:text-gray-500" />
              <span className="text-sm text-gray-500 mr-1">{t('dashboard.contests.filter_level') || 'Level'}:</span>
              {[
                { value: 'city', label: t('dashboard.contests.level_city') || 'City' },
                { value: 'country', label: t('dashboard.contests.level_country') || 'Country' },
                { value: 'all', label: t('dashboard.contests.all_levels') || 'All' },
              ].map((level) => (
                <button
                  key={level.value}
                  onClick={() => setFilterLevel(level.value)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                    filterLevel === level.value
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:bg-gray-800/60 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  {level.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Main Category Tabs (Nomination / Participations) */}
        <div className="mb-6 border-b border-gray-200 dark:border-gray-800">
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
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${categoryTab === 'nomination' ? 'border-blue-500 text-blue-600 dark:text-blue-400 bg-blue-500/5' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}`}
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
                setFilterLevel('all'); // Default to all levels for participations
              }}
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${categoryTab === 'participations' ? 'border-blue-500 text-blue-600 dark:text-blue-400 bg-blue-500/5' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}`}
            >
              {t('dashboard.contests.participations') || 'Participations'}
            </button>
          </div>
        </div>

        {/* Type Tabs (Generated from ALL contests in round) */}
        {contestTypes.length > 1 && (
          <div className="mb-8 border-b border-gray-200 dark:border-gray-800">
            <div className="flex space-x-6 overflow-x-auto scrollbar-hide">
              {contestTypes.map((type) => (
                <button
                  key={type.id}
                  onClick={() => setActiveTab(type.id || 'all')}
                  className={`pb-4 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${activeTab === (type.id || 'all')
                    ? 'border-blue-500 text-blue-500'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300 dark:hover:border-gray-700'
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
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 gap-6">
              {displayedContests.map((contest: any) => (
                <ContestCard
                  key={contest.id}
                  {...contest}
                  canParticipate={!filterCountry || filterCountry === 'all' || filterCountry === '' || (!!user?.country && filterCountry.toLowerCase() === user.country.toLowerCase())}
                  isKycVerified={!!user?.identity_verified}
                  isFavorite={false}
                  isNomination={categoryTab === 'nomination'}
                  contest_mode={contest.contest_mode}
                  currentUserContesting={(categoryTab === 'nomination' ? contest.currentUserParticipated : contest.currentUserContesting) || false}
                  onToggleFavorite={() => { }}
                  isRoundClosed={isRoundClosed}
                  onParticipate={() => handleParticipate(contest.id, (categoryTab === 'nomination' ? contest.currentUserParticipated : contest.currentUserContesting) || false, activeRoundId)}
                  onViewContestants={() => {
                    const params = new URLSearchParams()
                    if (filterCountry && filterCountry !== 'all') params.set('country', filterCountry)
                    params.set('continent', filterContinent !== 'all' ? filterContinent : 'all')
                    params.set('entryType', categoryTab === 'nomination' ? 'nomination' : 'participation')
                    const q = params.toString()
                    router.push(`/dashboard/contests/${contest.id}${q ? `?${q}` : ''}`)
                  }}
                  onOpenDetails={() => {
                    const params = new URLSearchParams()
                    if (filterCountry && filterCountry !== 'all') params.set('country', filterCountry)
                    params.set('continent', filterContinent !== 'all' ? filterContinent : 'all')
                    params.set('entryType', categoryTab === 'nomination' ? 'nomination' : 'participation')
                    const q = params.toString()
                    router.push(`/dashboard/contests/${contest.id}${q ? `?${q}` : ''}`)
                  }}
                />
              ))}
            </div>

            {/* Infinite scroll loader */}
            <div ref={loaderRef} className="flex justify-center py-8">
              {loadingMore && (
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Chargement...</span>
                </div>
              )}
              {!hasMore && allContests.length > 0 && (
                <span className="text-gray-500 dark:text-gray-400">
                  {t('admin.contests.all_loaded') || `${totalContests} concours affichés`}
                </span>
              )}
            </div>
          </>
        ) : !initialLoadComplete ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            <p className="text-gray-500 dark:text-gray-400">{t('common.loading') || 'Loading...'}</p>
          </div>
        ) : (
          <div className="text-center py-20">
            <p className="text-gray-500 dark:text-gray-400">{t('contests.no_contests') || 'Aucun concours trouvé correspondant aux critères.'}</p>
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
