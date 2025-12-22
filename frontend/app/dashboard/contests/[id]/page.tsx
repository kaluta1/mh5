'use client'

import * as React from "react"
import { useState, useEffect } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useParams } from 'next/navigation'
import { ContestDetailSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from 'lucide-react'
import { contestService, ContestResponse } from '@/services/contest-service'
import { ContestDetailsHeader } from '@/components/dashboard/contest-details-header'
import { ContestInfoDialog } from '@/components/dashboard/contest-info-dialog'
import { ContestantsList } from '@/components/dashboard/contestants-list'
import { ContestantsSidebar } from '@/components/dashboard/contestants-sidebar'
import { HoverInfoDialog } from '@/components/dashboard/hover-info-dialog'

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

  // Redirection si non authentifié
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  // Charger les détails du contest depuis le backend
  useEffect(() => {
    const loadContest = async () => {
      try {
        const contestResponse = await contestService.getContestById(contestId)
        const contestantsResponse = (contestResponse as any).contestants || []

        const parseMediaIds = (mediaIds: string | undefined, type: 'image' | 'video'): Media[] => {
          if (!mediaIds) {
            return []
          }
          
          if (Array.isArray(mediaIds)) {
            const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
            return mediaIds
              .filter((url: string) => url && url.trim() !== '')
              .map((url: string, index: number) => {
                let fullUrl = url
                if (url && !url.startsWith('http') && !url.startsWith('data:')) {
                  if (url.startsWith('/')) {
                    fullUrl = `${API_BASE_URL}${url}`
                  } else {
                    fullUrl = `${API_BASE_URL}/${url}`
                  }
                }
                return {
                  id: `${type}-${index}`,
                  type,
                  url: fullUrl,
                  thumbnail: type === 'video' ? fullUrl : undefined
                }
              })
          }
          
          try {
            const parsed = typeof mediaIds === 'string' ? JSON.parse(mediaIds) : mediaIds
            if (!Array.isArray(parsed)) {
              return []
            }
            
            const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
            
            return parsed
              .filter((url: string) => url && url.trim() !== '')
              .map((url: string, index: number) => {
                let fullUrl = url
                if (url && !url.startsWith('http') && !url.startsWith('data:')) {
                  if (url.startsWith('/')) {
                    fullUrl = `${API_BASE_URL}${url}`
                  } else {
                    fullUrl = `${API_BASE_URL}/${url}`
                  }
                }
                return {
                  id: `${type}-${index}`,
                  type,
                  url: fullUrl,
                  thumbnail: type === 'video' ? fullUrl : undefined
                }
              })
          } catch (error) {
            console.error(`Error parsing ${type} media IDs:`, error, 'Raw value:', mediaIds)
            return []
          }
        }

        const mappedContestants: Contestant[] = contestantsResponse.map((c: any, index: number) => {
          const images = parseMediaIds(c.image_media_ids, 'image')
          const videos = parseMediaIds(c.video_media_ids, 'video')
          const allMedia = [...images, ...videos]

          return {
            id: String(c.id ?? index),
            userId: c.user_id,
            name: c.author_name ?? `Contestant #${index + 1}`,
            country: c.author_country,
            city: c.author_city,
            continent: c.author_continent,
            region: c.author_region,
            avatar: c.author_avatar_url ?? '👤',
            participationTitle: c.title,
            description: c.description ?? '',
            votes: c.votes_count ?? 0,
            rank: c.rank,
            imagesCount: c.images_count ?? images.length,
            videosCount: c.videos_count ?? videos.length,
            canVote: c.can_vote ?? false,
            hasVoted: c.has_voted ?? false,
            voteRestrictionReason: c.vote_restriction_reason ?? null,
            media: allMedia,
            comments: c.comments_count ?? 0,
            reactions: c.reactions_count ?? 0,
            favorites: c.favorites_count ?? 0,
            shares: c.shares_count ?? 0,
            isFavorite: c.is_in_favorites ?? false,
            votesList: c.votes || [],
            commentsList: c.comments || [],
            reactionsList: c.reactions || {},
            favoritesList: c.favorites || [],
            sharesList: c.shares || [],
            season: c.season,
          }
        })

        mappedContestants.sort((a, b) => {
          if (a.rank && b.rank) {
            return a.rank - b.rank
          }
          if (a.rank && !b.rank) return -1
          if (!a.rank && b.rank) return 1
          if (b.votes !== a.votes) {
            return b.votes - a.votes
          }
          return Number(a.id) - Number(b.id)
        })

        setContest({
          contest: contestResponse,
          contestants: mappedContestants,
        })

        const favoriteIds = mappedContestants
          .filter(c => c.isFavorite)
          .map(c => c.id)
          setFavorites(favoriteIds)
      } catch (error) {
        console.error('Error loading contest:', error)
      } finally {
        setPageLoading(false)
      }
    }

    if (!isLoading && isAuthenticated && user) {
      loadContest()
    }
  }, [isLoading, isAuthenticated, user, contestId])

  const handleDeleteContestant = async (contestantId: string) => {
    try {
      await contestService.deleteContestant(Number(contestantId))
      
      const contestResponse = await contestService.getContestById(contestId)
      const contestantsResponse = (contestResponse as any).contestants || []
      
      const parseMediaIds = (mediaIds: string | undefined, type: 'image' | 'video'): Media[] => {
        if (!mediaIds) return []
        
        if (Array.isArray(mediaIds)) {
          const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          return mediaIds
            .filter((url: string) => url && url.trim() !== '')
            .map((url: string, index: number) => {
              let fullUrl = url
              if (url && !url.startsWith('http') && !url.startsWith('data:')) {
                if (url.startsWith('/')) {
                  fullUrl = `${API_BASE_URL}${url}`
                } else {
                  fullUrl = `${API_BASE_URL}/${url}`
                }
              }
              return {
                id: `${type}-${index}`,
                type,
                url: fullUrl,
                thumbnail: type === 'video' ? fullUrl : undefined
              }
            })
        }
        
        try {
          const parsed = typeof mediaIds === 'string' ? JSON.parse(mediaIds) : mediaIds
          if (!Array.isArray(parsed)) {
            return []
          }
          
          const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          
          return parsed
            .filter((url: string) => url && url.trim() !== '')
            .map((url: string, index: number) => {
              let fullUrl = url
              if (url && !url.startsWith('http') && !url.startsWith('data:')) {
                if (url.startsWith('/')) {
                  fullUrl = `${API_BASE_URL}${url}`
                } else {
                  fullUrl = `${API_BASE_URL}/${url}`
                }
              }
              return {
                id: `${type}-${index}`,
                type,
                url: fullUrl,
                thumbnail: type === 'video' ? fullUrl : undefined
              }
            })
        } catch (error) {
          console.error(`Error parsing ${type} media IDs:`, error)
          return []
        }
      }

      const mappedContestants: Contestant[] = contestantsResponse.map((c: any) => {
        const images = parseMediaIds(c.image_media_ids, 'image')
        const videos = parseMediaIds(c.video_media_ids, 'video')
        const allMedia = [...images, ...videos]

        return {
          id: String(c.id),
          userId: c.user_id,
          name: c.author_name || 'Utilisateur inconnu',
          country: c.author_country,
          city: c.author_city,
          continent: c.author_continent,
          region: c.author_region,
          avatar: c.author_avatar_url || '',
          participationTitle: c.title || '',
          description: c.description || '',
          votes: c.votes_count || 0,
          rank: c.rank,
          imagesCount: c.images_count ?? images.length,
          videosCount: c.videos_count ?? videos.length,
          canVote: c.can_vote || false,
          hasVoted: c.has_voted || false,
          isFavorite: c.is_in_favorites ?? false,
          media: allMedia,
          comments: c.comments_count || 0,
          reactions: c.reactions_count || 0,
          favorites: c.favorites_count || 0,
          shares: c.shares_count || 0,
          votesList: c.votes || [],
          commentsList: c.comments || [],
          reactionsList: c.reactions || {},
          favoritesList: c.favorites || [],
          sharesList: c.shares || [],
          season: c.season,
        }
      })

      mappedContestants.sort((a, b) => {
        if (a.rank && b.rank) {
          return a.rank - b.rank
        }
        if (a.rank && !b.rank) return -1
        if (!a.rank && b.rank) return 1
        if (b.votes !== a.votes) {
          return b.votes - a.votes
        }
        return Number(a.id) - Number(b.id)
      })

      setContest((prev) => {
        if (!prev) return null
        return {
          ...prev,
          contestants: mappedContestants
        }
      })

      showToast(t('common.deleted_successfully') || 'Candidature supprimée avec succès', 'success')
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

  const filteredContestants = contest.contestants.filter(contestant => {
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
          
          {/* Contest Details Header */}
          <ContestDetailsHeader
            contest={contest.contest}
            participantsCount={participantsCount}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onInfoClick={() => setShowInfoDialog(true)}
          />

        {/* Toast Notification */}
        {toast && (
          <div className={`fixed bottom-4 right-4 rounded-xl shadow-xl p-4 z-50 animate-in fade-in slide-in-from-bottom-2 backdrop-blur-sm ${
            toast.type === 'success'
              ? 'bg-green-50/95 dark:bg-green-900/30 border border-green-200 dark:border-green-800'
              : 'bg-red-50/95 dark:bg-red-900/30 border border-red-200 dark:border-red-800'
          }`}>
            <p className={`text-sm font-medium ${
              toast.type === 'success'
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
              <ContestantsList
                contestants={filteredContestants}
                contestId={contestId}
                    currentUserId={user?.id}
                favorites={favorites}
                searchQuery={searchQuery}
                formatLocation={formatLocation}
                onToggleFavorite={handleToggleFavorite}
                onViewDetails={(contestantId) => router.push(`/dashboard/contests/${contestId}/contestant/${contestantId}`)}
                onVote={() => {
                  // Le vote est géré dans ContestantCard, pas de redirection nécessaire
                }}
                onComment={() => {}}
                onShare={() => {}}
                onReport={() => showToast('Fonctionnalité de signalement à venir', 'success')}
                onEdit={() => router.push(`/dashboard/contests/${contestId}/participate?edit=true`)}
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
            </div>

            {/* Contestants Sidebar - Right Side */}
            <ContestantsSidebar
              contestants={contest.contestants}
              contestId={contestId}
              onShowToast={showToast}
            />
            </div>
        </div>
      </div>
    </div>
  )
}
