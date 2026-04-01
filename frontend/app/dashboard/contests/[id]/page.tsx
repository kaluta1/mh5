'use client'

import { cleanVideoUrl } from '@/lib/utils/video-platforms'
import * as React from "react"
import { useState, useEffect } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useParams, useSearchParams } from 'next/navigation'
import { ContestDetailSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ArrowLeft, Sparkles, Users, Video, Image, Globe, Lightbulb, Youtube, ExternalLink, HelpCircle, Trophy } from 'lucide-react'
import { contestService, ContestResponse } from '@/services/contest-service'
// REST API
import ApiService from '@/lib/api-service'
import { ContestInfoDialog } from '@/components/dashboard/contest-info-dialog'
import { ContestantsList } from '@/components/dashboard/contestants-list'
import { ContestantsSidebar } from '@/components/dashboard/contestants-sidebar'
import MyVotesPanel from '@/components/dashboard/my-votes-panel'
import { HoverInfoDialog } from '@/components/dashboard/hover-info-dialog'
import { ReportContestantDialog } from '@/components/dashboard/report-contestant-dialog'
import { LocationFilterBar } from '@/components/dashboard/location-filter-bar'

interface Media {
  id: string
  type: 'image' | 'video'
  url: string
  thumbnail?: string
}

interface Contestant {
  id: string
  userId?: number
  name: string
  country?: string
  city?: string
  continent?: string
  region?: string
  avatar: string
  participationTitle?: string
  description: string
  votes: number
  rank?: number
  imagesCount: number
  videosCount: number
  canVote: boolean
  isVotingOpenForRound: boolean
  hasVoted: boolean
  voteRestrictionReason?: string | null
  media: Media[]
  comments: number
  reactions?: number
  favorites?: number
  shares?: number
  isFavorite: boolean
  votesList?: Array<{
    id?: number
    user_id: number
    username?: string
    full_name?: string
    avatar_url?: string
    points: number
    vote_date: string
    contest_id?: number
    season_id?: number
  }>
  commentsList?: Array<{
    id: number
    user_id: number
    username?: string
    full_name?: string
    avatar_url?: string
    content: string
    created_at: string
    parent_id?: number | null
  }>
  reactionsList?: {
    [key: string]: Array<{
      id?: number
      user_id: number
      username?: string
      full_name?: string
      avatar_url?: string
      reaction_type: string
    }>
  }
  favoritesList?: Array<{
    id?: number
    user_id: number
    username?: string
    full_name?: string
    avatar_url?: string
    position?: number
    added_date: string
  }>
  sharesList?: Array<{
    id: number
    user_id?: number
    username?: string
    full_name?: string
    avatar_url?: string
    platform?: string
    share_link: string
    created_at: string
  }>
  season?: {
    id: number
    title: string
    level: string
  }
}

interface ContestDetail {
  contest: ContestResponse
  contestants: Contestant[]
  current_user_contesting?: boolean
  active_round_id?: number | null
}

