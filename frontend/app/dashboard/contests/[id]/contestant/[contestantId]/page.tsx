'use client'

import { useEffect, useState, Suspense } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { ContestantDetailSkeleton } from '@/components/ui/skeleton'
import { cleanVideoUrl } from '@/lib/utils/video-platforms'
import { Button } from '@/components/ui/button'
import { ContestantHeader } from '@/components/contestant'
import { MediaGallery, MediaViewerModal } from '@/components/media'
import { VideoEmbed } from '@/components/ui/video-embed'
import { CommentsSection } from '@/components/comments'
import { CommentsSection as CommentsDialog } from '@/components/dashboard/comments-section'
import { ContestantStatsBar } from '@/components/dashboard/contestant-stats-bar'
import { HoverInfoDialog } from '@/components/dashboard/hover-info-dialog'
import { ContestantDescription } from '@/components/dashboard/contestant-description'
import { ContestantInfoSidebar } from '@/components/dashboard/contestant-info-sidebar'
import { ContestantMobileActions } from '@/components/dashboard/contestant-mobile-actions'
import { ContestantMobileInfoDialog } from '@/components/dashboard/contestant-mobile-info-dialog'
import { ToastNotification } from '@/components/dashboard/toast-notification'
import { ShareDialog } from '@/components/dashboard/share-dialog'
import { Info } from 'lucide-react'
import api from '@/lib/api'
import { commentsService, Comment as ServiceComment } from '@/lib/services/comments-service'
import { reactionsService, ReactionDetails } from '@/services/reactions-service'
import { followService } from '@/services/follow-service'
import { sharesService } from '@/services/shares-service'

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
  user_id?: number
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
  contest_category?: string
  contest_id?: number
  entry_type?: string
  nominator_city?: string
  nominator_country?: string
  total_participants?: number
  favorites_count?: number
  reactions_count?: number
  comments_count?: number
  shares_count?: number
  has_voted?: boolean
  can_vote?: boolean
  vote_restriction_reason?: string | null
}


