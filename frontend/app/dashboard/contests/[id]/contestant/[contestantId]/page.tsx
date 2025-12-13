'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { ContestantDetailSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ContestantHeader, ContestantInfoCard } from '@/components/contestant'
import { MediaGallery, MediaViewerModal } from '@/components/media'
import { CommentsSection } from '@/components/comments'
import { CommentsSection as CommentsDialog } from '@/components/dashboard/comments-section'
import { ReactionsButton } from '@/components/dashboard/reactions-button'
import { CheckCircle, AlertCircle, Info, MessageCircle, Heart, ThumbsUp } from 'lucide-react'
import api from '@/lib/api'
import { commentsService, Comment as ServiceComment } from '@/lib/services/comments-service'
import { reactionsService, ReactionDetails } from '@/services/reactions-service'
import Image from 'next/image'
import * as React from 'react'

interface Media {
  id: string
  type: 'image' | 'video'
  url: string
  thumbnail?: string
}

interface Comment {
  id: string
  author_name: string
  author_avatar?: string
  text: string
  created_at: string
  target_type: 'contest' | 'photo' | 'video'
  target_id?: string
}

interface ContestantDetail {
  id: number
  title?: string
  description?: string
  author_name?: string
  author_country?: string
  author_city?: string
  author_continent?: string
  author_avatar_url?: string
  votes_count?: number
  images_count?: number
  videos_count?: number
  rank?: number
  image_media_ids?: string
  video_media_ids?: string
  is_qualified?: boolean
  registration_date?: string
  contest_title?: string
  contest_id?: number
  total_participants?: number
}

// Composant pour afficher une description tronquée avec popover au hover
function DescriptionWithPopover({ description, maxLength = 200 }: { description: string; maxLength?: number }) {
  const [isOpen, setIsOpen] = React.useState(false)
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null)
  const containerRef = React.useRef<HTMLDivElement>(null)

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

  if (!description || description.trim() === '') {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400 italic">
        Aucune description disponible
      </p>
    )
  }

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