export default function ContestDetailPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const contestId = params.id as string

  const [contest, setContest] = useState<ContestDetail | null>(null)
  const [favorites, setFavorites] = useState<string[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [showInfoDialog, setShowInfoDialog] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [hoveredElement, setHoveredElement] = useState<{ type: 'author' | 'description' | 'votes' | 'reactions' | 'favorites'; id: string; data?: any } | null>(null)
  const [hoverTimeout, setHoverTimeout] = useState<NodeJS.Timeout | null>(null)
  const [reportDialogOpen, setReportDialogOpen] = useState(false)
  const [showVotesPanel, setShowVotesPanel] = useState(false)
  const [selectedContestantId, setSelectedContestantId] = useState<number | null>(null)
  const [selectedContestantTitle, setSelectedContestantTitle] = useState<string>('')
  const [userHasEntry, setUserHasEntry] = useState(false)

  // Read location filters from URL (so "View contestants" from list uses selected country, e.g. Uganda)
  const searchParams = useSearchParams()
  const [filterCountry, setFilterCountry] = React.useState<string>(() => {
    return searchParams.get('country') || 'all'
  })
  const [filterContinent, setFilterContinent] = React.useState<string>(() => {
    return searchParams.get('continent') || 'all'
  })
  const entryType = searchParams.get('entryType') || undefined
  const roundIdFromUrl = searchParams.get('roundId')

  // Sync state from URL when params change (e.g. navigation from list with country=Uganda)
  React.useEffect(() => {
    const urlCountry = searchParams.get('country') || ''
    const urlContinent = searchParams.get('continent') || 'all'
    setFilterCountry(urlCountry)
    setFilterContinent(urlContinent)
  }, [searchParams])

  // Default to 'all' when no URL params (don't auto-filter by user country)
  React.useEffect(() => {
    const urlCountry = searchParams.get('country')
    const urlContinent = searchParams.get('continent')
    if (urlCountry || urlContinent) return
    // No auto-filter by user country: show all contestants by default
    setFilterCountry('all')
    setFilterContinent('all')
  }, [searchParams])

  // Mettre à jour l'URL quand les filtres changent
  const updateUrlWithFilters = React.useCallback((continent: string, country: string) => {
    const params = new URLSearchParams()
    if (continent) {
      params.set('continent', continent)
    }
    if (country) {
      params.set('country', country)
    }
    // Préserver le entryType dans l'URL
    if (entryType) {
      params.set('entryType', entryType)
    }
    if (roundIdFromUrl) {
      params.set('roundId', roundIdFromUrl)
    }
    const queryString = params.toString()
    const newUrl = `/dashboard/contests/${contestId}${queryString ? `?${queryString}` : ''}`
    router.replace(newUrl, { scroll: false })
  }, [router, contestId, entryType, roundIdFromUrl])

  // REST Data Fetching - Optimized for speed
  const fetchContestDetails = React.useCallback(async () => {
    if (!contestId) return

    const abortController = new AbortController()

    try {
      setPageLoading(true)
      // Fetch contest data
      const c = await ApiService.getContest(parseInt(contestId), {
        filterCountry: (!filterCountry || filterCountry === 'all') ? undefined : filterCountry,
        filterContinent: filterContinent === 'all' ? undefined : filterContinent,
        entryType: entryType,
        roundId: roundIdFromUrl ? parseInt(roundIdFromUrl, 10) : undefined,
      }) as any

      // Check if aborted
      if (abortController.signal.aborted) return

      // Map data
      const parseMediaIds = (mediaIds: string | undefined, type: 'image' | 'video'): Media[] => {
        if (!mediaIds) return []
        try {
          const parsed = typeof mediaIds === 'string' ? JSON.parse(mediaIds) : mediaIds
          if (!Array.isArray(parsed)) return []
          const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          return parsed.filter((url: string) => url && url.trim() !== '').map((url: string, index: number) => {
            // Nettoyer les URLs double-encodées JSON
            let fullUrl = cleanVideoUrl(url) || url
            if (fullUrl && !fullUrl.startsWith('http') && !fullUrl.startsWith('data:')) {
              fullUrl = fullUrl.startsWith('/') ? `${API_BASE_URL}${fullUrl}` : `${API_BASE_URL}/${fullUrl}`
            }
            return { id: `${type}-${index}`, type, url: fullUrl, thumbnail: type === 'video' ? fullUrl : undefined }
          })
        } catch (e) { return [] }
      }

      const mappedContestants: Contestant[] = (c.contestants || []).map((ct: any, index: number) => {
        const images = parseMediaIds(ct.image_media_ids, 'image') // snake_case from python
        const videos = parseMediaIds(ct.video_media_ids, 'video')
        return {
          id: String(ct.id ?? index),
          userId: ct.user_id,
          name: ct.author_name || `Contestant #${index + 1}`,
          country: ct.author_country,
          city: ct.author_city,
          continent: ct.author?.continent, // check if existing schema had this nested or flat
          avatar: ct.author_avatar_url || '👤',
          participationTitle: ct.title,
          description: ct.description ?? '',
          votes: ct.votes_count ?? 0,
          totalPoints: ct.total_points ?? 0,
          isVotingOpenForRound: ct.is_voting_open_for_round !== false,
          rank: ct.rank,
          imagesCount: ct.images_count ?? images.length,
          videosCount: ct.videos_count ?? videos.length,
          canVote: ct.can_vote ?? false,
          hasVoted: ct.has_voted ?? false,
          media: [...images, ...videos],
          comments: ct.comments_count ?? 0,
          reactions: ct.reactions_count ?? 0,
          favorites: ct.favorites_count ?? 0,
          shares: ct.shares_count ?? 0,
          isFavorite: ct.is_in_favorites ?? false,
          votesList: ct.votes || [],
          commentsList: ct.comments || [],
        }
      })

      // Backend already sorts by rank (ascending) and votes (descending)
      // No need to re-sort - backend provides contestants with most votes first
      // This ensures instant display without any delay

      const contestData = {
        contest: {
          ...c,
          entries_count: c.entries_count,
          total_votes: c.total_votes,
          cover_image_url: c.cover_image_url,
          current_user_contesting: c.current_user_contesting || false  // Ensure this is included
        },
        contestants: mappedContestants
      }

      setContest(contestData)

      setFavorites(mappedContestants.filter(ct => ct.isFavorite).map(ct => ct.id))

    } catch (error: any) {
      // Ignore aborted requests
      if (error?.name === 'AbortError' || abortController.signal.aborted) {
        return
      }
      // Failed to fetch contest
      setToast({ message: "Failed to load contest", type: "error" })
    } finally {
      if (!abortController.signal.aborted) {
        setPageLoading(false)
      }
    }
  }, [contestId, filterCountry, filterContinent, entryType, roundIdFromUrl, t])

  // Decide if the current user already submitted (so the CTA should show "Edit").
  // This is needed because `current_user_contesting` from the API can be inaccurate for nominations.
  React.useEffect(() => {
    const computeUserEntry = async () => {
      if (!user?.id || !contest) {
        setUserHasEntry(false)
        return
      }

      const contestMode = contest?.contest?.contest_mode
      const desiredEntryType = contestMode === 'nomination' ? 'nomination' : 'participation'
      const displayRoundId =
        contest?.contest?.display_round_id ??
        contest?.contest?.active_round_id ??
        contest?.active_round_id ??
        null
      const seasonId = parseInt(contestId)

      try {
        const userEntries = await contestService.getContestantsByContest(contestId, {
          user_id: user.id,
          skip: 0,
          limit: 50
        })

        const hasMatch = userEntries.some((e: any) => {
          const entryType = e?.entry_type
          // If the backend doesn't provide entry_type, fall back to "any entry matches".
          const typeMatch = !entryType || entryType === desiredEntryType
          if (!typeMatch) return false

          const seasonMatch = e?.season_id ? e.season_id === seasonId : true
          if (!seasonMatch) return false

          const roundMatch = displayRoundId != null ? e?.round_id === displayRoundId : true
          return roundMatch
        })

        setUserHasEntry(hasMatch)
      } catch {
        setUserHasEntry(false)
      }
    }

    computeUserEntry()
  }, [user?.id, contestId, contest?.contest?.contest_mode, contest?.contest?.active_round_id, contest?.contest?.display_round_id])

  useEffect(() => {
    fetchContestDetails()
    // Cleanup handled in fetchContestDetails via abortController
  }, [fetchContestDetails])

  // After vote / replace, refresh all cards so "Voted" ↔ "Vote" matches server (replaced contestant shows Vote again)
  useEffect(() => {
    const onVoteChanged = () => {
      void fetchContestDetails()
    }
    window.addEventListener('vote-changed', onVoteChanged)
    return () => window.removeEventListener('vote-changed', onVoteChanged)
  }, [fetchContestDetails])

  const handleReportClick = (contestantId: string) => {
    const contestant = contest?.contestants.find(c => c.id === contestantId)
    if (contestant) {
      setSelectedContestantId(parseInt(contestantId))
      setSelectedContestantTitle(contestant.participationTitle || contestant.name)
      setReportDialogOpen(true)
    }
  }

  const handleDeleteContestant = async (contestantId: string) => {
    try {
      await contestService.deleteContestant(Number(contestantId))
      // Refetch REST data
      await fetchContestDetails()
      showToast(t('common.deleted_successfully') || `Candidature supprimée avec succès`, 'success')
    } catch (err: any) {
      // Error during deletion
      const errorMessage = err?.response?.data?.detail || err?.message || t('common.delete_error') || 'Erreur lors de la suppression'
      showToast(errorMessage, 'error')
      throw err
    }
  }

  const showToast = (message: string, type: 'success' | 'error' = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleHoverStart = (type: 'author' | 'description' | 'votes' | 'reactions' | 'favorites', id: string, data?: any) => {
    if (hoverTimeout) {
      clearTimeout(hoverTimeout)
    }

    const timeout = setTimeout(() => {
      setHoveredElement({ type, id, data })
    }, 2000)

    setHoverTimeout(timeout)
  }

  const handleHoverEnd = () => {
    if (hoverTimeout) {
      clearTimeout(hoverTimeout)
      setHoverTimeout(null)
    }
  }

  const handleToggleFavorite = async (contestantId: string) => {
    const isFavorite = favorites.includes(contestantId)

    try {
      if (isFavorite) {
        await contestService.removeFromFavorites(parseInt(contestantId), 'contestant')
        setFavorites(prevFavorites => prevFavorites.filter(id => id !== contestantId))
        setContest((prev) => {
          if (!prev) return null
          return {
            ...prev,
            contestants: prev.contestants.map(c =>
              c.id === contestantId ? { ...c, isFavorite: false } : c
            )
          }
        })
        showToast(t('dashboard.contests.removed_from_favorites') || 'Contestant retiré des favoris', 'success')
      } else {
        if (favorites.length >= 5) {
          showToast(t('dashboard.contests.favorite_limit_reached'), 'error')
          return
        }

        await contestService.addToFavorites(parseInt(contestantId), 'contestant')
        setFavorites(prevFavorites => [...prevFavorites, contestantId])
        setContest((prev) => {
          if (!prev) return null
          return {
            ...prev,
            contestants: prev.contestants.map(c =>
              c.id === contestantId ? { ...c, isFavorite: true } : c
            )
          }
        })
        showToast(t('dashboard.contests.added_to_favorites') || 'Contestant ajouté aux favoris', 'success')
      }
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'Une erreur est survenue'
      showToast(errorMessage, 'error')
      // Error updating favorites
    }
  }

  // Canonical country codes for strict single-country matching (user sees ONLY one country)
  const getCountryCode = React.useCallback((str: string | undefined): string => {
    if (!str) return ''
    const n = (str || '').toLowerCase().trim()
    const map: Record<string, string> = {
      uganda: 'ug', ug: 'ug', tanzania: 'tz', tz: 'tz', 'united republic of tanzania': 'tz',
      kenya: 'ke', ke: 'ke', rwanda: 'rw', rw: 'rw', burundi: 'bi', bi: 'bi',
      'ivory coast': 'ci', 'côte d\'ivoire': 'ci', 'cote d\'ivoire': 'ci', ci: 'ci',
      nigeria: 'ng', ng: 'ng', ghana: 'gh', gh: 'gh', senegal: 'sn', sn: 'sn',
      cameroon: 'cm', cm: 'cm', 'south africa': 'za', za: 'za', ethiopia: 'et', et: 'et',
      egypt: 'eg', eg: 'eg', morocco: 'ma', ma: 'ma', algeria: 'dz', dz: 'dz',
    }
    return map[n] || n
  }, [])

  // Strict: only show contestants from the selected country (or user's country if none selected)
  const effectiveCountry = (filterCountry && filterCountry !== 'all' ? filterCountry : '') || ''
  const effectiveContinent = (filterContinent && filterContinent !== 'all' ? filterContinent : '') || ''

  const locationFilteredContestants = React.useMemo(() => {
    const list = contest?.contestants ?? []
    if (!effectiveCountry && !effectiveContinent) return list
    return list.filter((c) => {
      const matchCountry = !effectiveCountry || (() => {
        const cc = (c.country || '').toLowerCase().trim()
        if (!cc) return false
        const codeFilter = getCountryCode(effectiveCountry)
        const codeContestant = getCountryCode(c.country)
        if (codeFilter && codeContestant && codeFilter === codeContestant) return true
        if (effectiveCountry.toLowerCase().trim() === cc) return true
        if (cc.includes(effectiveCountry.toLowerCase().trim()) || effectiveCountry.toLowerCase().trim().includes(cc)) return true
        return false
      })()
      const matchContinent = !effectiveContinent || (() => {
        const cc = (c.continent || '').toLowerCase().trim()
        if (!cc) return false
        return cc.includes(effectiveContinent.toLowerCase()) || effectiveContinent.toLowerCase().includes(cc) || effectiveContinent.toLowerCase() === cc
      })()
      return matchCountry && matchContinent
    })
  }, [contest?.contestants, effectiveCountry, effectiveContinent, getCountryCode, user?.country])

  if (isLoading || pageLoading) {
    return <ContestDetailSkeleton />
  }

  // Allow unauthenticated users to view contest details (they just can't participate)
  if (!contest) {
    return null
  }

  const participantsCount = contest.contest.entries_count ?? contest.contestants.length

  // Fonction pour formater la localisation selon le niveau de saison
  const formatLocation = (contestant: Contestant): string => {
    const level = (contest.contest.season_level || contest.contest.level || '').toLowerCase()
    const parts: string[] = []

    if (level === 'city') {
      // Afficher ville + pays
      if (contestant.city) parts.push(contestant.city)
      if (contestant.country) parts.push(contestant.country)
    } else if (level === 'country') {
      // Afficher pays + continent
      if (contestant.country) parts.push(contestant.country)
      if (contestant.continent) parts.push(contestant.continent)
    } else if (level === 'regional' || level === 'region') {
      // Afficher région + continent
      if (contestant.region) parts.push(contestant.region)
      if (contestant.continent) parts.push(contestant.continent)
    } else if (level === 'continent' || level === 'continental') {
      // Afficher continent uniquement
      if (contestant.continent) parts.push(contestant.continent)
    } else {
      // Global ou niveau inconnu -> afficher toutes les infos disponibles
      if (contestant.city) parts.push(contestant.city)
      if (contestant.country) parts.push(contestant.country)
      if (contestant.region) parts.push(contestant.region)
      if (contestant.continent) parts.push(contestant.continent)
    }

    return parts.length > 0 ? parts.join(' · ') : t('dashboard.contests.participant') || 'Participant'
  }

  const filteredContestants = locationFilteredContestants.filter(contestant => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    return (
      contestant.name.toLowerCase().includes(query) ||
      contestant.participationTitle?.toLowerCase().includes(query) ||
      contestant.description.toLowerCase().includes(query) ||
      contestant.country?.toLowerCase().includes(query) ||
      contestant.city?.toLowerCase().includes(query) ||
      contestant.continent?.toLowerCase().includes(query) ||
      contestant.region?.toLowerCase().includes(query)
    )
  })

  // Déterminer si c'est une nomination
  const isNomination = contest.contest.contest_mode === 'nomination'
  const hasNoContestants = filteredContestants.length === 0

  // Déterminer si l'utilisateur peut participer (pays sélectionné = son pays ou aucun filtre)
  const isUserCountrySelected = !filterCountry || filterCountry === 'all' || filterCountry === '' || (user?.country && filterCountry.toLowerCase() === user.country.toLowerCase())

  return (
    <div className="min-h-screen">
      <div className="py-2 px-1 sm:px-2">
        <div>
          {/* Compact Header */}
          <div className="relative overflow-hidden rounded-xl bg-gradient-to-r from-[#1e3a8a] to-[#0e7490] mb-4 shadow-md">
            <div className="relative z-10 px-4 py-3 sm:px-5 sm:py-3.5 flex items-center gap-3">
              <button
                onClick={() => router.back()}
                className="flex-shrink-0 w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition-all cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
              <div className="flex-1 min-w-0">
                <h1 className="text-lg sm:text-xl font-bold text-white truncate">
                  {contest.contest.name}
                </h1>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-blue-200/80 text-xs font-medium">
                    {participantsCount} participants
                  </span>
                  <span className="text-blue-200/50">·</span>
                  <span className="text-blue-200/80 text-xs font-medium">
                    {contest.contest.total_points || 0} pts
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowVotesPanel(true)}
                  className="flex-shrink-0 h-8 px-3 rounded-full bg-white/10 hover:bg-white/20 flex items-center gap-1.5 text-white text-xs font-medium transition-all cursor-pointer"
                >
                  <Trophy className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Votes</span>
                </button>
                <button
                  onClick={() => setShowInfoDialog(true)}
                  className="flex-shrink-0 w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition-all cursor-pointer"
                >
                  <HelpCircle className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Barre de recherche et filtres */}
          <LocationFilterBar
            user={user}
            searchTerm={searchQuery}
            onSearchChange={setSearchQuery}
            searchPlaceholder={t('dashboard.contests.search_contestant') || 'Rechercher un participant...'}
            filterContinent={filterContinent}
            onContinentChange={(value) => {
              setFilterContinent(value)
              updateUrlWithFilters(value, filterCountry)
            }}
            filterCountry={filterCountry}
            onCountryChange={(value) => {
              setFilterCountry(value)
              updateUrlWithFilters(filterContinent, value)
            }}
            showSort={false}
            showSearchButton={false}
            className="mb-4"
          />

          {/* Toast Notification */}
          {toast && (
            <div className={`fixed bottom-4 right-4 rounded-xl shadow-xl p-4 z-50 animate-in fade-in slide-in-from-bottom-2 backdrop-blur-sm ${toast.type === 'success'
              ? 'bg-green-50/95 dark:bg-green-900/30 border border-green-200 dark:border-green-800'
              : 'bg-red-50/95 dark:bg-red-900/30 border border-red-200 dark:border-red-800'
              }`}>
              <p className={`text-sm font-medium ${toast.type === 'success'
                ? 'text-green-700 dark:text-green-300'
                : 'text-red-700 dark:text-red-300'
                }`}>
                {toast.type === 'success' ? '✅' : '❌'} {toast.message}
              </p>
            </div>
          )}

          {/* Contest Info Dialog */}
          <ContestInfoDialog
            isOpen={showInfoDialog}
            onOpenChange={setShowInfoDialog}
            contest={contest.contest}
            participantsCount={participantsCount}
          />

          {/* Hover Info Dialog */}
          {hoveredElement && (
            <HoverInfoDialog
              isOpen={!!hoveredElement}
              onOpenChange={() => {
                setHoveredElement(null)
                if (hoverTimeout) {
                  clearTimeout(hoverTimeout)
                  setHoverTimeout(null)
                }
              }}
              type={hoveredElement.type}
              data={hoveredElement.data}
            />
          )}

          {/* Mobile Top Contestants Scroll - visible uniquement pendant le vote */}
          {locationFilteredContestants.length > 0 && locationFilteredContestants.some(c => c.isVotingOpenForRound) && (
            <div className="lg:hidden mb-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {t('dashboard.contests.top_contestants') || 'Top Contestants'}
                </h3>
                <button
                  onClick={() => {
                    const params = new URLSearchParams()
                    if (roundIdFromUrl) params.set('roundId', roundIdFromUrl)
                    if (filterCountry) params.set('country', filterCountry)
                    if (filterContinent && filterContinent !== 'all') params.set('continent', filterContinent)
                    const qs = params.toString()
                    router.push(`/dashboard/contests/${contestId}/contestants${qs ? '?' + qs : ''}`)
                  }}
                  className="text-xs font-medium text-myhigh5-primary hover:text-myhigh5-blue-600 transition-colors cursor-pointer"
                >
                  {t('dashboard.contests.view_all_contestants') || 'Voir tout'}
                </button>
              </div>
              <div className="flex overflow-x-auto gap-4 pb-2 -mx-1 px-1" style={{ scrollbarWidth: 'none' }}>
                {locationFilteredContestants.slice(0, 10).map((c) => (
                  <div key={c.id} className="flex-shrink-0 flex flex-col items-center gap-1.5 w-16">
                    <div className="relative">
                      {c.avatar && (c.avatar.startsWith('http') || c.avatar.startsWith('/')) ? (
                        <img
                          src={c.avatar}
                          alt={c.name}
                          className={`w-14 h-14 rounded-full object-cover ring-2 ${
                            c.rank === 1 ? 'ring-yellow-400' : c.rank === 2 ? 'ring-gray-400' : c.rank === 3 ? 'ring-amber-600' : 'ring-gray-200 dark:ring-gray-700'
                          }`}
                        />
                      ) : (
                        <div className={`w-14 h-14 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center text-lg ring-2 ${
                          c.rank === 1 ? 'ring-yellow-400' : c.rank === 2 ? 'ring-gray-400' : c.rank === 3 ? 'ring-amber-600' : 'ring-gray-200 dark:ring-gray-700'
                        }`}>
                          {c.avatar || '👤'}
                        </div>
                      )}
                      {c.rank && c.rank <= 3 && (
                        <span className={`absolute -bottom-0.5 -right-0.5 w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center shadow-md border-2 border-white dark:border-gray-900 ${
                          c.rank === 1 ? 'bg-yellow-400 text-yellow-900' : c.rank === 2 ? 'bg-gray-300 text-gray-700' : 'bg-amber-600 text-white'
                        }`}>
                          {c.rank}
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-gray-600 dark:text-gray-400 truncate w-full text-center leading-tight">
                      {c.name.split(' ')[0]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Main Content Layout: Contestants with Sidebar */}
          <div className="mt-2 lg:mt-6">
            {/* Contestants Cards - Left Side (2/3 width on large screens) */}
            <div className="space-y-6">
              {hasNoContestants ? (
                /* Empty State - No Contestants */
                <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8 md:p-12 text-center">
                  <div className="max-w-2xl mx-auto space-y-6">
                    {/* Icon */}
                    <div className="flex justify-center">
                      <div className="w-20 h-20 bg-myhigh5-primary dark:bg-myhigh5-blue-700 rounded-full flex items-center justify-center shadow-lg">
                        {isNomination ? (
                          <Sparkles className="w-10 h-10 text-white" />
                        ) : (
                          <Users className="w-10 h-10 text-white" />
                        )}
                      </div>
                    </div>

                    {/* Title */}
                    <div className="space-y-2">
                      <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white">
                        {isNomination
                          ? (t('dashboard.contests.be_first_to_nominate') || 'Soyez le premier à nommer !')
                          : (t('dashboard.contests.be_first_to_participate') || 'Soyez le premier à participer !')
                        }
                      </h2>
                      <p className="text-gray-600 dark:text-gray-300 text-lg">
                        {isNomination
                          ? (t('dashboard.contests.empty_nomination_message') || 'Aucune nomination pour le moment. Commencez en nommant quelqu\'un de votre pays !')
                          : (t('dashboard.contests.empty_participation_message') || 'Aucun participant pour le moment. Soyez le premier à participer à ce concours !')
                        }
                      </p>
                    </div>

                    {/* CTA Button - Show Edit if user has already nominated */}
                    {isUserCountrySelected ? (
                    <Button
                      onClick={() => {
                        const hasNominated = userHasEntry
                        const roundForApply =
                          (roundIdFromUrl ? parseInt(roundIdFromUrl, 10) : null) ||
                          contest?.contest?.display_round_id ||
                          contest?.contest?.active_round_id ||
                          contest?.active_round_id

                        const queryParams = new URLSearchParams()
                        if (hasNominated) queryParams.set('edit', 'true')
                        if (roundForApply) queryParams.set('roundId', String(roundForApply))

                        const queryString = queryParams.toString()
                        router.push(`/dashboard/contests/${contestId}/apply${queryString ? `?${queryString}` : ''}`)
                      }}
                      className="bg-myhigh5-primary hover:bg-myhigh5-blue-700 text-white font-semibold px-8 py-6 text-lg rounded-xl shadow-lg hover:shadow-xl transition-all duration-200 transform hover:scale-105"
                    >
                      {(() => {
                        return userHasEntry
                          ? (t('dashboard.contests.edit') || 'Modifier')
                          : isNomination
                            ? (t('dashboard.contests.nominate') || 'Nommer')
                            : (t('dashboard.contests.participate') || 'Participer')
                      })()}
                      <ExternalLink className="w-5 h-5 ml-2" />
                    </Button>
                    ) : (
                    <p className="text-gray-500 dark:text-gray-400 text-sm italic">
                      {t('dashboard.contests.select_your_country') || 'Sélectionnez votre pays pour participer ou nommer'}
                    </p>
                    )}

                    {/* Tips Section */}
                    <div className="mt-10 pt-8 border-t border-gray-200 dark:border-gray-700">
                      <div className="flex items-center justify-center gap-2 mb-6">
                        <Lightbulb className="w-5 h-5 text-yellow-500" />
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                          {t('dashboard.contests.tips') || 'Astuces'}
                        </h3>
                      </div>

                      <div className="grid md:grid-cols-2 gap-4 text-left">
                        {isNomination ? (
                          <>
                            {/* Tips for Nomination */}
                            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <Youtube className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                </div>
                                <div>
                                  <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    {t('dashboard.contests.tip_nomination_video') || 'Importez du contenu vidéo'}
                                  </h4>
                                  <p className="text-sm text-gray-600 dark:text-gray-400">
                                    {t('dashboard.contests.tip_nomination_video_desc') || 'Vous pouvez importer du contenu d\'un utilisateur depuis YouTube ou Vimeo de votre pays.'}
                                  </p>
                                </div>
                              </div>
                            </div>

                            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 bg-purple-100 dark:bg-purple-900 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <Globe className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                </div>
                                <div>
                                  <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    {t('dashboard.contests.tip_nomination_country') || 'Même pays requis'}
                                  </h4>
                                  <p className="text-sm text-gray-600 dark:text-gray-400">
                                    {t('dashboard.contests.tip_nomination_country_desc') || 'Le contenu doit provenir d\'un utilisateur de votre pays.'}
                                  </p>
                                </div>
                              </div>
                            </div>

                            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <Video className="w-4 h-4 text-green-600 dark:text-green-400" />
                                </div>
                                <div>
                                  <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    {t('dashboard.contests.tip_nomination_required') || 'Vidéo obligatoire'}
                                  </h4>
                                  <p className="text-sm text-gray-600 dark:text-gray-400">
                                    {t('dashboard.contests.tip_nomination_required_desc') || 'Les vidéos sont obligatoires pour les nominations. Les images sont optionnelles.'}
                                  </p>
                                </div>
                              </div>
                            </div>

                            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 bg-orange-100 dark:bg-orange-900 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <Sparkles className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                                </div>
                                <div>
                                  <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    {t('dashboard.contests.tip_nomination_platforms') || 'Plateformes supportées'}
                                  </h4>
                                  <p className="text-sm text-gray-600 dark:text-gray-400">
                                    {t('dashboard.contests.tip_nomination_platforms_desc') || 'YouTube (y compris YouTube Shorts), TikTok, ou liens vidéo directs. Facebook et Vimeo ne sont pas autorisés.'}
                                  </p>
                                </div>
                              </div>
                            </div>
                          </>
                        ) : (
                          <>
                            {/* Tips for Participation */}
                            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <Image className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                </div>
                                <div>
                                  <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    {t('dashboard.contests.tip_participation_content') || 'Utilisez votre propre contenu'}
                                  </h4>
                                  <p className="text-sm text-gray-600 dark:text-gray-400">
                                    {t('dashboard.contests.tip_participation_content_desc') || 'Partagez vos propres photos et vidéos pour participer au concours.'}
                                  </p>
                                </div>
                              </div>
                            </div>

                            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 bg-purple-100 dark:bg-purple-900 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <Video className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                </div>
                                <div>
                                  <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    {t('dashboard.contests.tip_participation_media') || 'Médias requis'}
                                  </h4>
                                  <p className="text-sm text-gray-600 dark:text-gray-400">
                                    {t('dashboard.contests.tip_participation_media_desc') || 'Vérifiez les exigences en matière d\'images et de vidéos pour ce concours.'}
                                  </p>
                                </div>
                              </div>
                            </div>

                            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <Users className="w-4 h-4 text-green-600 dark:text-green-400" />
                                </div>
                                <div>
                                  <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    {t('dashboard.contests.tip_participation_verification') || 'Vérification requise'}
                                  </h4>
                                  <p className="text-sm text-gray-600 dark:text-gray-400">
                                    {t('dashboard.contests.tip_participation_verification_desc') || 'Assurez-vous que votre compte est vérifié pour participer.'}
                                  </p>
                                </div>
                              </div>
                            </div>

                            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 bg-orange-100 dark:bg-orange-900 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                  <Sparkles className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                                </div>
                                <div>
                                  <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    {t('dashboard.contests.tip_participation_quality') || 'Qualité du contenu'}
                                  </h4>
                                  <p className="text-sm text-gray-600 dark:text-gray-400">
                                    {t('dashboard.contests.tip_participation_quality_desc') || 'Partagez votre meilleur contenu pour maximiser vos chances de gagner.'}
                                  </p>
                                </div>
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <ContestantsList
                  contestants={filteredContestants}
                  contestId={contestId}
                  currentUserId={user?.id}
                  favorites={favorites}
                  searchQuery={searchQuery}
                  onToggleFavorite={handleToggleFavorite}
                  onViewDetails={(contestantId) => router.push(`/dashboard/contests/${contestId}/contestant/${contestantId}`)}
                  onVote={() => {
                    // Rafraîchir le panel "Mes votes" après un vote
                    window.dispatchEvent(new Event('vote-changed'))
                  }}
                  onComment={() => { }}
                  onShare={() => { }}
                  onReport={handleReportClick}
                  onEdit={(contestantId) => router.push(`/dashboard/contests/${contestId}/apply?edit=true&contestantId=${contestantId}`)}
                  onDelete={handleDeleteContestant}
                  onHoverAuthor={(contestantId, data) => handleHoverStart('author', contestantId, data)}
                  onHoverEnd={handleHoverEnd}
                  onHoverDescription={(contestantId, description) => handleHoverStart('description', contestantId, description)}
                  onHoverVotes={(contestantId, votes) => {
                    const contestant = contest.contestants.find(c => c.id === contestantId)
                    // Seul l'auteur peut voir la liste des votes
                    if (user?.id === contestant?.userId) {
                      handleHoverStart('votes', contestantId, votes)
                    }
                  }}
                  onHoverReactions={(contestantId, reactions) => {
                    const contestant = contest.contestants.find(c => c.id === contestantId)
                    if (user?.id === contestant?.userId) {
                      handleHoverStart('reactions', contestantId, reactions)
                    }
                  }}
                  onHoverFavorites={(contestantId, favorites) => {
                    const contestant = contest.contestants.find(c => c.id === contestantId)
                    // Seul l'auteur peut voir la liste des favoris
                    if (user?.id === contestant?.userId) {
                      handleHoverStart('favorites', contestantId, favorites)
                    }
                  }}
                />
              )}
            </div>

            {/* Dialog de signalement */}
            {selectedContestantId !== null && (
              <ReportContestantDialog
                open={reportDialogOpen}
                onOpenChange={setReportDialogOpen}
                contestantId={selectedContestantId}
                contestId={parseInt(contestId)}
                contestantTitle={selectedContestantTitle}
              />
            )}

            {/* Votes & Leaderboard Dialog */}
            {showVotesPanel && (
              <div className="fixed inset-0 bg-black/60 z-50 flex items-start justify-end p-4" onClick={() => setShowVotesPanel(false)}>
                <div
                  className="w-full max-w-sm bg-white dark:bg-gray-800 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 max-h-[90vh] overflow-y-auto mt-12 animate-in slide-in-from-right"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between rounded-t-2xl z-10">
                    <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                      <Trophy className="w-5 h-5 text-myhigh5-primary" />
                      Votes & Classement
                    </h3>
                    <button onClick={() => setShowVotesPanel(false)} className="w-8 h-8 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-center text-gray-500">
                      ✕
                    </button>
                  </div>
                  <div className="p-4 space-y-4">
                    <MyVotesPanel
                      contestId={Number(contestId)}
                      onVoteChanged={() => {
                        window.dispatchEvent(new Event('vote-changed'))
                      }}
                    />
                    {locationFilteredContestants.some(c => c.isVotingOpenForRound) && (
                      <ContestantsSidebar
                        contestants={locationFilteredContestants}
                        contestId={contestId}
                        onShowToast={showToast}
                        filterCountry={filterCountry || undefined}
                        filterContinent={filterContinent !== 'all' ? filterContinent : undefined}
                        roundId={roundIdFromUrl || undefined}
                      />
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
