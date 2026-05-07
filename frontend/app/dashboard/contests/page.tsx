'use client'

import * as React from "react"
import { useState, useEffect, useMemo, Suspense, useRef, useCallback } from "react"
import dynamic from 'next/dynamic'
import Image from 'next/image'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useSearchParams } from 'next/navigation'
import { useToast } from '@/components/ui/toast'
import { ContestsSkeleton } from '@/components/ui/skeleton'
import { Lightbulb, Loader2, MapPin, Lock } from 'lucide-react'
import { GeographyLevelIcon, type GeographyLevelIconKey } from '@/components/dashboard/geography-level-icons'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { logger } from '@/lib/logger'
import { LocationFilterBar } from '@/components/dashboard/location-filter-bar'
import { getEffectiveApiUrl } from '@/lib/config'

// GraphQL
// REST API
import ApiService, { Round } from '@/lib/api-service'
import { isRoundVotingLive } from '@/lib/is-round-voting-live'

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

type NominationMigrationLevel = 'all' | 'city' | 'country' | 'regional' | 'continental' | 'global'

function normalizeContestLevel(level?: string): Exclude<NominationMigrationLevel, 'all'> | null {
  if (!level) return null
  const raw = String(level).trim().toLowerCase()
  if (raw === 'city') return 'city'
  if (raw === 'country') return 'country'
  if (raw === 'regional' || raw === 'region') return 'regional'
  if (raw === 'continental' || raw === 'continent') return 'continental'
  if (raw === 'global') return 'global'
  return null
}

const REGIONAL_POOL_BY_COUNTRY: Record<string, string> = {
  tanzania: 'East Africa',
  tz: 'East Africa',
  kenya: 'East Africa',
  ke: 'East Africa',
  uganda: 'East Africa',
  ug: 'East Africa',
  rwanda: 'East Africa',
  rw: 'East Africa',
  burundi: 'East Africa',
  bi: 'East Africa',
  ethiopia: 'East Africa',
  et: 'East Africa',
  somalia: 'East Africa',
  so: 'East Africa',
  eritrea: 'East Africa',
  er: 'East Africa',
  djibouti: 'East Africa',
  dj: 'East Africa',
  'south sudan': 'East Africa',
  ss: 'East Africa',
  sudan: 'East Africa',
  sd: 'East Africa',
  nigeria: 'West Africa',
  ng: 'West Africa',
  ghana: 'West Africa',
  gh: 'West Africa',
  senegal: 'West Africa',
  sn: 'West Africa',
  'ivory coast': 'West Africa',
  "cote d'ivoire": 'West Africa',
  "côte d'ivoire": 'West Africa',
  ci: 'West Africa',
  'south africa': 'Southern Africa',
  za: 'Southern Africa',
  zimbabwe: 'Southern Africa',
  zw: 'Southern Africa',
  zambia: 'Southern Africa',
  zm: 'Southern Africa',
  botswana: 'Southern Africa',
  bw: 'Southern Africa',
  namibia: 'Southern Africa',
  na: 'Southern Africa',
  mozambique: 'Southern Africa',
  mz: 'Southern Africa',
  malawi: 'Southern Africa',
  mw: 'Southern Africa',
  angola: 'Southern Africa',
  ao: 'Southern Africa',
  egypt: 'North Africa',
  eg: 'North Africa',
  morocco: 'North Africa',
  ma: 'North Africa',
  algeria: 'North Africa',
  dz: 'North Africa',
  tunisia: 'North Africa',
  tn: 'North Africa',
  libya: 'North Africa',
  ly: 'North Africa',
  cameroon: 'Central Africa',
  cm: 'Central Africa',
  'democratic republic of the congo': 'Central Africa',
  drc: 'Central Africa',
  cd: 'Central Africa',
  'republic of the congo': 'Central Africa',
  cg: 'Central Africa',
  gabon: 'Central Africa',
  ga: 'Central Africa',
  chad: 'Central Africa',
  td: 'Central Africa',
}