function ContestantDetailContent() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const contestantId = params.contestantId as string
  const contestId = params.id as string

  const [contestant, setContestant] = useState<ContestantDetail | null>(null)
  const [contestMode, setContestMode] = useState<string | null>(null)
  const [pageLoading, setPageLoading] = useState(true)
  const [selectedMedia, setSelectedMedia] = useState<Media | null>(null)
  const [isFavorite, setIsFavorite] = useState(false)
  const [showInfoDialog, setShowInfoDialog] = useState(false)
  const [showCommentsDialog, setShowCommentsDialog] = useState(false)
  const [isVoting, setIsVoting] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [isFollowing, setIsFollowing] = useState(false)
  const [isFollowLoading, setIsFollowLoading] = useState(false)
  const [followersCount, setFollowersCount] = useState<number | null>(null)
  const [voters, setVoters] = useState<Array<{ id?: number; user_id: number; username?: string; full_name?: string; avatar_url?: string; vote_date?: string; contest_id?: number; season_id?: number }>>([])
  const [reactionDetails, setReactionDetails] = useState<ReactionDetails | null>(null)
  const [selectedReaction, setSelectedReaction] = useState<string | null>(null)
  const [reactionStats, setReactionStats] = useState<{ total_reactions: number; like_count: number; love_count: number } | null>(null)
  const [favoritesList, setFavoritesList] = useState<Array<{ id?: number; user_id: number; username?: string; full_name?: string; avatar_url?: string; added_date?: string }>>([])
  const [sharesList, setSharesList] = useState<Array<{ id: number; user_id?: number; username?: string; full_name?: string; avatar_url?: string; platform?: string; created_at?: string }>>([])
  const [hoveredElement, setHoveredElement] = useState<{ type: 'votes' | 'reactions' | 'favorites' | 'shares'; data?: any } | null>(null)
  const [hoverTimeout, setHoverTimeout] = useState<NodeJS.Timeout | null>(null)
  const [showShareDialog, setShowShareDialog] = useState(false)
  const [shareLink, setShareLink] = useState('')

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

        // Fetch contest mode to reliably detect nomination vs participation
        try {
          const contestRes = await api.get(`/api/v1/contests/${data.contest_id || contestId}`)
          setContestMode(contestRes.data?.contest_mode || contestRes.data?.entry_type || null)
        } catch { /* ignore, fallback to other checks */ }

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

  useEffect(() => {
    const loadFollowStatus = async () => {
      try {
        if (user?.id && contestant?.user_id && user.id !== contestant.user_id) {
          const following = await followService.getFollowing(user.id, 0, 100)
          setIsFollowing(following.some(f => f.id === contestant.user_id))
        }
      } catch (err) {
        console.error('Error loading follow status:', err)
      }

      if (!contestant?.user_id) {
        return
      }

      try {
        const followers = await followService.getFollowers(contestant.user_id, 0, 100)
        setFollowersCount(followers.length)
      } catch (err) {
        console.error('Error loading followers count:', err)
      }
    }

    if (contestant?.user_id && user?.id) {
      loadFollowStatus()
    }
  }, [contestant?.user_id, user?.id])

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

  // Charger les votants, réactions, favoris et partages
  useEffect(() => {
    const loadDetails = async () => {
      if (!contestantId || !contestant) return

      try {
        // Charger les votants (seulement si l'utilisateur est l'auteur)
        if (user?.id === contestant.user_id) {
          try {
            const votesResponse = await api.get(`/api/v1/contestants/${contestantId}/votes/details`)
            const votersData = votesResponse.data.voters || []
            setVoters(votersData)
          } catch (err) {
            console.error('Error loading voters:', err)
          }
        }

        // Charger les détails des réactions (seulement si l'utilisateur est l'auteur)
        if (user?.id === contestant.user_id) {
          try {
            const reactionsResponse = await reactionsService.getReactionDetails(Number(contestantId))
            setReactionDetails(reactionsResponse)
          } catch (err) {
            console.error('Error loading reaction details:', err)
          }
        }

        // Charger les stats de réactions
        try {
          const statsResponse = await reactionsService.getReactionStats(Number(contestantId))
          setReactionStats(statsResponse)
          setSelectedReaction(statsResponse.user_reaction || null)
        } catch (err) {
          console.error('Error loading reaction stats:', err)
        }

        // Charger les favoris (seulement si l'utilisateur est l'auteur)
        if (user?.id === contestant.user_id) {
          try {
            const favoritesResponse = await api.get(`/api/v1/contestants/${contestantId}/favorites/details`)
            const favoritesData = favoritesResponse.data.users || []
            setFavoritesList(favoritesData)
          } catch (err) {
            console.error('Error loading favorites:', err)
          }
        }

        // Charger les partages
        try {
          const sharesResponse = await api.get(`/api/v1/contestants/${contestantId}/shares`)
          const sharesData = sharesResponse.data.shares || []
          setSharesList(sharesData)
        } catch (err) {
          console.error('Error loading shares:', err)
        }
      } catch (err) {
        console.error('Error loading details:', err)
      }
    }

    if (contestantId && contestant && user) {
      loadDetails()
    }
  }, [contestantId, contestant, user])

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
    if (!contestant?.can_vote || isVoting || contestant?.has_voted) return

    setIsVoting(true)
    try {
      const response = await api.post(`/api/v1/contestants/${contestant?.id}/vote`)

      // Recharger les données du contestant pour avoir les stats à jour
      const updatedResponse = await api.get(`/api/v1/contestants/${contestantId}`)
      setContestant(updatedResponse.data)

      // Recharger les votants si l'utilisateur est l'auteur
      if (user?.id === contestant?.user_id) {
        try {
          const votesResponse = await api.get(`/api/v1/contestants/${contestantId}/votes/details`)
          setVoters(votesResponse.data.voters || [])
        } catch (err) {
          console.error('Error reloading voters:', err)
        }
      }

      setToast({
        type: 'success',
        message: t('contestant_detail.vote_success') || 'Vote enregistré avec succès!'
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

  const handleFollowToggle = async () => {
    if (!contestant?.user_id || !user?.id || contestant.user_id === user.id) return

    setIsFollowLoading(true)
    try {
      if (isFollowing) {
        await followService.unfollowUser(contestant.user_id)
        setIsFollowing(false)
        setToast({
          type: 'success',
          message: t('dashboard.following.unfollow') || 'Unfollowed'
        })
      } else {
        await followService.followUser(contestant.user_id)
        setIsFollowing(true)
        setToast({
          type: 'success',
          message: t('dashboard.following.follow') || 'Followed'
        })
      }
    } catch (error: any) {
      console.error('Error updating follow status:', error)
      setToast({
        type: 'error',
        message: error?.response?.data?.detail || t('common.error') || 'Error'
      })
    } finally {
      setIsFollowLoading(false)
    }
  }

  const handleMessage = () => {
    if (!contestant?.user_id || contestant.user_id === user?.id) return
    router.push(`/dashboard/messages?user=${contestant.user_id}`)
  }

  const handleShare = async () => {
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''
    const refCode = (user as any)?.personal_referral_code || ''
    const link = `${baseUrl}/c/${contestantId}${refCode ? `?ref=${encodeURIComponent(refCode)}` : ''}`
    setShareLink(link)
    setShowShareDialog(true)

    try {
      await sharesService.shareContestant(
        Number(contestantId),
        link,
        undefined,
        user?.id,
        refCode || undefined
      )
    } catch (error) {
      console.error('Error recording share:', error)
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
        url: cleanVideoUrl(id) || id,
        thumbnail: undefined
      }))
    } catch {
      return []
    }
  }

  const images = parseMediaIds(contestant.image_media_ids, 'image')
  const videos = parseMediaIds(contestant.video_media_ids, 'video')
  const allMedia = [...images, ...videos]
  // Detect nomination using all available signals (URL param, API fields, contest mode)
  const urlEntryType = searchParams.get('entryType')
  const isNomination =
    urlEntryType === 'nomination' ||
    contestant.entry_type === 'nomination' ||
    contestMode === 'nomination' ||
    !!contestant.nominator_country ||
    !!contestant.nominator_city
  const nominationLabel = contestant.contest_category || contestant.contest_title

  return (
    <div className="min-h-screen ">
      {/* Hero Header */}
      <ContestantHeader
        author_name={contestant.author_name}
        author_country={contestant.author_country}
        author_city={contestant.author_city}
        author_continent={contestant.author_continent}
        author_avatar_url={contestant.author_avatar_url}
        votes_count={contestant.votes_count}
        followersCount={followersCount}
        rank={contestant.rank}
        total_participants={contestant.total_participants}
        titlePrefix={isNomination ? (t('contestant_detail.nominator_label') || 'Nominator') : (t('contestant_detail.contestant_label') || 'Contestant')}
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
        showActions={!!contestant.user_id}
        isSelf={user?.id === contestant.user_id}
        isFollowing={isFollowing}
        isFollowLoading={isFollowLoading}
        onFollowToggle={handleFollowToggle}
        onMessage={handleMessage}
      />

      {/* Stats Bar */}
      <ContestantStatsBar
        votes={contestant.votes_count || 0}
        images={contestant.images_count || 0}
        videos={contestant.videos_count || 0}
        rank={contestant.rank}
        comments={contestant.comments_count || comments.length}
        reactions={contestant.reactions_count || 0}
        favorites={contestant.favorites_count || 0}
        shares={contestant.shares_count || 0}
        onVotesClick={() => {
          if (user?.id === contestant.user_id && voters.length > 0) {
            setHoveredElement({ type: 'votes', data: voters })
          }
        }}
        onCommentsClick={() => setShowCommentsDialog(true)}
        onReactionsClick={() => {
          if (user?.id === contestant.user_id && reactionDetails) {
            setHoveredElement({ type: 'reactions', data: reactionDetails })
          }
        }}
        onFavoritesClick={() => {
          if (user?.id === contestant.user_id && favoritesList.length > 0) {
            setHoveredElement({ type: 'favorites', data: favoritesList })
          }
        }}
        onSharesClick={() => {
          if (sharesList.length > 0) {
            setHoveredElement({ type: 'shares', data: sharesList })
          }
        }}
      />

      {/* Mobile Action Buttons */}
      <ContestantMobileActions
        commentsCount={comments.length}
        hasVoted={contestant.has_voted || false}
        canVote={contestant.can_vote || false}
        isVoting={isVoting}
        onCommentsClick={() => setShowCommentsDialog(true)}
        onVote={handleVote}
        onShare={handleShare}
        isAuthor={user?.id === contestant.user_id}
        voteRestrictionReason={contestant.vote_restriction_reason}
        showActions={!!contestant.user_id}
        isSelf={user?.id === contestant.user_id}
        isFollowing={isFollowing}
        isFollowLoading={isFollowLoading}
        onFollowToggle={handleFollowToggle}
        onMessage={handleMessage}
      />

      {/* Main Content */}
      <div className="py-8 md:py-12 pb-24 md:pb-12">
        <div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-2 lg:gap-8">
            {/* Left Column - Contest & Candidate Info (1/3) - Hidden on Mobile */}
            <div className="hidden lg:block lg:col-span-1">
              <ContestantInfoSidebar
                candidateTitle={contestant.title}
                registrationDate={contestant.registration_date}
                followersCount={followersCount}
                isAuthor={user?.id === contestant.user_id}
                contestantId={Number(contestantId)}
                selectedReaction={selectedReaction}
                onReactionSelect={handleReactionSelect}
                reactionDetails={reactionDetails}
                voters={voters}
                hasVoted={contestant.has_voted || false}
                canVote={contestant.can_vote || false}
                isVoting={isVoting}
                onVote={handleVote}
                voteRestrictionReason={contestant.vote_restriction_reason}
                showActions={!!contestant.user_id}
                isSelf={user?.id === contestant.user_id}
                isFollowing={isFollowing}
                isFollowLoading={isFollowLoading}
                onFollowToggle={handleFollowToggle}
                onMessage={handleMessage}
                onShare={handleShare}
              />
            </div>

            {/* Center Column - Media & Description (Full on Mobile, 2/3 on Desktop) */}
            <div className="col-span-1 lg:col-span-2 space-y-6">
              {/* Description */}
              <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-3xl p-6 md:p-8 shadow-lg border border-gray-100 dark:border-gray-700/50 hover:shadow-xl transition-all duration-300">
                <div className="flex items-center justify-between gap-2 mb-4">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    {t('contestant_detail.about')}
                  </h2>
                  {/* Info Button on Mobile */}
                  <div className="lg:hidden">
                    <button
                      onClick={() => setShowInfoDialog(!showInfoDialog)}
                      className="flex-shrink-0 w-9 h-9 p-0 bg-gray-100 dark:bg-gray-700/50 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-xl flex items-center justify-center transition-all duration-200"
                      title="Détails"
                    >
                      <Info className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* For nominations: show which contest/category they are nominating for */}
                {isNomination && nominationLabel && (
                  <div className="mb-4 flex items-center gap-2 px-4 py-2.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-xl">
                    <span className="text-blue-500 dark:text-blue-400 text-sm font-medium whitespace-nowrap">
                      {t('contestant_detail.nominated_for') || 'Nominated for:'}
                    </span>
                    <span className="text-blue-700 dark:text-blue-300 text-sm font-semibold">
                      {nominationLabel}
                    </span>
                  </div>
                )}

                <ContestantDescription
                  description={contestant.description || ''}
                  maxLength={200}
                />
              </div>

              {/* Media: Video embed for nominations, Gallery for participations */}
              {isNomination && videos.length > 0 ? (
                <div className="rounded-2xl overflow-hidden shadow-lg">
                  <div className="aspect-video w-full">
                    <VideoEmbed
                      url={videos[0].url}
                      className="w-full h-full"
                      allowFullscreen={true}
                    />
                  </div>
                </div>
              ) : allMedia.length > 0 && (
                <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-3xl p-6 md:p-8 shadow-lg border border-gray-100 dark:border-gray-700/50 hover:shadow-xl transition-all duration-300">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">
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

      {/* Mobile Info Dialog */}
      <ContestantMobileInfoDialog
        isOpen={showInfoDialog}
        onClose={() => setShowInfoDialog(false)}
        contestTitle={nominationLabel || contestant.contest_title}
        totalParticipants={contestant.total_participants}
        candidateTitle={contestant.title}
        registrationDate={contestant.registration_date}
        followersCount={followersCount}
        isQualified={contestant.is_qualified}
      />

      {/* Hover Info Dialog */}
      {hoveredElement && (
        <HoverInfoDialog
          type={hoveredElement.type}
          data={hoveredElement.data}
          onClose={() => setHoveredElement(null)}
        />
      )}

      {/* Toast Notification */}
      {toast && (
        <ToastNotification
          type={toast.type}
          message={toast.message}
        />
      )}

      {/* Share Dialog */}
      <ShareDialog
        isOpen={showShareDialog}
        onOpenChange={setShowShareDialog}
        shareLink={shareLink}
        title={contestant.title || contestant.author_name}
        description={contestant.description}
      />
    </div>
  )
}

export default function ContestantDetailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen" />}>
      <ContestantDetailContent />
    </Suspense>
  )
}