export default function ContestantDetailPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const contestantId = params.contestantId as string
  const contestId = params.id as string

  const [contestant, setContestant] = useState<ContestantDetail | null>(null)
  const [pageLoading, setPageLoading] = useState(true)
  const [selectedMedia, setSelectedMedia] = useState<Media | null>(null)
  const [isFavorite, setIsFavorite] = useState(false)
  const [showInfoDialog, setShowInfoDialog] = useState(false)
  const [showCommentsDialog, setShowCommentsDialog] = useState(false)
  const [isVoting, setIsVoting] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [voters, setVoters] = useState<Array<{ user_id: number; username?: string; full_name?: string; avatar_url?: string }>>([])
  const [reactionDetails, setReactionDetails] = useState<ReactionDetails | null>(null)
  const [selectedReaction, setSelectedReaction] = useState<string | null>(null)
  const [reactionStats, setReactionStats] = useState<{ total_reactions: number; like_count: number; love_count: number } | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  // Charger les données du contestant
  useEffect(() => {
    const loadContestant = async () => {
      try {
        setPageLoading(true)
        setError(null)
        
        // Appel API pour récupérer les détails du contestant
        const response = await api.get(`/api/v1/contestants/${contestantId}`)
        const data = response.data
        
        setContestant(data)
        
        // Vérifier si c'est un favori
        try {
          const favResponse = await api.get(`/api/v1/favorites/contestants/${contestantId}/is-favorite`)
          setIsFavorite(favResponse.data.is_favorite)
        } catch (err) {
          console.error('Error checking favorite status:', err)
        }
      } catch (err) {
        console.error('Error loading contestant:', err)
        setError('Erreur lors du chargement des détails du contestant')
      } finally {
        setPageLoading(false)
      }
    }

    if (!isLoading && isAuthenticated && user && contestantId) {
      loadContestant()
    }
  }, [isLoading, isAuthenticated, user, contestantId])

  // Charger les commentaires du contestant
  useEffect(() => {
    const loadComments = async () => {
      try {
        const response = await commentsService.getContestantComments(contestantId)
        // getContestantComments retourne un CommentListResponse avec { comments, total, ... }
        // Convertir les commentaires du service vers le format de la page
        const convertedComments: Comment[] = (response.comments || []).map((c: ServiceComment) => ({
          id: String(c.id),
          author_name: c.author_name,
          author_avatar: c.author_avatar,
          text: c.text || c.content || '',
          created_at: c.created_at,
          target_type: c.target_type || 'contest',
          target_id: c.target_id
        }))
        setComments(convertedComments)
      } catch (err) {
        console.error('Error loading comments:', err)
        setComments([]) // En cas d'erreur, initialiser avec un tableau vide
      }
    }

    if (contestantId) {
      loadComments()
    }
  }, [contestantId])

  // Charger les votants et les réactions
  useEffect(() => {
    const loadVotersAndReactions = async () => {
      if (!contestantId) return

      try {
        // Charger les votants
        const votesResponse = await api.get(`/api/v1/contestants/${contestantId}/votes/details`)
        const votersData = votesResponse.data.voters || []
        setVoters(votersData.slice(0, 5)) // Prendre les 5 premiers

        // Charger les détails des réactions
        const reactionsResponse = await reactionsService.getReactionDetails(Number(contestantId))
        setReactionDetails(reactionsResponse)

        // Charger les stats de réactions
        const statsResponse = await reactionsService.getReactionStats(Number(contestantId))
        setReactionStats(statsResponse)
        setSelectedReaction(statsResponse.user_reaction || null)
      } catch (err) {
        console.error('Error loading voters and reactions:', err)
      }
    }

    if (contestantId) {
      loadVotersAndReactions()
    }
  }, [contestantId])

  const handleReactionSelect = async (reactionType: string) => {
    try {
      if (selectedReaction === reactionType) {
        // Supprimer la réaction
        await reactionsService.removeReaction(Number(contestantId))
        setSelectedReaction(null)
      } else {
        // Ajouter ou mettre à jour la réaction
        await reactionsService.addReaction(Number(contestantId), reactionType as 'like' | 'love' | 'wow' | 'dislike')
        setSelectedReaction(reactionType)
      }
      
      // Recharger les stats et détails
      const stats = await reactionsService.getReactionStats(Number(contestantId))
      setReactionStats(stats)
      const details = await reactionsService.getReactionDetails(Number(contestantId))
      setReactionDetails(details)
    } catch (error: any) {
      console.error('Error handling reaction:', error)
      setToast({
        type: 'error',
        message: error?.response?.data?.detail || 'Erreur lors de l\'ajout de la réaction'
      })
    }
  }

  const handleAddComment = async (text: string, targetType: 'contest' | 'photo' | 'video', targetId?: string) => {
    try {
      let newComment: Comment
      
      if (targetType === 'contest') {
        // Ajouter un commentaire au contestant
        const response = await commentsService.addContestantComment(contestantId, text)
        newComment = {
          id: String(response.id),
          author_name: response.author_name,
          author_avatar: response.author_avatar,
          text: response.text,
          created_at: response.created_at,
          target_type: targetType,
          target_id: targetId
        }
      } else {
        // Ajouter un commentaire à un média
        const response = await commentsService.addMediaComment(
          contestantId,
          targetType as 'photo' | 'video',
          targetId || '',
          text
        )
        newComment = {
          id: String(response.id),
          author_name: response.author_name,
          author_avatar: response.author_avatar,
          text: response.text,
          created_at: response.created_at,
          target_type: targetType,
          target_id: targetId
        }
      }

      setComments(prev => Array.isArray(prev) ? [newComment, ...prev] : [newComment])
      setToast({
        type: 'success',
        message: t('contestant_detail.comment_posted')
      })
    } catch (err) {
      console.error('Error posting comment:', err)
      setToast({
        type: 'error',
        message: t('contestant_detail.comment_error')
      })
    }
  }

  const handleVote = async () => {
    setIsVoting(true)
    try {
      const response = await api.post(`/api/v1/contestants/${contestant?.id}/vote`)
      
      if (contestant) {
        setContestant({
          ...contestant,
          votes_count: (contestant.votes_count || 0) + 1
        })
      }
      
      setToast({
        type: 'success',
        message: t('contestant_detail.vote_success')
      })
    } catch (error: any) {
      const errorDetail = error?.response?.data?.detail || ''
      
      // Détecter le type d'erreur et utiliser les traductions appropriées
      let errorMessage = t('dashboard.contests.vote_error') || t('contestant_detail.vote_error')
      
      if (errorDetail) {
        const errorLower = errorDetail.toLowerCase()
        
        if (errorLower.includes('vote') && errorLower.includes('ouvert')) {
          errorMessage = t('dashboard.contests.voting_not_open') || 'Le vote n\'est pas encore ouvert pour ce concours.'
        } else if (errorLower.includes('déjà voté') || errorLower.includes('already voted')) {
          errorMessage = t('dashboard.contests.already_voted_error') || 'Vous avez déjà voté pour ce participant.'
        } else if (errorLower.includes('propre candidature') || errorLower.includes('own entry')) {
          errorMessage = t('dashboard.contests.cannot_vote_own') || 'Vous ne pouvez pas voter pour votre propre candidature.'
        } else if (errorLower.includes('masculins') && errorLower.includes('féminines') && errorLower.includes('voter')) {
          errorMessage = t('dashboard.contests.vote_gender_restriction_male') || 'Ce concours est réservé aux participants masculins. Seules les participantes féminines peuvent voter.'
        } else if (errorLower.includes('féminines') && errorLower.includes('masculins') && errorLower.includes('voter')) {
          errorMessage = t('dashboard.contests.vote_gender_restriction_female') || 'Ce concours est réservé aux participantes féminines. Seuls les participants masculins peuvent voter.'
        } else if (errorLower.includes('genre') && errorLower.includes('voter')) {
          errorMessage = t('dashboard.contests.vote_gender_not_set') || 'Votre profil ne contient pas d\'information de genre. Veuillez compléter votre profil pour voter dans ce concours.'
        } else {
          // Utiliser le message d'erreur du backend s'il est disponible
          errorMessage = errorDetail
        }
      }
      
      setToast({
        type: 'error',
        message: errorMessage
      })
    } finally {
      setIsVoting(false)
    }
  }

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  if (isLoading || pageLoading) {
    return <ContestantDetailSkeleton />
  }

  if (!isAuthenticated || !user || !contestant) {
    return null
  }

  // Parser les médias depuis les IDs
  const parseMediaIds = (mediaIds: string | undefined, type: 'image' | 'video'): Media[] => {
    if (!mediaIds) return []
    try {
      const ids = JSON.parse(mediaIds)
      return ids.map((id: string, index: number) => ({
        id: `${type}-${index}`,
        type,
        url: id,
        thumbnail: undefined
      }))
    } catch {
      return []
    }
  }

  const images = parseMediaIds(contestant.image_media_ids, 'image')
  const videos = parseMediaIds(contestant.video_media_ids, 'video')
  const allMedia = [...images, ...videos]

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Hero Header */}
      <ContestantHeader
        author_name={contestant.author_name}
        author_country={contestant.author_country}
        author_city={contestant.author_city}
        author_continent={contestant.author_continent}
        author_avatar_url={contestant.author_avatar_url}
        votes_count={contestant.votes_count}
        rank={contestant.rank}
        total_participants={contestant.total_participants}
        isFavorite={isFavorite}
        coverImage={images.length > 0 ? images[0].url : undefined}
        onBack={() => router.back()}
        onFavoriteToggle={async () => {
          try {
            if (isFavorite) {
              await api.delete(`/api/v1/contestants/${contestantId}/favorite`)
              setIsFavorite(false)
              setToast({
                type: 'success',
                message: 'Retiré des favoris'
              })
            } else {
              await api.post(`/api/v1/contestants/${contestantId}/favorite`)
              setIsFavorite(true)
              setToast({
                type: 'success',
                message: 'Ajouté aux favoris'
              })
            }
          } catch (error: any) {
            console.error('Error toggling favorite:', error)
            setToast({
              type: 'error',
              message: error?.response?.data?.detail || 'Erreur lors de la modification des favoris'
            })
          }
        }}
      />

      {/* Stats Bar */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="container mx-auto px-4 md:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-around md:justify-start md:gap-12">
            <div className="text-center md:text-left">
              <p className="text-2xl md:text-3xl font-bold text-myfav-primary">
                {contestant.votes_count || 0}
              </p>
              <p className="text-xs md:text-sm text-gray-600 dark:text-gray-400">
                Votes
              </p>
            </div>
            <div className="text-center md:text-left">
              <p className="text-2xl md:text-3xl font-bold text-myfav-primary">
                {contestant.images_count || 0}
              </p>
              <p className="text-xs md:text-sm text-gray-600 dark:text-gray-400">
                Images
              </p>
            </div>
            <div className="text-center md:text-left">
              <p className="text-2xl md:text-3xl font-bold text-myfav-primary">
                {contestant.videos_count || 0}
              </p>
              <p className="text-xs md:text-sm text-gray-600 dark:text-gray-400">
                Vidéos
              </p>
            </div>
            {contestant.rank && (
              <div className="text-center md:text-left">
                <p className="text-2xl md:text-3xl font-bold text-myfav-primary">
                  #{contestant.rank}
                </p>
                <p className="text-xs md:text-sm text-gray-600 dark:text-gray-400">
                  Rang
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile Action Buttons */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 p-3 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 z-40 flex gap-2">
        <Button
          onClick={() => setShowCommentsDialog(true)}
          variant="outline"
          className="flex-1 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white"
        >
          <MessageCircle className="w-5 h-5 mr-2" />
          {t('contestant_detail.comments')} ({comments.length})
        </Button>
        <Button
          onClick={handleVote}
          disabled={isVoting}
          className="flex-1 bg-gradient-to-r from-myfav-primary to-myfav-primary-dark text-white font-bold py-3 text-base"
        >
          {isVoting ? t('contestant_detail.voting') : t('contestant_detail.vote')}
        </Button>
      </div>

      {/* Main Content */}
      <div className="py-6 md:py-8 pb-20 md:pb-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 lg:gap-6">
          {/* Left Column - Contest & Candidate Info (1/3) - Hidden on Mobile */}
          <div className="hidden lg:block lg:col-span-1">
            <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-200 dark:border-gray-700 sticky top-6 space-y-4">
              {/* Contest Info */}
              <div>
                <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-3">
                  {t('contestant_detail.contest_info')}
                </h3>
                <div className="space-y-2">
                  {contestant.contest_title && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">{t('contestant_detail.title')}</p>
                      <p className="text-xs text-gray-900 dark:text-white mt-1">{contestant.contest_title}</p>
                    </div>
                  )}
                  {contestant.total_participants && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">{t('contestant_detail.participants')}</p>
                      <p className="text-xs text-gray-900 dark:text-white mt-1">{contestant.total_participants}</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700"></div>

              {/* Candidate Info */}
              <div>
                <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-3">
                  {t('contestant_detail.candidate_info')}
                </h3>
                <div className="space-y-2">
                  {contestant.title && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">{t('contestant_detail.title')}</p>
                      <p className="text-xs text-gray-900 dark:text-white mt-1">{contestant.title}</p>
                    </div>
                  )}
                  
                  {contestant.registration_date && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">{t('contestant_detail.registered_on')}</p>
                      <p className="text-xs text-gray-900 dark:text-white mt-1">
                        {new Date(contestant.registration_date).toLocaleDateString('fr-FR')}
                      </p>
                    </div>
                  )}
                  
                  {contestant.is_qualified !== undefined && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">{t('contestant_detail.status')}</p>
                      <p className={`text-xs font-semibold mt-1 ${
                        contestant.is_qualified 
                          ? 'text-green-600 dark:text-green-400' 
                          : 'text-orange-600 dark:text-orange-400'
                      }`}>
                        {contestant.is_qualified ? t('contestant_detail.qualified') : t('contestant_detail.pending')}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700"></div>

              {/* Reactions Section */}
              <div>
                <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-3">
                  {t('dashboard.contests.reactions') || 'Réactions'}
                </h3>
                <ReactionsButton
                  contestantId={Number(contestantId)}
                  selectedReaction={selectedReaction}
                  onReactionSelect={handleReactionSelect}
                />
                
                {/* Reaction Stats */}
                {reactionStats && (
                  <div className="mt-3 flex items-center gap-3 text-xs">
                    {reactionStats.like_count > 0 && (
                      <div className="flex items-center gap-1">
                        <ThumbsUp className="w-3 h-3 text-blue-500" />
                        <span className="text-gray-600 dark:text-gray-400">{reactionStats.like_count}</span>
                      </div>
                    )}
                    {reactionStats.love_count > 0 && (
                      <div className="flex items-center gap-1">
                        <Heart className="w-3 h-3 text-red-500" />
                        <span className="text-gray-600 dark:text-gray-400">{reactionStats.love_count}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Users who liked/loved - Compact */}
                {reactionDetails && (
                  <div className="mt-3 space-y-2">
                    {/* Users who liked */}
                    {reactionDetails.reactions_by_type.like && reactionDetails.reactions_by_type.like.length > 0 && (
                      <div>
                        <div className="flex items-center gap-1 mb-1">
                          <ThumbsUp className="w-3 h-3 text-blue-500" />
                          <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                            {reactionDetails.reactions_by_type.like.length}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 flex-wrap">
                          {reactionDetails.reactions_by_type.like.slice(0, 5).map((user) => (
                            <div key={user.user_id} className="relative">
                              {user.avatar_url ? (
                                <Image
                                  src={user.avatar_url}
                                  alt={user.full_name || user.username || ''}
                                  width={24}
                                  height={24}
                                  className="rounded-full border border-blue-500 cursor-pointer hover:scale-110 transition-transform"
                                  title={user.full_name || user.username || ''}
                                />
                              ) : (
                                <div className="w-6 h-6 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center text-[10px] border border-blue-500 cursor-pointer hover:scale-110 transition-transform">
                                  {(user.full_name || user.username || 'U')[0].toUpperCase()}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Users who loved */}
                    {reactionDetails.reactions_by_type.love && reactionDetails.reactions_by_type.love.length > 0 && (
                      <div>
                        <div className="flex items-center gap-1 mb-1">
                          <Heart className="w-3 h-3 text-red-500" />
                          <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                            {reactionDetails.reactions_by_type.love.length}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 flex-wrap">
                          {reactionDetails.reactions_by_type.love.slice(0, 5).map((user) => (
                            <div key={user.user_id} className="relative">
                              {user.avatar_url ? (
                                <Image
                                  src={user.avatar_url}
                                  alt={user.full_name || user.username || ''}
                                  width={24}
                                  height={24}
                                  className="rounded-full border border-red-500 cursor-pointer hover:scale-110 transition-transform"
                                  title={user.full_name || user.username || ''}
                                />
                              ) : (
                                <div className="w-6 h-6 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center text-[10px] border border-red-500 cursor-pointer hover:scale-110 transition-transform">
                                  {(user.full_name || user.username || 'U')[0].toUpperCase()}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Top 5 Voters */}
                {voters.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <h4 className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-2">
                      {t('contestant_detail.vote_history') || 'Top Votants'}
                    </h4>
                    <div className="flex items-center gap-1 flex-wrap">
                      {voters.map((voter) => (
                        <div key={voter.user_id} className="relative">
                          {voter.avatar_url ? (
                            <Image
                              src={voter.avatar_url}
                              alt={voter.full_name || voter.username || ''}
                              width={24}
                              height={24}
                              className="rounded-full border border-myfav-primary cursor-pointer hover:scale-110 transition-transform"
                              title={voter.full_name || voter.username || ''}
                            />
                          ) : (
                            <div className="w-6 h-6 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center text-[10px] border border-myfav-primary cursor-pointer hover:scale-110 transition-transform">
                              {(voter.full_name || voter.username || 'V')[0].toUpperCase()}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700"></div>

              {/* Desktop Vote Button */}
              <Button
                onClick={handleVote}
                disabled={isVoting}
                className="w-full hidden md:block bg-gradient-to-r from-myfav-primary to-myfav-primary-dark text-white font-bold py-2 text-sm hover:shadow-lg transition-all"
              >
                {isVoting ? t('contestant_detail.voting') : t('contestant_detail.vote')}
              </Button>
            </div>
          </div>

          {/* Center Column - Media & Description (Full on Mobile, 2/3 on Desktop) */}
          <div className="col-span-1 lg:col-span-2 space-y-4">
            {/* Description */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-md">
              <div className="flex items-center justify-between gap-2 mb-3">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                  {t('contestant_detail.about')}
                </h2>
                {/* Info Button on Mobile */}
                <div className="lg:hidden relative">
                  <button
                    onClick={() => setShowInfoDialog(!showInfoDialog)}
                    className="flex-shrink-0 w-8 h-8 p-0 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-gray-300 dark:hover:bg-gray-600 rounded-lg flex items-center justify-center"
                    title="Détails"
                  >
                    <Info className="w-4 h-4" />
                  </button>
                  
                  {/* Info Popover */}
                  {showInfoDialog && (
                    <div
                      className="absolute top-full right-0 mt-2 bg-gradient-to-br from-white to-gray-50 dark:from-gray-800 dark:to-gray-900 rounded-xl p-5 w-72 border border-gray-200 dark:border-gray-700 shadow-xl z-50"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="space-y-4">
                        {/* Contest Info */}
                        <div className="bg-gradient-to-r from-myfav-primary/10 to-myfav-primary-dark/10 rounded-lg p-3 border border-myfav-primary/20">
                          <h3 className="text-xs font-bold text-myfav-primary uppercase mb-2 tracking-wide">
                            {t('contestant_detail.contest_info')}
                          </h3>
                          <div className="space-y-2">
                            {contestant?.contest_title && (
                              <div>
                                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                                  {t('contestant_detail.title')}
                                </p>
                                <p className="text-sm font-medium text-gray-900 dark:text-white">
                                  {contestant.contest_title}
                                </p>
                              </div>
                            )}
                            {contestant?.total_participants && (
                              <div>
                                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                                  {t('contestant_detail.participants')}
                                </p>
                                <p className="text-sm font-medium text-gray-900 dark:text-white">
                                  {contestant.total_participants}
                                </p>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Candidate Info */}
                        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-gray-700 dark:to-gray-800 rounded-lg p-3 border border-blue-200 dark:border-gray-600">
                          <h3 className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase mb-2 tracking-wide">
                            {t('contestant_detail.candidate_info')}
                          </h3>
                          <div className="space-y-2">
                            {contestant?.title && (
                              <div>
                                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                                  {t('contestant_detail.title')}
                                </p>
                                <p className="text-sm font-medium text-gray-900 dark:text-white">
                                  {contestant.title}
                                </p>
                              </div>
                            )}
                            {contestant?.registration_date && (
                              <div>
                                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                                  {t('contestant_detail.registered_on')}
                                </p>
                                <p className="text-sm font-medium text-gray-900 dark:text-white">
                                  {new Date(contestant.registration_date).toLocaleDateString('fr-FR')}
                                </p>
                              </div>
                            )}
                            {contestant?.is_qualified !== undefined && (
                              <div>
                                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                                  {t('contestant_detail.status')}
                                </p>
                                <div className="flex items-center gap-2">
                                  <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-semibold ${
                                    contestant.is_qualified
                                      ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                                      : 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400'
                                  }`}>
                                    {contestant.is_qualified ? '✓' : '⏳'} {contestant.is_qualified ? t('contestant_detail.qualified') : t('contestant_detail.pending')}
                                  </span>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <DescriptionWithPopover 
                description={contestant.description || ''}
                maxLength={200}
              />
            </div>

            {/* Media Gallery */}
            {allMedia.length > 0 && (
              <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-md">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
                  {t('contestant_detail.gallery')}
                </h2>
                <MediaGallery
                  images={images}
                  videos={videos}
                  onMediaSelect={setSelectedMedia}
                />
              </div>
            )}

            {/* Comments Section - Desktop (Same width as gallery, below gallery) */}
            <div className="hidden lg:block">
              <CommentsSection
                comments={comments}
                onAddComment={(text) => handleAddComment(text, 'contest')}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Media Viewer Modal */}
      <MediaViewerModal
        media={selectedMedia}
        allMedia={allMedia}
        onClose={() => setSelectedMedia(null)}
        onMediaChange={setSelectedMedia}
        comments={comments}
        onAddComment={(text) => handleAddComment(text, selectedMedia?.type === 'video' ? 'video' : 'photo', selectedMedia?.id)}
      />

      {/* Comments Dialog - Mobile */}
      <CommentsDialog
        contestantId={contestantId}
        initialCount={comments.length}
        isOpen={showCommentsDialog}
        onOpenChange={setShowCommentsDialog}
        onCountChange={(count) => {
          // Optionnel: mettre à jour le compteur si nécessaire
        }}
      />

      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-6 py-4 rounded-xl shadow-lg transition-all duration-300 ${
            toast.type === 'success'
              ? 'bg-green-500 dark:bg-green-600'
              : 'bg-red-500 dark:bg-red-600'
          } text-white`}
        >
          {toast.type === 'success' ? (
            <CheckCircle className="w-5 h-5 flex-shrink-0" />
          ) : (
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
          )}
          <p className="font-semibold">{toast.message}</p>
        </div>
      )}
    </div>
  )
}