function regionalPoolForCountry(country?: string | null): string | undefined {
  const key = country?.trim().toLowerCase()
  return key ? REGIONAL_POOL_BY_COUNTRY[key] : undefined
}

type RoundTabKind = 'nominate' | 'vote' | 'combined'

/** Only the current nomination month + the live voting round (hide Jan/Feb/March clutter). */
function computeDisplayRounds(rounds: Round[]): Array<{ round: Round; pill: string; kind: RoundTabKind }> {
  if (!rounds?.length) return []
  const voteRound = rounds.find((r: any) => isRoundVotingLive(r, rounds))
  const now = new Date()
  const currentMonthStr = now.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }).toLowerCase()
  const nominationRound =
    rounds.find((r: any) => String(r.name || '').toLowerCase().includes(currentMonthStr)) || rounds[0]
  if (nominationRound && voteRound && Number((nominationRound as any).id) === Number((voteRound as any).id)) {
    return [{ round: nominationRound, pill: 'Submit & Vote', kind: 'combined' }]
  }
  const out: Array<{ round: Round; pill: string; kind: RoundTabKind }> = []
  const seen = new Set<number>()
  const push = (r: Round | undefined | null, pill: string, kind: RoundTabKind) => {
    if (!r) return
    const id = Number((r as any).id)
    if (Number.isNaN(id) || seen.has(id)) return
    seen.add(id)
    out.push({ round: r, pill, kind })
  }
  push(nominationRound, 'Submit', 'nominate')
  push(voteRound as Round | undefined, 'Vote', 'vote')
  return out.length
    ? out
    : rounds.map((r) => ({
        round: r,
        pill: isRoundVotingLive(r, rounds) ? 'Vote' : 'Submit',
        kind: (isRoundVotingLive(r, rounds) ? 'vote' : 'nominate') as RoundTabKind,
      }))
}

