'use client'

import * as React from "react"
import { useState, useEffect } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useParams } from 'next/navigation'
import { ContestDetailSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Heart, ArrowLeft, HelpCircle, X, Search } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { ContestantCard } from '@/components/dashboard/contestant-card'
import { contestService, ContestResponse } from '@/services/contest-service'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

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
  avatar: string
  participationTitle?: string
  description: string
  votes: number
  rank?: number
  imagesCount: number
  videosCount: number
  canVote: boolean
  hasVoted: boolean
  media: Media[]
  comments: number
  reactions?: number
  favorites?: number
  isFavorite: boolean
}

interface ContestDetail {
  contest: ContestResponse
  contestants: Contestant[]
}

// Composant pour afficher une description tronquée avec popover au hover
function DescriptionWithPopover({ description, maxLength = 150 }: { description: string; maxLength?: number }) {
  const [isOpen, setIsOpen] = useState(false)
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null)
  const containerRef = React.useRef<HTMLDivElement>(null)
  const popoverRef = React.useRef<HTMLDivElement>(null)

  const shouldTruncate = description.length > maxLength
  const truncatedDescription = shouldTruncate ? description.substring(0, maxLength) + '...' : description

  const handleMouseEnter = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    setIsOpen(true)
  }

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setIsOpen(false)
    }, 200)
  }

  React.useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  if (!shouldTruncate) {
    return (
      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
        {description}
      </p>
    )
  }

  return (
    <div 
      ref={containerRef}
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed cursor-pointer hover:text-myfav-primary dark:hover:text-myfav-secondary transition-colors">
        {truncatedDescription}
      </p>
      
      {/* Popover */}
      {isOpen && (
        <div
          ref={popoverRef}
          className="absolute z-50 w-80 max-w-[90vw] max-h-[400px] overflow-y-auto bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-4 bottom-full left-0 mb-2"
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          <div className="space-y-2">
            <h4 className="font-semibold text-sm text-gray-900 dark:text-white">Description complète</h4>
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
              {description}
            </p>
          </div>
        </div>
      )}
    </div>
  )
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
        // Détails du contest
        const contestResponse = await contestService.getContestById(contestId)

        // Participants du contest
        const contestantsResponse = await contestService.getContestantsByContest(contestId, 0, 100)

        // Fonction pour parser les médias depuis image_media_ids et video_media_ids
        const parseMediaIds = (mediaIds: string | undefined, type: 'image' | 'video'): Media[] => {
          if (!mediaIds) {
            return []
          }
          
          // Si c'est déjà un tableau, l'utiliser directement
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
          
          // Sinon, essayer de parser comme JSON
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
          // Parser les images et vidéos
          const images = parseMediaIds(c.image_media_ids, 'image')
          const videos = parseMediaIds(c.video_media_ids, 'video')
          const allMedia = [...images, ...videos]

          // Log pour déboguer
          if (index === 0) {
            console.log('First contestant data:', {
              id: c.id,
              image_media_ids: c.image_media_ids,
              video_media_ids: c.video_media_ids,
              images_count: c.images_count,
              videos_count: c.videos_count,
              parsed_images: images,
              parsed_videos: videos,
              all_media: allMedia
            })
          }

          return {
            id: String(c.id ?? index),
            userId: c.user_id,
            name: c.author_name ?? `Contestant #${index + 1}`,
            country: c.author_country,
            city: c.author_city,
            avatar: c.author_avatar_url ?? '👤',
            participationTitle: c.title,
            description: c.description ?? '',
            votes: c.votes_count ?? 0,
            rank: c.rank,
            imagesCount: images.length,
            videosCount: videos.length,
            canVote: c.can_vote ?? false,
            hasVoted: c.has_voted ?? false,
            media: allMedia,
            comments: c.comments_count ?? 0,
            reactions: c.reactions_count ?? 0,
            favorites: c.favorites_count ?? 0,
            isFavorite: false,
          }
        })

        setContest({
          contest: contestResponse,
          contestants: mappedContestants,
        })

        // Charger les favoris depuis l'API
        try {
          const favoritesResponse = await contestService.getUserFavorites()
          const favoriteIds = favoritesResponse
            .filter((fav: any) => fav.season_id === contestResponse.id)
            .map((fav: any) => String(fav.id))
          setFavorites(favoriteIds)
        } catch (error) {
          console.error('Error loading favorites:', error)
        }
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
      
      // Recharger la liste des contestants
      const contestantsResponse = await contestService.getContestantsByContest(contestId, 0, 100)
      
      // Fonction pour parser les médias
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
          avatar: c.author_avatar_url || '',
          participationTitle: c.title || '',
          votes: c.votes_count || 0,
          rank: c.rank,
          imagesCount: c.images_count || 0,
          videosCount: c.videos_count || 0,
          canVote: c.can_vote || false,
          hasVoted: c.has_voted || false,
          isFavorite: favorites.includes(String(c.id)),
          media: allMedia,
          description: c.description || '',
          comments: c.comments_count || 0,
          reactions: c.reactions_count || 0,
          favorites: c.favorites_count || 0
        }
      })

      // Mettre à jour l'état avec les nouveaux contestants
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
      throw err // Re-throw pour que le dialog puisse gérer l'erreur
    }
  }

  const showToast = (message: string, type: 'success' | 'error' = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleToggleFavorite = async (contestantId: string) => {
    const isFavorite = favorites.includes(contestantId)
    
    try {
      if (isFavorite) {
        // Retirer des favoris
        await contestService.removeFromFavorites(parseInt(contestantId))
        setFavorites(prevFavorites => prevFavorites.filter(id => id !== contestantId))
        showToast('Contestant retiré des favoris', 'success')
      } else {
        // Ajouter aux favoris
        if (favorites.length >= 5) {
          showToast(t('dashboard.contests.favorite_limit_reached'), 'error')
          return
        }
        
        await contestService.addToFavorites(parseInt(contestantId))
        setFavorites(prevFavorites => [...prevFavorites, contestantId])
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

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'country':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      case 'continental':
        return 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
      case 'regional':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
      default:
        return 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'country':
        return t('dashboard.contests.country')
      case 'continental':
        return t('dashboard.contests.continental')
      case 'regional':
        return t('dashboard.contests.regional')
      default:
        return status
    }
  }

  const participantsCount = contest.contest.entries_count ?? contest.contestants.length

  // Filtrer les contestants selon la recherche
  const filteredContestants = contest ? contest.contestants.filter(contestant => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    return (
      contestant.name.toLowerCase().includes(query) ||
      contestant.participationTitle?.toLowerCase().includes(query) ||
      contestant.description.toLowerCase().includes(query) ||
      contestant.country?.toLowerCase().includes(query) ||
      contestant.city?.toLowerCase().includes(query)
    )
  }) : []

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50/30 to-purple-50/20 dark:from-slate-950 dark:via-blue-950/20 dark:to-purple-950/10 relative overflow-hidden">
      {/* Background Pattern */}
      <div className="absolute inset-0 bg-grid-slate-900/[0.04] dark:bg-grid-slate-400/[0.05] bg-[size:20px_20px] [mask-image:radial-gradient(ellipse_at_center,white,transparent)]" />
      
      <div className="relative z-10 px-4 py-6 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
          {/* Header with Back Button and Info Button */}
          <div className="mb-6 flex items-center justify-between">
          <Button
            onClick={() => router.back()}
            variant="outline"
            className="text-sm sm:text-base text-myfav-primary border-myfav-primary hover:bg-myfav-blue-50 dark:hover:bg-myfav-blue-900/20"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            {t('common.back')}
          </Button>
            
            {/* Info Button */}
            <Button
              onClick={() => setShowInfoDialog(true)}
              variant="outline"
              size="icon"
              className="rounded-full border-myfav-primary text-myfav-primary hover:bg-myfav-blue-50 dark:hover:bg-myfav-blue-900/20"
            >
              <HelpCircle className="w-5 h-5" />
          </Button>
        </div>

          {/* Contest Title - Sticky on Scroll */}
          <div className="sticky top-0 z-40 bg-gradient-to-br from-slate-50 via-blue-50/30 to-purple-50/20 dark:from-slate-950 dark:via-blue-950/20 dark:to-purple-950/10 backdrop-blur-sm border-b border-gray-200 dark:border-gray-800 mb-8 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-start justify-between gap-4 mb-4">
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold tracking-tight text-gray-900 dark:text-white">
            {contest.contest.name}
          </h1>
            </div>
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={`${getStatusColor(contest.contest.level)} border-0 text-xs font-semibold px-3 py-1`}>
              {getStatusLabel(contest.contest.level)}
            </Badge>
            <Badge
              className={`${
                contest.contest.is_submission_open
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                  : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                  } border-0 text-xs font-semibold px-3 py-1`}
            >
              {contest.contest.is_submission_open ? t('dashboard.contests.open') : t('dashboard.contests.closed')}
            </Badge>
          </div>
          
              {/* Search Bar */}
              <div className="relative w-full sm:w-auto sm:min-w-[300px]">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder={t('dashboard.contests.search_contestant') || 'Rechercher un participant...'}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary focus:border-transparent"
                />
              </div>
            </div>
        </div>

        {/* Toast Notification */}
        {toast && (
          <div className={`fixed bottom-4 right-4 rounded-lg shadow-lg p-4 z-50 animate-in fade-in slide-in-from-bottom-2 ${
            toast.type === 'success'
              ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
              : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
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

          {/* Info Dialog */}
          <Dialog open={showInfoDialog} onOpenChange={setShowInfoDialog}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="text-2xl font-bold">
                  {t('dashboard.contests.view_details')}
                </DialogTitle>
                <DialogDescription>
                  {contest.contest.name}
                </DialogDescription>
              </DialogHeader>

              {contest && (
                <div className="space-y-6 mt-4">
                {/* Contest Description */}
                  <div className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
                    <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2">
                      <span className="text-lg">📖</span> Description
                  </h3>
                    <DescriptionWithPopover 
                      description={contest.contest.description || t('dashboard.contests.no_description')}
                      maxLength={200}
                    />
                </div>

                  {/* Badges */}
                  <div className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
                    <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2">
                      <span className="text-lg">🏷️</span> Informations
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      <Badge className={`${getStatusColor(contest.contest.level)} border-0 text-xs font-semibold px-3 py-1`}>
                        {getStatusLabel(contest.contest.level)}
                      </Badge>
                      <Badge
                        className={`${
                          contest.contest.is_submission_open
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                            : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                        } border-0 text-xs font-semibold px-3 py-1`}
                      >
                        {contest.contest.is_submission_open ? t('dashboard.contests.open') : t('dashboard.contests.closed')}
                      </Badge>
                    </div>
                </div>

                {/* Stats */}
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 rounded-xl p-5 border border-blue-200 dark:border-blue-800">
                  <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
                    <span className="text-lg">📊</span> Statistiques
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('dashboard.contests.contestants')}</p>
                      <p className="text-2xl font-bold text-gray-900 dark:text-white">{participantsCount}</p>
                    </div>
                    <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('dashboard.contests.likes')}</p>
                      <p className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-1">
                        <Heart className="w-5 h-5 text-red-500" />
                        0
                      </p>
                    </div>
                  </div>
                </div>

                {/* Submission Period */}
                <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/30 rounded-xl p-5 border border-green-200 dark:border-green-800">
                  <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
                    <span className="text-lg">📝</span> {t('dashboard.contests.submission')}
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('dashboard.contests.start')}</p>
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">
                        {new Date(contest.contest.submission_start_date).toLocaleDateString('fr-FR', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric'
                        })}
                      </p>
                    </div>
                    <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('dashboard.contests.end')}</p>
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">
                        {new Date(contest.contest.submission_end_date).toLocaleDateString('fr-FR', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric'
                        })}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Voting Period */}
                <div className="bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-950/30 dark:to-pink-950/30 rounded-xl p-5 border border-purple-200 dark:border-purple-800">
                  <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
                    <span className="text-lg">🗳️</span> {t('dashboard.contests.voting')}
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('dashboard.contests.start')}</p>
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">
                        {new Date(contest.contest.voting_start_date).toLocaleDateString('fr-FR', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric'
                        })}
                      </p>
                    </div>
                    <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('dashboard.contests.end')}</p>
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">
                        {new Date(contest.contest.voting_end_date).toLocaleDateString('fr-FR', {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric'
                        })}
                      </p>
                    </div>
                  </div>
                </div>
                </div>
              )}
            </DialogContent>
          </Dialog>

          {/* Main Content Layout: Cards on Left, Sidebar on Right */}
          <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Contestants Cards - Left Side (2/3 width on large screens) */}
            <div className="lg:col-span-2">
              <div className="space-y-4 max-w-2xl">
                {filteredContestants.length > 0 ? (
                  filteredContestants.map(contestant => (
                  <ContestantCard
                    key={contestant.id}
                    id={contestant.id}
                    userId={contestant.userId}
                    currentUserId={user?.id}
                    contestId={contestId}
                    name={contestant.name}
                    country={contestant.country}
                    city={contestant.city}
                    avatar={contestant.avatar}
                    participationTitle={contestant.participationTitle}
                    votes={contestant.votes}
                    rank={contestant.rank}
                    imagesCount={contestant.imagesCount}
                    videosCount={contestant.videosCount}
                    canVote={contestant.canVote}
                    hasVoted={contestant.hasVoted}
                    isFavorite={favorites.includes(contestant.id)}
                    media={contestant.media}
                    description={contestant.description}
                    comments={contestant.comments}
                    onToggleFavorite={() => handleToggleFavorite(contestant.id)}
                    onViewDetails={() => router.push(`/dashboard/contests/${contestId}/contestant/${contestant.id}`)}
                    onVote={() => router.push(`/dashboard/contests/${contestId}/contestant/${contestant.id}`)}
                    onComment={() => {
                      // Le dialog des commentaires est géré dans ContestantCard
                    }}
                    onShare={() => {
                      // Le dialog de partage est géré dans ContestantCard
                    }}
                    onReport={() => {
                      // TODO: Implement report functionality
                      showToast('Fonctionnalité de signalement à venir', 'success')
                    }}
                    onEdit={() => {
                      router.push(`/dashboard/contests/${contestId}/participate?edit=true`)
                    }}
                    onDelete={async () => {
                      await handleDeleteContestant(contestant.id)
                    }}
                  />
                  ))
                ) : (
                  <div className="text-center py-12">
                    <div className="flex flex-col items-center gap-3">
                      <p className="text-5xl mb-2">🏆</p>
                      <p className="text-lg font-semibold text-gray-700 dark:text-gray-300">
                        {searchQuery 
                          ? t('dashboard.contests.no_contestants_found') || 'Aucun participant trouvé'
                          : t('dashboard.contests.no_contestants') || 'Aucun participant pour le moment'}
                      </p>
                      {!searchQuery && (
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {t('dashboard.contests.participate') || 'Soyez le premier à participer !'}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Contest Info Sidebar - Right Side (1/3 width on large screens, hidden on mobile) */}
            <div className="hidden lg:block lg:col-span-1">
              <div className="sticky top-6">
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6">
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
                    {contest.contest.name}
                  </h3>
                  
                  {/* Contest Description */}
                  <div className="mb-6">
                    <h4 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-2">
                      Description
                    </h4>
                    <DescriptionWithPopover 
                      description={contest.contest.description || t('dashboard.contests.no_description')}
                      maxLength={150}
                    />
                  </div>

                  {/* Stats */}
                  <div className="mb-6">
                    <h4 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3">
                      Statistiques
                    </h4>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600 dark:text-gray-400">{t('dashboard.contests.contestants')}</span>
                        <span className="text-lg font-bold text-gray-900 dark:text-white">{participantsCount}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600 dark:text-gray-400">{t('dashboard.contests.likes')}</span>
                        <span className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-1">
                          <Heart className="w-4 h-4 text-red-500" />
                          0
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Badges */}
                  <div className="mb-6">
                    <div className="flex flex-wrap gap-2">
                      <Badge className={`${getStatusColor(contest.contest.level)} border-0 text-xs font-semibold px-3 py-1`}>
                        {getStatusLabel(contest.contest.level)}
                      </Badge>
                      <Badge
                        className={`${
                          contest.contest.is_submission_open
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                            : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                        } border-0 text-xs font-semibold px-3 py-1`}
                      >
                        {contest.contest.is_submission_open ? t('dashboard.contests.open') : t('dashboard.contests.closed')}
                      </Badge>
                    </div>
                  </div>

                  {/* Submission Period */}
                  <div className="mb-6">
                    <h4 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3">
                      {t('dashboard.contests.submission')}
                    </h4>
                    <div className="space-y-2 text-sm">
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">{t('dashboard.contests.start')}: </span>
                        <span className="font-semibold text-gray-900 dark:text-white">
                          {new Date(contest.contest.submission_start_date).toLocaleDateString('fr-FR', {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric'
                          })}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">{t('dashboard.contests.end')}: </span>
                        <span className="font-semibold text-gray-900 dark:text-white">
                          {new Date(contest.contest.submission_end_date).toLocaleDateString('fr-FR', {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric'
                          })}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Voting Period */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3">
                      {t('dashboard.contests.voting')}
                    </h4>
                    <div className="space-y-2 text-sm">
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">{t('dashboard.contests.start')}: </span>
                        <span className="font-semibold text-gray-900 dark:text-white">
                          {new Date(contest.contest.voting_start_date).toLocaleDateString('fr-FR', {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric'
                          })}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">{t('dashboard.contests.end')}: </span>
                        <span className="font-semibold text-gray-900 dark:text-white">
                          {new Date(contest.contest.voting_end_date).toLocaleDateString('fr-FR', {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric'
                          })}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              </div>
            </div>
        </div>
      </div>
    </div>
  )
}
