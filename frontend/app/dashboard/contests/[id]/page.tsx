'use client'

import * as React from "react"
import { useState, useEffect } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useParams, useSearchParams } from 'next/navigation'
import { ContestDetailSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ArrowLeft, Sparkles, Users, Video, Image, Globe, Lightbulb, Youtube, ExternalLink } from 'lucide-react'
import { contestService, ContestResponse } from '@/services/contest-service'
// REST API
import ApiService from '@/lib/api-service'
import { StickyPageHeader } from '@/components/ui/sticky-page-header'
import { ContestInfoDialog } from '@/components/dashboard/contest-info-dialog'
import { ContestantsList } from '@/components/dashboard/contestants-list'
import { ContestantsSidebar } from '@/components/dashboard/contestants-sidebar'
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
  const [selectedContestantId, setSelectedContestantId] = useState<number | null>(null)
  const [selectedContestantTitle, setSelectedContestantTitle] = useState<string>('')

  // Lire les filtres de localisation depuis l'URL (ou défaut: pays/continent de l'utilisateur)
  const searchParams = useSearchParams()
  const [filterCountry, setFilterCountry] = React.useState<string>(() => {
    return searchParams.get('country') || ''
  })
  const [filterContinent, setFilterContinent] = React.useState<string>(() => {
    return searchParams.get('continent') || 'all'
  })

  // Au premier chargement sans paramètres URL: afficher par défaut les contestants du pays + continent=all
  React.useEffect(() => {
    const urlCountry = searchParams.get('country')
    const urlContinent = searchParams.get('continent')
    if (urlCountry || urlContinent) return
    if (!user?.country) return
    const defaultCountry = (user?.country as string) || ''
    if (defaultCountry) {
      setFilterCountry(defaultCountry)
      setFilterContinent('all')
      const params = new URLSearchParams()
      params.set('country', defaultCountry)
      params.set('continent', 'all')
      router.replace(`/dashboard/contests/${contestId}?${params.toString()}`, { scroll: false })
    }
  }, [user?.country, contestId, router, searchParams])

  // Mettre à jour l'URL quand les filtres changent
  const updateUrlWithFilters = React.useCallback((continent: string, country: string) => {
    const params = new URLSearchParams()
    if (continent) {
      params.set('continent', continent)
    }
    if (country) {
      params.set('country', country)
    }
    const queryString = params.toString()
    const newUrl = `/dashboard/contests/${contestId}${queryString ? `?${queryString}` : ''}`
    router.replace(newUrl, { scroll: false })
  }, [router, contestId])

  // REST Data Fetching
  const fetchContestDetails = React.useCallback(async () => {
    if (!contestId) return

    try {
      setPageLoading(true)
      // Need to fetch contest + enrichment (participants etc)
      // Currently getContest returns everything if backend is updated
      // Fetch ALL contestants - backend filter can return 0 due to country format mismatch (TZ vs Tanzania)
      const c = await ApiService.getContest(parseInt(contestId), {
        filterCountry: 'all',
        filterContinent: 'all'
      }) as any

      // Map data
      const parseMediaIds = (mediaIds: string | undefined, type: 'image' | 'video'): Media[] => {
        if (!mediaIds) return []
        try {
          const parsed = typeof mediaIds === 'string' ? JSON.parse(mediaIds) : mediaIds
          if (!Array.isArray(parsed)) return []
          const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          return parsed.filter((url: string) => url && url.trim() !== '').map((url: string, index: number) => {
            let fullUrl = url
            if (url && !url.startsWith('http') && !url.startsWith('data:')) {
              fullUrl = url.startsWith('/') ? `${API_BASE_URL}${url}` : `${API_BASE_URL}/${url}`
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

      // Sort logic
      mappedContestants.sort((a, b) => {
        if (a.rank && b.rank) return a.rank - b.rank
        if (a.rank && !b.rank) return -1
        if (!a.rank && b.rank) return 1
        if (b.votes !== a.votes) return b.votes - a.votes
        return Number(a.id) - Number(b.id)
      })

      setContest({
        contest: {
          ...c,
          entries_count: c.entries_count,
          total_votes: c.total_votes,
          cover_image_url: c.cover_image_url
        },
        contestants: mappedContestants
      })

      setFavorites(mappedContestants.filter(ct => ct.isFavorite).map(ct => ct.id))

    } catch (error) {
      console.error("Failed to fetch contest:", error)
      setToast({ message: "Failed to load contest", type: "error" })
    } finally {
      setPageLoading(false)
    }
  }, [contestId, t])

  useEffect(() => {
    fetchContestDetails()
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
      console.error('Erreur lors de la suppression:', err)
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
        await contestService.removeFromFavorites(parseInt(contestantId))
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
        showToast('Contestant retiré des favoris', 'success')
      } else {
        if (favorites.length >= 5) {
          showToast(t('dashboard.contests.favorite_limit_reached'), 'error')
          return
        }

        await contestService.addToFavorites(parseInt(contestantId))
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
        showToast('Contestant ajouté aux favoris', 'success')
      }
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'Une erreur est survenue'
      showToast(errorMessage, 'error')
      console.error('Erreur lors de la modification des favoris:', error)
    }
  }

  // Client-side location filter - must be before early returns (hooks rules)
  const locationFilteredContestants = React.useMemo(() => {
    const list = contest?.contestants ?? []
    if (!filterCountry && (!filterContinent || filterContinent === 'all')) return list
    return list.filter((c) => {
      const matchCountry = !filterCountry || filterCountry === 'all' || (() => {
        const uc = (filterCountry || '').toLowerCase().trim()
        const cc = (c.country || '').toLowerCase().trim()
        if (!cc) return false
        if (uc === cc) return true
        if (cc.includes(uc) || uc.includes(cc)) return true
        const alias: Record<string, string[]> = { tz: ['tanzania', 'united republic of tanzania'], ke: ['kenya'] }
        const uCode = uc.length === 2 ? uc : Object.entries(alias).find(([, names]) => names.some(n => cc.includes(n) || uc.includes(n)))?.[0]
        const cCode = cc.length === 2 ? cc : Object.entries(alias).find(([, names]) => names.some(n => cc.includes(n)))?.[0]
        return uCode && cCode && uCode === cCode
      })()
      const matchContinent = !filterContinent || filterContinent === 'all' || (() => {
        const uc = (filterContinent || '').toLowerCase().trim()
        const cc = (c.continent || '').toLowerCase().trim()
        if (!cc) return false
        return cc.includes(uc) || uc.includes(cc) || uc === cc
      })()
      return matchCountry && matchContinent
    })
  }, [contest?.contestants, filterCountry, filterContinent])

  if (isLoading || pageLoading) {
    return <ContestDetailSkeleton />
  }

  if (!isAuthenticated || !user || !contest) {
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
  const isNomination = contest.contest.voting_type != null
  const hasNoContestants = filteredContestants.length === 0

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-950">
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          {/* Header with Back Button */}
          <div className="mb-6 flex items-center">
            <Button
              onClick={() => router.back()}
              variant="outline"
              className="text-sm sm:text-base text-myfav-primary border-myfav-primary/30 hover:bg-myfav-primary hover:text-white hover:border-myfav-primary transition-all duration-200 shadow-sm hover:shadow-md"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t('common.back')}
            </Button>
          </div>

          {/* Sticky Page Header - Desktop: se cache à droite, Mobile: se fixe en haut */}
          <StickyPageHeader
            title={contest.contest.name}
            subtitle={contest.contest.contest_type || undefined}
            onInfoClick={() => setShowInfoDialog(true)}
            infoTooltip={t('dashboard.contests.tooltip_info') || 'Voir les détails et les conditions du concours'}
          />

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
            className="mb-6 lg:mb-8"
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

          {/* Main Content Layout: Contestants with Sidebar */}
          <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8">
            {/* Contestants Cards - Left Side (2/3 width on large screens) */}
            <div className="lg:col-span-2 space-y-6">
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

                    {/* CTA Button */}
                    <Button
                      onClick={() => router.push(`/dashboard/contests/${contestId}/apply`)}
                      className="bg-myhigh5-primary hover:bg-myhigh5-blue-700 text-white font-semibold px-8 py-6 text-lg rounded-xl shadow-lg hover:shadow-xl transition-all duration-200 transform hover:scale-105"
                    >
                      {isNomination
                        ? (t('dashboard.contests.nominate') || 'Nommer')
                        : (t('dashboard.contests.participate') || 'Participer')
                      }
                      <ExternalLink className="w-5 h-5 ml-2" />
                    </Button>

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
                    // Le vote est géré dans ContestantCard, pas de redirection nécessaire
                  }}
                  onComment={() => { }}
                  onShare={() => { }}
                  onReport={handleReportClick}
                  onEdit={() => router.push(`/dashboard/contests/${contestId}/apply?edit=true`)}
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

            {/* Contestants Sidebar - Right Side */}
            <ContestantsSidebar
              contestants={locationFilteredContestants}
              contestId={contestId}
              onShowToast={showToast}
              filterCountry={filterCountry || undefined}
              filterContinent={filterContinent !== 'all' ? filterContinent : undefined}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