function ContestsPageContent() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { addToast } = useToast()

  // State
  const [activeRoundId, setActiveRoundId] = useState<string | null>(null)
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
  const [filterRegion, setFilterRegion] = useState<string>(() => {
    const urlRegion = searchParams.get('region')
    return urlRegion || ''
  })
  const [filterLevel, setFilterLevel] = useState<string>('all') // Level filter for participations: 'city', 'country', 'all'
  const [nominationMigrationLevel, setNominationMigrationLevel] = useState<NominationMigrationLevel>('all')

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
  const voteNowRoundId = useMemo(() => {
    const voteRound = rounds.find((r: any) => isRoundVotingLive(r, rounds))
    return voteRound ? String(voteRound.id) : null
  }, [rounds])
  const displayRounds = useMemo(() => computeDisplayRounds(rounds), [rounds])
  /**
   * Show Country / Regional / … chips when the user is in a voting-round context.
   * Use several signals — frontend pill `kind`, API live-vote id, and `isRoundVotingLive` on the active row —
   * so levels still appear if one of them drifts out of sync.
   */
  const showVoteGeographyLevels = useMemo(() => {
    if (!activeRoundId || !rounds.length) return false
    const entryIdx = displayRounds.findIndex((d) => String(d.round.id) === activeRoundId)
    const entry = entryIdx >= 0 ? displayRounds[entryIdx] : undefined
    if (entry?.kind === 'vote' || entry?.kind === 'combined') return true
    // Two top pills are always [current nomination month, live vote round]; index > 0 is the Vote round.
    if (displayRounds.length >= 2 && entryIdx > 0) return true
    if (voteNowRoundId && activeRoundId === voteNowRoundId) return true
    // Never infer "voting context" from dates alone when this row is the Nominate-month pill.
    if (entry?.kind === 'nominate') return false
    const activeRound = rounds.find((r: any) => String(r.id) === activeRoundId)
    if (activeRound && isRoundVotingLive(activeRound as any, rounds)) return true
    return false
  }, [displayRounds, activeRoundId, rounds, voteNowRoundId])

  const nominationStageOptions = useMemo(() => {
    const allStages: Array<{
      value: Exclude<NominationMigrationLevel, 'all'>
      label: string
      icon: GeographyLevelIconKey
    }> = [
      { value: 'country', label: t('dashboard.contests.country'), icon: 'country' },
      { value: 'regional', label: t('dashboard.contests.regional'), icon: 'regional' },
      // City omitted: vote-round Nominate tab only (participations still has City).
      { value: 'continental', label: t('dashboard.contests.continental'), icon: 'continent' },
      { value: 'global', label: t('dashboard.contests.global'), icon: 'global' },
    ]
    return allStages
  }, [t])

  const participationLevelOptions = useMemo(() => {
    type Opt = { value: string; label: string; icon: GeographyLevelIconKey }
    const full: Opt[] = [
      { value: 'country', label: t('dashboard.contests.country') || 'Country', icon: 'country' },
      { value: 'regional', label: t('dashboard.contests.regional') || 'Regional', icon: 'regional' },
      { value: 'city', label: t('dashboard.contests.level_city') || 'City', icon: 'city' },
      { value: 'continental', label: t('dashboard.contests.continental') || 'Continental', icon: 'continent' },
      { value: 'global', label: t('dashboard.contests.global') || 'Global', icon: 'global' },
    ]
    const slim: Opt[] = [
      { value: 'country', label: t('dashboard.contests.country') || 'Country', icon: 'country' },
      { value: 'regional', label: t('dashboard.contests.regional') || 'Regional', icon: 'regional' },
    ]
    return showVoteGeographyLevels ? full : slim
  }, [showVoteGeographyLevels, t])

  useEffect(() => {
    if (!showVoteGeographyLevels && ['regional', 'continental', 'global'].includes(nominationMigrationLevel)) {
      setNominationMigrationLevel('all')
    }
  }, [showVoteGeographyLevels, nominationMigrationLevel])

  useEffect(() => {
    if (showVoteGeographyLevels && nominationMigrationLevel === 'city') {
      setNominationMigrationLevel('all')
    }
  }, [showVoteGeographyLevels, nominationMigrationLevel])

  useEffect(() => {
    if (categoryTab !== 'participations' || showVoteGeographyLevels) return
    if (['country', 'continental', 'global'].includes(filterLevel)) {
      setFilterLevel('all')
    }
  }, [categoryTab, filterLevel, showVoteGeographyLevels])

  useEffect(() => {
    if (!rounds.length) return
    const dr = computeDisplayRounds(rounds)
    const allowed = new Set(dr.map((d) => String(d.round.id)))
    setActiveRoundId((prev) => {
      if (prev && allowed.has(prev)) return prev
      return String(dr[0].round.id)
    })
  }, [rounds])

  const effectiveRoundIdForFetch = useMemo(() => {
    if (!activeRoundId) return null
    if (categoryTab !== 'nomination') return activeRoundId
    const offsetByStage: Partial<Record<NominationMigrationLevel, number>> = {
      regional: 1,
      continental: 2,
      global: 3,
    }
    const offset = offsetByStage[nominationMigrationLevel]
    if (!offset) return activeRoundId
    const idx = rounds.findIndex((r: any) => String(r.id) === activeRoundId)
    if (idx < 0) return activeRoundId
    const target = rounds[idx + offset]
    return target ? String(target.id) : activeRoundId
  }, [activeRoundId, categoryTab, nominationMigrationLevel, rounds])

  /** Round id sent to contest detail / apply (must match API round scoped to migration data). */
  const roundIdNav = effectiveRoundIdForFetch ?? activeRoundId

  // 1. Fetch Rounds for Selector (allow unauthenticated users) - Optimized for speed
  useEffect(() => {
    const abortController = new AbortController()
    
    const fetchRounds = async () => {
      try {
        setRoundsLoading(true)
        // Fetch rounds with minimal data for faster response
        const data = await ApiService.getRounds({ contestLimit: 1, limit: 12 }) // Minimal data for round selector
        
        // Check if aborted
        if (abortController.signal.aborted) return
        
        setRounds(data)
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
    if (filterRegion && nominationMigrationLevel === 'regional') {
      params.set('region', filterRegion)
      params.delete('country')
    } else {
      params.delete('region')
    }
    if (filterCountry && filterCountry !== 'all' && nominationMigrationLevel !== 'regional') {
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
  }, [filterCountry, filterRegion, filterContinent, nominationMigrationLevel, searchParams])

  useEffect(() => {
    if (categoryTab !== 'nomination' || nominationMigrationLevel !== 'regional') return
    const nextRegion = regionalPoolForCountry(filterCountry) || (user as any)?.region || regionalPoolForCountry(user?.country)
    if (nextRegion && filterRegion !== nextRegion) {
      setFilterRegion(nextRegion)
    }
    if (filterCountry) {
      setFilterCountry('')
    }
  }, [categoryTab, nominationMigrationLevel, filterCountry, filterRegion, user?.country, (user as any)?.region])

  // Regional nomination voting must stay on the current "VOTE NOW" round.
  useEffect(() => {
    if (categoryTab !== 'nomination') return
    if (!['regional', 'continental', 'global'].includes(nominationMigrationLevel)) return
    if (!voteNowRoundId) return
    if (activeRoundId === voteNowRoundId) return
    setActiveRoundId(voteNowRoundId)
  }, [categoryTab, nominationMigrationLevel, voteNowRoundId, activeRoundId])

  // Set default filters based on category tab and user location (only when no filter is set yet)
  useEffect(() => {
    if (!user) return

    if (categoryTab === 'nomination') {
      // Set user's country for nominations only if no country already set (from URL or manual selection)
      if (user.country && !filterCountry && !filterRegion) {
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
  }, [categoryTab, user?.country, filterRegion])

  // Handle Search Execution
  const handleSearch = () => {
    setCommittedSearch(searchTerm)
  }

  // Reset pagination when filters change
  useEffect(() => {
    setAllContests([])
    setHasMore(true)
    setInitialLoadComplete(false)
  }, [activeRoundId, effectiveRoundIdForFetch, categoryTab, filterCountry, filterRegion, filterContinent, nominationMigrationLevel, committedSearch])

  // 2. Fetch Contests for Selected Round (Initial load) - allow unauthenticated users
  // Use a ref to track current user id without triggering re-fetches
  const userIdRef = useRef<number | null>(null)
  useEffect(() => {
    userIdRef.current = user?.id ?? null
  }, [user?.id])

  useEffect(() => {
    if (!activeRoundId || !effectiveRoundIdForFetch) return

    // AbortController for request cancellation
    const abortController = new AbortController()

    const fetchContestsForRound = async () => {
      setContestsLoading(true)
      const contestMode = categoryTab === 'nomination' ? 'nomination' : categoryTab === 'participations' ? 'participation' : undefined
      const activeCountry = (filterCountry && filterCountry !== 'all') ? filterCountry : undefined
      const activeRegion = (filterRegion && nominationMigrationLevel === 'regional') ? filterRegion : undefined
      const activeContinent = (filterContinent && filterContinent !== 'all') ? filterContinent : undefined
      const activeSearch = committedSearch || undefined

      // Check cache first
      const authKey = userIdRef.current || 'anon'
      const cacheKey = getCacheKey(effectiveRoundIdForFetch, categoryTab, activeCountry || activeRegion || 'all', activeContinent || 'all', activeSearch || '', 0, authKey)
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
          roundId: parseInt(effectiveRoundIdForFetch),
          contestMode,
          filterCountry: activeRegion ? undefined : activeCountry,
          filterRegion: activeRegion,
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
              roundId: parseInt(effectiveRoundIdForFetch),
              contestMode,
              filterCountry: activeRegion ? undefined : activeCountry,
              filterRegion: activeRegion,
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
  }, [activeRoundId, effectiveRoundIdForFetch, categoryTab, filterCountry, filterRegion, filterContinent, nominationMigrationLevel, committedSearch])

  // Load more contests function
  const loadMoreContests = useCallback(async () => {
    if (loadingMore || !hasMore || !activeRoundId || !effectiveRoundIdForFetch) return

    setLoadingMore(true)
    const contestMode = categoryTab === 'nomination' ? 'nomination' : categoryTab === 'participations' ? 'participation' : undefined
    const activeCountry = (filterCountry && filterCountry !== 'all') ? filterCountry : undefined
    const activeRegion = (filterRegion && nominationMigrationLevel === 'regional') ? filterRegion : undefined
    const activeContinent = filterContinent !== 'all' ? filterContinent : undefined
    const activeSearch = committedSearch || undefined

    try {
      const data = await ApiService.getRounds({
        roundId: parseInt(effectiveRoundIdForFetch),
        contestMode,
        filterCountry: activeRegion ? undefined : activeCountry,
        filterRegion: activeRegion,
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
  }, [loadingMore, hasMore, activeRoundId, effectiveRoundIdForFetch, categoryTab, filterCountry, filterRegion, filterContinent, nominationMigrationLevel, committedSearch, allContests.length])

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
  const API_BASE_URL = useMemo(() => getEffectiveApiUrl(), [])

  // Canonical: opening a pooled REGIONAL/+ contest must not attach ?country= from the grid,
  // or the detail API filters to Tanzania-only while the card count shows full East Africa pool.
  const shouldPassCountryNavParam = React.useCallback(
    (contestStatus: unknown) => {
      const s = String(contestStatus ?? '').toLowerCase()
      if (['regional', 'continent', 'continental', 'global'].includes(s)) return false
      if (categoryTab === 'nomination') {
        const explicit =
          !!(filterCountry && filterCountry !== 'all' && filterCountry !== '')
        return explicit || !!user?.country
      }
      return !!(filterCountry && filterCountry !== 'all' && filterCountry !== '')
    },
    [filterCountry, user?.country, categoryTab]
  )

  // Keep contest detail filters aligned with current list filters
  // so card participants_count and detail list show the same population.
  const buildContestNavParams = React.useCallback(
    (contestStatus: unknown) => {
      const params = new URLSearchParams()
      if (roundIdNav) params.set('roundId', String(roundIdNav))

      const level = normalizeContestLevel(String(contestStatus ?? ''))
      const region = filterRegion || regionalPoolForCountry(filterCountry) || regionalPoolForCountry(user?.country)
      if (level === 'regional') {
        if (region) params.set('region', region)
      } else if (shouldPassCountryNavParam(contestStatus)) {
        const countryValue =
          categoryTab === 'nomination'
            ? (filterCountry && filterCountry !== 'all' && filterCountry !== '' ? filterCountry : (user?.country || ''))
            : (filterCountry || '')
        if (countryValue && countryValue !== 'all') params.set('country', countryValue)
      }

      if (filterContinent && filterContinent !== 'all') {
        params.set('continent', filterContinent)
      }
      params.set('entryType', categoryTab === 'nomination' ? 'nomination' : 'participation')
      return params
    },
    [roundIdNav, filterRegion, filterCountry, user?.country, shouldPassCountryNavParam, filterContinent, categoryTab]
  )

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
        contestants: Number(c.participants_count ?? c.entries_count ?? 0),
        isOpen: contestsData?.is_submission_open || contestsData?.is_voting_open || false,
        contestType: c.contest_type,
        isSubmissionOpen: contestsData?.is_submission_open,
        isVotingOpen: contestsData?.is_voting_open,
        // Pass dates for countdown in ContestCard
        participationStartDate: contestsData?.submission_start_date,
        participationEndDate: contestsData?.submission_end_date,
        votingStartDate: contestsData?.voting_start_date,
        votingEndDate: contestsData?.voting_end_date,
        // Contest-level flags only. Do not mix with round-level "current_user_participated"
        // to avoid showing Edit on contests/categories where user has no submission.
        currentUserParticipated: Boolean(c.currentUserParticipated === true || c.current_user_participated === true),
        currentUserContesting: Boolean(c.currentUserContesting === true || c.current_user_contesting === true),
        topContestants: [] // Not fetching top contestants per contest in new query yet
      }
    })

    // Removed debug logs for performance
  }, [allContests, contestsData])

  // Filter and Sort Contests for Display
  const displayedContests = useMemo(() => {
    let filtered = rawContests.slice()

    // 1. Filter by Search
    if (committedSearch) {
      const lower = committedSearch.toLowerCase()
      filtered = filtered.filter(c => c.title.toLowerCase().includes(lower))
    }

    // 2. Filter by Level (for participations tab)
    if (categoryTab === 'participations' && filterLevel !== 'all') {
      const want = filterLevel as Exclude<NominationMigrationLevel, 'all'>
      filtered = filtered.filter((c) => normalizeContestLevel(c.status) === want)
    }

    // 3. Filter by migration stage (for nominations tab)
    if (categoryTab === 'nomination' && nominationMigrationLevel !== 'all') {
      filtered = filtered.filter((c) => normalizeContestLevel(c.status) === nominationMigrationLevel)
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
  }, [rawContests, committedSearch, sortBy, categoryTab, filterLevel, nominationMigrationLevel])

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
            {displayRounds.map(({ round, pill, kind }) => {
              const isPast = new Date(round.submission_end_date + 'T23:59:59') < new Date()
              const showLock = isPast && kind === 'vote'
              const iconVote = (
                <Image
                  src="/contests/vote-tab-icon.png?v=2"
                  alt=""
                  width={28}
                  height={28}
                  className="h-7 w-7 object-contain flex-shrink-0 rounded-md"
                />
              )

              // Submit tab icon (provided by you).
              const iconNominateForSubmit = (
                <Image
                  src="/contests/submit-tab-icon.png?v=2"
                  alt=""
                  width={28}
                  height={28}
                  className="h-7 w-7 object-contain flex-shrink-0 rounded-md"
                />
              )
              return (
                <button
                  key={round.id}
                  onClick={() => setActiveRoundId(String(round.id))}
                  className={`px-5 py-2.5 rounded-full text-sm font-medium transition-all duration-200 whitespace-nowrap flex flex-row items-center justify-center gap-2 min-h-[3rem] ${activeRoundId === String(round.id)
                    ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg shadow-blue-500/30 scale-105'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:bg-gray-800/80 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-white hover:scale-[1.02]'
                    }`}
                >
                  {showLock && <Lock className="w-4 h-4 opacity-80 flex-shrink-0" aria-hidden />}
                  {kind === 'combined' ? (
                    <span className="inline-flex items-center gap-1">
                      {iconNominateForSubmit}
                      {iconVote}
                    </span>
                  ) : kind === 'vote' ? (
                    iconVote
                  ) : (
                    iconNominateForSubmit
                  )}
                  <span className="font-semibold leading-tight">
                    {pill ||
                      (isRoundVotingLive(round, rounds) ? (t('dashboard.contests.vote_now_short') || 'Vote') : '')}
                  </span>
                </button>
              )
            })}
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
        </div>

        {/* Main Category Tabs (Nomination / Participations) */}
        <div className="mb-6 border-b border-gray-200 dark:border-gray-800">
          <div className="flex space-x-1">
            <button
              onClick={() => {
                setCategoryTab('nomination');
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
                setNominationMigrationLevel('all');
              }}
              className={`inline-flex items-center gap-2 px-6 py-3 text-base font-semibold transition-colors border-b-2 ${categoryTab === 'nomination' ? 'border-blue-500 text-blue-600 dark:text-blue-400 bg-blue-500/5' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}`}
            >
              <Image
                src="/contests/submit-tab-icon.png?v=2"
                alt=""
                width={22}
                height={22}
                className="h-[22px] w-[22px] object-contain"
              />
              {t('dashboard.contests.nominate_tab') || 'Nominate'}
            </button>
            <button
              onClick={() => {
                setCategoryTab('participations');
                setSearchTerm('');
                setCommittedSearch('');
                setFilterCountry(''); // Reset country filter for participations
                setFilterContinent('all');
                setFilterLevel('all'); // Default to all levels for participations
                setNominationMigrationLevel('all');
              }}
              className={`inline-flex items-center gap-2 px-6 py-3 text-base font-semibold transition-colors border-b-2 ${categoryTab === 'participations' ? 'border-blue-500 text-blue-600 dark:text-blue-400 bg-blue-500/5' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}`}
            >
              <Image
                src="/contests/submit-tab-icon.png?v=2"
                alt=""
                width={22}
                height={22}
                className="h-[22px] w-[22px] object-contain"
              />
              {t('dashboard.contests.participations') || 'Participations'}
            </button>
          </div>
        </div>

        {/* Level filters directly under tabs: Vote / Nominate & Vote rounds show Country, Regional, … on Nominate; Participations uses same when voting round selected */}
        {categoryTab === 'participations' && (
          <div className="mb-6 flex items-center gap-2 flex-wrap">
            <MapPin className="w-4 h-4 text-gray-400 dark:text-gray-500" />
            <span className="text-sm text-gray-500 mr-1">{t('dashboard.contests.filter_level') || 'Level'}:</span>
            {participationLevelOptions.map((level) => (
              <button
                key={level.value}
                type="button"
                onClick={() => setFilterLevel(level.value)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  filterLevel === level.value
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:bg-gray-800/60 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-300'
                }`}
              >
                <GeographyLevelIcon level={level.icon} size={22} />
                {level.label}
              </button>
            ))}
          </div>
        )}

        {categoryTab === 'nomination' && showVoteGeographyLevels && (
          <div className="mb-6 flex items-center gap-2 flex-wrap">
            <MapPin className="w-4 h-4 text-gray-400 dark:text-gray-500" />
            <span className="text-sm text-gray-500 mr-1">{t('dashboard.contests.filter_level') || 'Level'}:</span>
            {nominationStageOptions.map((stage) => (
              <button
                key={stage.value}
                type="button"
                onClick={() => setNominationMigrationLevel(stage.value)}
                className={`inline-flex flex-col items-center gap-0.5 px-2.5 py-1.5 rounded-2xl text-[11px] font-semibold transition-all min-w-[3.25rem] ${
                  nominationMigrationLevel === stage.value
                    ? 'bg-blue-600 text-white shadow-sm ring-2 ring-blue-400/60 ring-offset-1 ring-offset-white dark:ring-offset-gray-900'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:bg-gray-800/60 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-300'
                }`}
              >
                <GeographyLevelIcon level={stage.icon} size={28} />
                <span className="leading-tight text-center max-w-[4.5rem]">{stage.label}</span>
              </button>
            ))}
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
                  currentUserContesting={(categoryTab === 'nomination' ? contest.currentUserContesting : contest.currentUserParticipated) || false}
                  onToggleFavorite={() => { }}
                  isRoundClosed={isRoundClosed}
                  onParticipate={() =>
                    handleParticipate(
                      contest.id,
                      (categoryTab === 'nomination' ? contest.currentUserContesting : contest.currentUserParticipated) || false,
                      roundIdNav
                    )
                  }
                  onViewContestants={() => {
                    const params = buildContestNavParams(contest.status)
                    const q = params.toString()
                    router.push(`/dashboard/contests/${contest.id}${q ? `?${q}` : ''}`)
                  }}
                  onOpenDetails={() => {
                    const params = buildContestNavParams(contest.status)
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
                  <span>{t('dashboard.contests.loading_more')}</span>
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
            <p className="text-gray-500 dark:text-gray-400">
              {categoryTab === 'nomination'
                ? nominationMigrationLevel === 'city'
                  ? t('dashboard.contests.no_nominated_yet')
                  : nominationMigrationLevel === 'regional'
                    ? t('dashboard.contests.no_regional_migration')
                    : nominationMigrationLevel === 'continental'
                      ? t('dashboard.contests.no_continental_migration')
                      : nominationMigrationLevel === 'global'
                        ? t('dashboard.contests.no_global_migration')
                        : nominationMigrationLevel === 'country'
                          ? t('dashboard.contests.no_country_migration')
                          : t('dashboard.contests.no_nomination_contests')
                : t('contests.no_contests')}
            </p>
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
