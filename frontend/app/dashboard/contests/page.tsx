'use client'

import * as React from "react"
import { useState, useEffect, useMemo, Suspense } from "react"
import dynamic from 'next/dynamic'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useSearchParams } from 'next/navigation'
import { useToast } from '@/components/ui/toast'
import { ContestsSkeleton } from '@/components/ui/skeleton'
import { Lightbulb } from 'lucide-react'
import { Button } from '@/components/ui/button'
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

  // Data States
  const [rounds, setRounds] = useState<Round[]>([])
  const [roundsLoading, setRoundsLoading] = useState(true)
  const [contestsData, setContestsData] = useState<Round | null>(null)
  const [contestsLoading, setContestsLoading] = useState(false)

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

  // Handle Search Execution
  const handleSearch = () => {
    setCommittedSearch(searchTerm)
  }

  // 2. Fetch Contests for Selected Round (Fetch ALL types to populate tabs correctly)
  useEffect(() => {
    if (!activeRoundId || !isAuthenticated) return

    const fetchContestsForRound = async () => {
      setContestsLoading(true)
      const hasVotingType = categoryTab === 'nomination'
      const activeCountry = filterCountry !== 'all' ? filterCountry : undefined
      const activeContinent = filterContinent !== 'all' ? filterContinent : undefined
      const activeSearch = committedSearch || undefined

      try {
        // We reuse getRounds but ideally we should have a more specific endpoint 
        // to get a single round with contests or get contests filtered by round.
        // Currently getRounds returns a list.
        // Based on previous GraphQL usage, it was getting rounds filtered by ID.
        // Let's assume getRounds can handle the ID or we filter client side if needed 
        // but ApiService.getRounds supports roundId param? Yes it does in our implementation.

        const data = await ApiService.getRounds({
          roundId: parseInt(activeRoundId),
          isActive: false,
          hasVotingType,
          filterCountry: activeCountry,
          filterContinent: activeContinent,
          searchTerm: activeSearch
        })

        if (data && data.length > 0) {
          setContestsData(data[0])
        } else {
          setContestsData(null)
        }
      } catch (error) {
        console.error('Failed to fetch contests:', error)
      } finally {
        setContestsLoading(false)
      }
    }

    fetchContestsForRound()
  }, [activeRoundId, isAuthenticated, categoryTab, filterCountry, filterContinent, committedSearch])

  // Raw Contests List (Before filtering by type)
  const rawContests = useMemo(() => {
    // New Structure: contestsData.contests (from REST API)
    const activeRound = contestsData
    if (!activeRound?.contests) return []

    return activeRound.contests.map((c: any) => {
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
        received: c.votes_count || 0,
        contestants: c.participants_count || c.entries_count || 0,
        isOpen: activeRound.is_submission_open || activeRound.is_voting_open || false,
        contestType: c.contest_type,
        isSubmissionOpen: activeRound.is_submission_open,
        isVotingOpen: activeRound.is_voting_open,
        // Pass dates for countdown in ContestCard
        participationStartDate: activeRound.submission_start_date,
        participationEndDate: activeRound.submission_end_date,
        votingStartDate: activeRound.voting_start_date,
        votingEndDate: activeRound.voting_end_date,
        currentUserParticipated: false, // Not fetching this specific user status in new query yet
        topContestants: [] // Not fetching top contestants per contest in new query yet
      }
    })
  }, [contestsData])

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
    let filtered = [...rawContests]

    // 1. Filter by Tab (Type)
    if (activeTab !== 'all') {
      filtered = filtered.filter(c => c.contestType === activeTab)
    }

    // 2. Filter by Search
    if (committedSearch) {
      const lower = committedSearch.toLowerCase()
      filtered = filtered.filter(c => c.title.toLowerCase().includes(lower))
    }

    // 3. Location Filters (if applicable to contest objects in future, currently filtering by user input)
    // Add logic here if contests have country/continent fields

    // 4. Sort
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'participants': return b.contestants - a.contestants
        case 'votes': return b.received - a.received
        case 'name': return a.title.localeCompare(b.title)
        default: return b.contestants - a.contestants
      }
    })

    return filtered
  }, [rawContests, activeTab, committedSearch, sortBy])

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

        {/* Location Filter Bar (Re-added) */}
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
          className="mb-6"
        />

        {/* Main Category Tabs (Nomination / Participations) */}
        <div className="mb-6 border-b border-gray-800">
          <div className="flex space-x-1">
            <button
              onClick={() => {
                setCategoryTab('nomination');
                setActiveTab('all');
                setSearchTerm('');
                setCommittedSearch('');
                setFilterCountry('');
                setFilterContinent('all');
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
                setFilterCountry('');
                setFilterContinent('all');
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
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {displayedContests.map((contest: any) => (
              <ContestCard
                key={contest.id}
                {...contest}
                canParticipate={true}
                isKycVerified={!!user?.identity_verified}
                isFavorite={false}
                onToggleFavorite={() => { }}
                onParticipate={() => handleParticipate(contest.id, contest.currentUserParticipated)}
                onViewContestants={() => router.push(`/dashboard/contests/${contest.id}`)}
                onOpenDetails={() => router.push(`/dashboard/contests/${contest.id}`)}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-20">
            <p className="text-gray-500">No contests found matching criteria.</p>
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
