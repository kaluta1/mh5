'use client'

import * as React from "react"
import { useState, useEffect, useMemo } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useSearchParams } from 'next/navigation'
import { useToast } from '@/components/ui/toast'
import { ContestsSkeleton } from '@/components/ui/skeleton'
import { ContestsLoader } from '@/components/dashboard/contests-loader'
import { Contest } from '@/services/contest-service'
import { Lightbulb } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ContestCard } from '@/components/dashboard/contest-card'
import { SuggestContestDialog } from '@/components/dashboard/suggest-contest-dialog'
import { LocationFilterBar } from '@/components/dashboard/location-filter-bar'

// GraphQL
import { useQuery } from '@apollo/client'
import { GET_ROUNDS_FOR_SELECTOR, GET_CONTESTS_BY_ROUND } from '@/graphql/queries'

export default function ContestsPage() {
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
  const [sortBy, setSortBy] = useState<string>('participants')
  const [filterContinent, setFilterContinent] = useState<string>('all')
  const [filterCountry, setFilterCountry] = useState<string>('')

  // Constants
  const ITEMS_PER_PAGE = 50 // Increased since we filter client-side for types

  // 1. Fetch Rounds for Selector
  const { data: roundsData, loading: roundsLoading } = useQuery(GET_ROUNDS_FOR_SELECTOR, {
    variables: { isActive: true },
    skip: !isAuthenticated,
    fetchPolicy: 'cache-first'
  })

  // Set default active round
  useEffect(() => {
    if (roundsData?.rounds?.length > 0 && !activeRoundId) {
      setActiveRoundId(String(roundsData.rounds[0].id))
    }
  }, [roundsData, activeRoundId])

  // Save category tab preference
  useEffect(() => {
    if (typeof window !== 'undefined') localStorage.setItem('contests_category_tab', categoryTab)
  }, [categoryTab])

  // 2. Fetch Contests for Selected Round (Fetch ALL types to populate tabs correctly)
  const hasVotingType = categoryTab === 'nomination' ? true : false

  const { data: contestsData, loading: contestsLoading } = useQuery(GET_CONTESTS_BY_ROUND, {
    variables: {
      roundId: activeRoundId ? parseInt(activeRoundId) : 0,
      skip: 0,
      limit: ITEMS_PER_PAGE,
      // We DO NOT filter by contestType in the query so we get all types back 
      // to populate the tabs list
      contestType: undefined,
      hasVotingType: hasVotingType
    },
    skip: !activeRoundId || !isAuthenticated,
    fetchPolicy: 'cache-first'
  })

  // Raw Contests List (Before filtering by type)
  const rawContests = useMemo(() => {
    if (!contestsData?.contests) return []

    return contestsData.contests.map((c: any) => {
      const roundStats = c.rounds.find((r: any) => String(r.id) === activeRoundId) || {}

      // Fallback multiple pour l'image
      const rawImage = c.coverImageUrl || c.imageUrl || c.cover_image_url || c.image_url || '/placeholder.png'

      const isEmoji = rawImage?.length <= 4 && rawImage?.codePointAt(0) > 0x1F000
      let coverImage = rawImage

      if (!isEmoji && coverImage && !coverImage.startsWith('http') && !coverImage.startsWith('data:') && !coverImage.startsWith('/')) {
        const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        coverImage = `${API_BASE_URL}/${coverImage}`
      }

      console.log('Cover Image Debug:', { id: c.id, name: c.name, raw: rawImage, final: coverImage })

      return {
        id: String(c.id),
        title: c.name,
        description: c.description,
        coverImage: coverImage,
        startDate: new Date(),
        status: c.level || 'country',
        received: roundStats.votesCount || 0,
        contestants: roundStats.participantsCount || 0,
        isOpen: roundStats.isSubmissionOpen || roundStats.isVotingOpen || false,
        contestType: c.contestType,
        isSubmissionOpen: roundStats.isSubmissionOpen,
        isVotingOpen: roundStats.isVotingOpen,
        currentUserParticipated: roundStats.currentUserParticipated,
        topContestants: roundStats.topContestants?.map((tc: any) => ({
          id: tc.id,
          image_url: tc.imageUrl,
          votes_count: tc.votesCount,
          author_name: tc.author?.username,
          author_avatar_url: tc.author?.avatarUrl
        })) || []
      }
    })
  }, [contestsData, activeRoundId])

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
    if (searchTerm) {
      const lower = searchTerm.toLowerCase()
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
  }, [rawContests, activeTab, searchTerm, sortBy])


  // Handlers
  const handleParticipate = (id: string, isEditing: boolean) => {
    router.push(isEditing ? `/dashboard/contests/${id}/apply?edit=true` : `/dashboard/contests/${id}/apply`)
  }

  if (isLoading || (roundsLoading && !roundsData)) return <ContestsSkeleton />
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
            {roundsData?.rounds.map((round: any) => (
              <button
                key={round.id}
                onClick={() => setActiveRoundId(String(round.id))}
                className={`px-5 py-2.5 rounded-full text-sm font-medium transition-all whitespace-nowrap ${activeRoundId === String(round.id)
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
                  }`}
              >
                {round.name} <span className="ml-1 opacity-70">({round.participantsCount || 0})</span>
              </button>
            ))}
          </div>
        </div>

        {/* Location Filter Bar (Re-added) */}
        <LocationFilterBar
          user={user}
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          onSearch={() => { }}
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
              onClick={() => { setCategoryTab('nomination'); setActiveTab('all'); }}
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${categoryTab === 'nomination' ? 'border-blue-500 text-blue-500' : 'border-transparent text-gray-400 hover:text-gray-300'}`}
            >
              {t('dashboard.contests.nomination') || 'Nomination'}
            </button>
            <button
              onClick={() => { setCategoryTab('participations'); setActiveTab('all'); }}
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
