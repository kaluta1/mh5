'use client'

import { useRouter } from 'next/navigation'
import { useState, useEffect, useRef } from 'react'
import * as React from 'react'
import { Play, ChevronLeft, ChevronRight, Clock, Info, Lock, ThumbsUp } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { VideoPreviewDialog } from '@/components/ui/video-preview-dialog'
import { MediaViewerModal } from '@/components/media/media-viewer-modal'
import { VideoEmbed } from '@/components/ui/video-embed'
import { detectVideoPlatform, convertToEmbedUrl } from '@/lib/utils/video-platforms'
import { htmlToPlainText } from '@/lib/utils'
import { contestService } from '@/services/contest-service'
import { reactionsService } from '@/services/reactions-service'
import { sharesService } from '@/services/shares-service'
import { useToast } from '@/components/ui/toast'
import { VoteButton } from './vote-button'
import { FavoriteButton } from './favorite-button'
import { ReactionsButton } from './reactions-button'
import { CommentsButton } from './comments-button'
import { ContestantDescription } from './contestant-description'
import { CommentsSection } from './comments-section'
import { AuthorPopover } from './author-popover'
import { ShareDialog } from './share-dialog'
import { ContestantActionsMenu } from './contestant-actions-menu'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

// Composant pour afficher une description tronquée avec popover au hover
function DescriptionWithPopover({ description, maxLength = 150 }: { description: string; maxLength?: number }) {
  const { t } = useLanguage()
  const [isOpen, setIsOpen] = useState(false)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const plainText = description ? htmlToPlainText(description) : ''
  const shouldTruncate = plainText.length > maxLength
  const truncatedDescription = shouldTruncate ? plainText.substring(0, maxLength) + '...' : plainText

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
    return null
  }

  if (!shouldTruncate) {
    return (
      <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words">{plainText}</p>
    )
  }

  return (
    <div
      ref={containerRef}
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words cursor-pointer hover:text-myhigh5-primary dark:hover:text-myhigh5-secondary transition-colors">
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
            <h4 className="font-semibold text-sm text-gray-900 dark:text-white">
              {t('contestant_detail.full_description') || 'Full description'}
            </h4>
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap break-words">{plainText}</p>
          </div>
        </div>
      )}
    </div>


  )
}

interface Media {
  id: string
  type: 'image' | 'video'
  url: string
  thumbnail?: string
}

interface ContestantCardProps {
  id: string
  userId?: number
  currentUserId?: number
  name: string
  country?: string
  city?: string
  continent?: string
  region?: string
  locationDisplay?: string
  avatar: string
  participationTitle?: string
  votes: number
  totalPoints?: number
  isVotingOpenForRound?: boolean
  rank?: number
  imagesCount?: number
  videosCount?: number
  canVote?: boolean
  hasVoted?: boolean
  hasReported?: boolean
  voteRestrictionReason?: string | null
  isFavorite: boolean
  media: Media[]
  description: string
  comments: number
  reactions?: number
  favorites?: number
  votesList?: Array<any>
  reactionsList?: { [key: string]: Array<any> }
  favoritesList?: Array<any>
  contestId?: string
  onToggleFavorite: () => void
  onViewDetails: () => void
  onVote: () => void
  onComment?: () => void
  onShare?: () => void
  onReport?: () => void
  onEdit?: () => void
  onDelete?: () => void | Promise<void>
  onHoverAuthor?: () => void
  onHoverEnd?: () => void
  onHoverDescription?: () => void
  onHoverVotes?: () => void
  onHoverReactions?: () => void
  onHoverFavorites?: () => void
}

export function ContestantCard({
  id,
  userId,
  currentUserId,
  name,
  country,
  city,
  continent,
  region,
  locationDisplay,
  avatar,
  participationTitle,
  votes,
  totalPoints = 0,
  isVotingOpenForRound = true,
  rank,
  imagesCount = 0,
  videosCount = 0,
  canVote = false,
  hasVoted = false,
  hasReported = false,
  voteRestrictionReason,
  isFavorite,
  media,
  description,
  comments,
  reactions = 0,
  favorites: favoritesCount = 0,
  votesList = [],
  reactionsList = {},
  favoritesList = [],
  contestId,
  onToggleFavorite,
  onViewDetails,
  onVote,
  onComment,
  onShare,
  onReport,
  onEdit,
  onDelete,
  onHoverAuthor,
  onHoverEnd,
  onHoverDescription,
  onHoverVotes,
  onHoverReactions,
  onHoverFavorites
}: ContestantCardProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const { user } = useAuth()
  const [showVideoDialog, setShowVideoDialog] = useState(false)
  const [selectedVideo, setSelectedVideo] = useState<Media | null>(null)
  const [isLiked, setIsLiked] = useState(hasVoted)
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [showMediaViewer, setShowMediaViewer] = useState(false)
  const [selectedMedia, setSelectedMedia] = useState<Media | null>(null)
  const [showShareDialog, setShowShareDialog] = useState(false)
  const [shareLink, setShareLink] = useState('')
  const router = useRouter()
  const [showCommentsDialog, setShowCommentsDialog] = useState(false)
  const [isVoting, setIsVoting] = useState(false)
  const [currentVotes, setCurrentVotes] = useState(votes)

  // Sync from server when switching cards; never clear optimistic "voted" on refetch noise (same id).
  useEffect(() => {
    setIsLiked(hasVoted)
  }, [id])

  useEffect(() => {
    if (hasVoted) setIsLiked(true)
  }, [hasVoted])

  useEffect(() => {
    setCurrentVotes(votes)
  }, [votes])
  
  // Override canVote si le round n'est pas en phase de vote
  const effectiveCanVote = isVotingOpenForRound ? canVote : false
  const effectiveVoteRestrictionReason = !isVotingOpenForRound ? 'voting_not_open' : voteRestrictionReason
  const userHasVotedThisContestant = isLiked || !!hasVoted
  const voteButtonCanVote = effectiveCanVote && !userHasVotedThisContestant
  const [currentComments, setCurrentComments] = useState(comments)
  const [selectedReaction, setSelectedReaction] = useState<string | null>(null)
  const [reactionsCount, setReactionsCount] = useState(reactions || 0)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  // Charger les stats de réactions au montage
  useEffect(() => {
    const loadReactionStats = async () => {
      try {
        const stats = await reactionsService.getReactionStats(Number(id))
        setReactionsCount(stats.total_reactions)
        if (stats.user_reaction) {
          setSelectedReaction(stats.user_reaction)
        }
      } catch (error) {
        console.error('Error loading reaction stats:', error)
      }
    }
    loadReactionStats()
  }, [id])

  const isAuthor = userId && currentUserId && userId === currentUserId

  const images = media.filter(m => m.type === 'image')
  const videos = media.filter(m => m.type === 'video')
  const firstVideo = videos[0]
  const allMedia = [...images, ...videos]

  // Log pour déboguer
  useEffect(() => {
    if (id === '1' || id === '2') {
      console.log(`[ContestantCard] Contestant ${id} - Media data:`, {
        media,
        images,
        videos,
        firstVideo,
        allMedia,
        imagesCount,
        videosCount
      })
    }
  }, [id, media, images, videos, firstVideo, allMedia, imagesCount, videosCount])

  const handleVideoClick = (video: Media) => {
    setSelectedVideo(video)
    setShowVideoDialog(true)
  }

  const handleMediaClick = (clickedMedia: Media) => {
    setSelectedMedia(clickedMedia)
    setShowMediaViewer(true)
  }

  const handleMediaChange = (newMedia: Media) => {
    setSelectedMedia(newMedia)
  }

  const handleVote = async () => {
    if (!voteButtonCanVote || isVoting) return

    try {
      setIsVoting(true)
      const cid =
        contestId != null && contestId !== ''
          ? parseInt(String(contestId), 10)
          : undefined
      const result = await contestService.voteForContestant(Number(id), {
        contestId: cid && !Number.isNaN(cid) ? cid : undefined,
      })

      if (result.success) {
        setIsLiked(true)
        setCurrentVotes(prev => prev + 1)
        addToast(t('dashboard.contests.vote_success') || 'Vote enregistré avec succès!', 'success')
        onVote()
      } else if (result.code === 'max_votes_reached') {
        // Replace 5th vote automatically (no confirmation)
        await contestService.replaceVote(Number(id), cid && !Number.isNaN(cid) ? cid : undefined)
        setIsLiked(true)
        setCurrentVotes(prev => prev + 1)
        addToast(t('dashboard.contests.vote_replaced') || 'Vote enregistré (remplace le 5e choix).', 'success')
        onVote()
      } else if (result.code === 'already_voted') {
        addToast(t('dashboard.contests.already_voted_error') || 'Vous avez déjà voté pour ce participant.', 'info')
      }
    } catch (error: any) {
      console.error('Error voting:', error)
      const errorMessage = error.response?.data?.detail || ''
      const errorStr = typeof errorMessage === 'string' ? errorMessage : (errorMessage.message || '')

      let toastMessage = t('dashboard.contests.vote_error') || 'Erreur lors du vote. Veuillez réessayer.'
      const errorLower = errorStr.toLowerCase()

      if ((errorLower.includes('vote') && errorLower.includes('ouvert')) || errorLower.includes('not started yet') || errorLower.includes('has ended') || errorLower.includes('voting is not open')) {
        toastMessage = t('dashboard.contests.voting_not_open') || 'Le vote n\'est pas encore ouvert pour ce concours.'
      } else if (errorLower.includes('propre candidature') || errorLower.includes('own')) {
        toastMessage = t('dashboard.contests.cannot_vote_own') || 'Vous ne pouvez pas voter pour votre propre candidature.'
      } else if (errorLower.includes('gender') || errorLower.includes('genre')) {
        toastMessage = t('dashboard.contests.vote_gender_not_set') || 'Veuillez compléter votre profil pour voter.'
      } else if (errorStr) {
        toastMessage = errorStr
      }

      addToast(toastMessage, 'error')
    } finally {
      setIsVoting(false)
    }
  }

  const handleReaction = async (reactionType: string) => {
    try {
      // Si la même réaction est sélectionnée, on la supprime
      if (selectedReaction === reactionType) {
        await reactionsService.removeReaction(Number(id))
        setSelectedReaction(null)
        addToast(t('dashboard.contests.reaction_removed') || 'Réaction supprimée', 'success')
      } else {
        // Sinon, on ajoute ou met à jour la réaction
        await reactionsService.addReaction(Number(id), reactionType as 'like' | 'love' | 'wow' | 'dislike')
        setSelectedReaction(reactionType)
        const reactionLabels: Record<string, string> = {
          like: t('dashboard.contests.like') || 'J\'aime',
          love: t('dashboard.contests.love') || 'J\'adore',
          wow: t('dashboard.contests.wow') || 'Wow',
          dislike: t('dashboard.contests.dislike') || 'Je n\'aime pas'
        }
        addToast(
          `${t('dashboard.contests.reaction_added') || 'Réaction ajoutée'}: ${reactionLabels[reactionType] || reactionType}`,
          'success'
        )
      }
      // Recharger les stats
      const stats = await reactionsService.getReactionStats(Number(id))
      setReactionsCount(stats.total_reactions)
    } catch (error: any) {
      console.error('Error handling reaction:', error)
      addToast(error.response?.data?.detail || 'Erreur lors de l\'ajout de la réaction', 'error')
    }
  }

  const handleOpenComments = () => {
    setShowCommentsDialog(true)
  }

  const handleDelete = () => {
    setShowDeleteDialog(true)
  }

  const handleShare = async () => {
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''
    const sharePath = `/c/${id}`
    const shareUrl = new URL(`${baseUrl}${sharePath}`)

    const referralCode = user?.personal_referral_code
    const shareLinkStr = shareUrl.toString()
    setShareLink(shareLinkStr)
    setShowShareDialog(true)

    // Enregistrer le partage dans la base de données avec le referral code
    try {
      await sharesService.shareContestant(
        Number(id),
        shareLinkStr,
        undefined, // platform sera détecté automatiquement si possible
        currentUserId,
        referralCode || undefined
      )
    } catch (error: any) {
      console.error('Error recording share:', error)
      // Ne pas bloquer l'utilisateur si l'enregistrement échoue
    }

    if (onShare) onShare()
  }

  const nextImage = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (images.length > 0) {
      setCurrentImageIndex((prev) => (prev + 1) % images.length)
    }
  }

  const prevImage = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (images.length > 0) {
      setCurrentImageIndex((prev) => (prev - 1 + images.length) % images.length)
    }
  }

  return (
    <>
      {/* Modern Post Card */}
      <div className="bg-white dark:bg-gray-800/90 rounded-2xl border border-gray-200/60 dark:border-gray-700/50 shadow-sm hover:shadow-lg transition-all duration-300 overflow-hidden flex flex-col h-full">
        {/* Header */}
        <div className="p-3 pb-2 border-b border-gray-100 dark:border-gray-700/30">
          <div className="flex items-start justify-between">
            {participationTitle && (
              <h4
                onClick={(e) => {
                  e.stopPropagation()
                  onViewDetails()
                }}
                className="text-sm font-bold text-gray-900 dark:text-white hover:text-myhigh5-primary dark:hover:text-white transition-colors cursor-pointer flex-1 line-clamp-2"
              >
                {participationTitle}
              </h4>
            )}

            {/* Actions Menu */}
            <ContestantActionsMenu
              isAuthor={isAuthor}
              isFavorite={isFavorite}
              hasReported={hasReported}
              onEdit={onEdit}
              onDelete={handleDelete}
              onToggleFavorite={onToggleFavorite}
              onShare={handleShare}
              onReport={!hasReported && !isAuthor ? onReport : undefined}
            />
          </div>
        </div>

        {/* Media - Video or Image Carousel */}
        {firstVideo ? (
          <div className="w-full">
            <div
              className="relative w-full bg-black overflow-hidden cursor-pointer group"
              onClick={() => handleVideoClick(firstVideo)}
            >
              {/* Video Container - Larger size */}
              <div className="relative w-full aspect-video">
                {detectVideoPlatform(firstVideo.url) === 'direct' ? (
                  <>
                    <video
                      src={firstVideo.url}
                      className="w-full h-full object-cover"
                      poster={firstVideo.thumbnail}
                    />
                    <div className="absolute inset-0 bg-black/20 group-hover:bg-black/30 transition-all flex items-center justify-center">
                      <div className="w-20 h-20 rounded-full bg-white/90 dark:bg-gray-800/90 flex items-center justify-center group-hover:scale-110 transition-transform shadow-lg">
                        <Play className="w-10 h-10 text-myhigh5-primary ml-1" fill="currentColor" />
                      </div>
                    </div>
                  </>
                ) : (() => {
                  const _platform = detectVideoPlatform(firstVideo.url)
                  const _info = convertToEmbedUrl(firstVideo.url)
                  // YouTube: use thumbnail, others: gradient placeholder
                  const _ytThumb = _platform === 'youtube' && _info?.videoId
                    ? `https://img.youtube.com/vi/${_info.videoId}/hqdefault.jpg`
                    : null
                  const _platformLabels: Record<string, string> = {
                    tiktok: 'TikTok', youtube: 'YouTube', instagram: 'Instagram',
                    vimeo: 'Vimeo', facebook: 'Facebook', snapchat: 'Snapchat'
                  }
                  const _platformColors: Record<string, string> = {
                    tiktok: 'from-gray-900 via-gray-800 to-gray-900',
                    youtube: 'from-red-900 via-red-800 to-red-900',
                    instagram: 'from-purple-900 via-pink-800 to-orange-900',
                    vimeo: 'from-blue-900 via-blue-800 to-blue-900',
                    facebook: 'from-blue-900 via-blue-800 to-blue-900',
                    snapchat: 'from-yellow-900 via-yellow-800 to-yellow-900',
                  }
                  return (
                    <div className="relative w-full h-full">
                      {_ytThumb ? (
                        <img src={_ytThumb} alt="Video thumbnail" className="w-full h-full object-cover" />
                      ) : (
                        <div className={`w-full h-full bg-gradient-to-br ${_platformColors[_platform] || 'from-gray-800 to-gray-900'} flex items-center justify-center`}>
                          <div className="text-center">
                            <div className="text-4xl mb-2 opacity-30">▶</div>
                            <span className="text-white/40 text-xs font-medium uppercase tracking-wider">{_platformLabels[_platform] || 'Vidéo'}</span>
                          </div>
                        </div>
                      )}
                      {/* Play overlay */}
                      <div className="absolute inset-0 bg-black/30 group-hover:bg-black/40 transition-all flex items-center justify-center">
                        <div className="w-16 h-16 rounded-full bg-white/90 dark:bg-gray-800/90 flex items-center justify-center group-hover:scale-110 transition-transform shadow-lg">
                          <Play className="w-8 h-8 text-myhigh5-primary ml-0.5" fill="currentColor" />
                        </div>
                      </div>
                      {/* Platform badge */}
                      <div className="absolute top-3 left-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-semibold text-white shadow-md ${
                          _platform === 'tiktok' ? 'bg-black' :
                          _platform === 'youtube' ? 'bg-red-600' :
                          _platform === 'instagram' ? 'bg-gradient-to-r from-purple-600 via-pink-500 to-orange-400' :
                          _platform === 'vimeo' ? 'bg-blue-500' :
                          _platform === 'facebook' ? 'bg-blue-600' :
                          'bg-gray-700'
                        }`}>
                          {_platformLabels[_platform] || 'Vidéo'}
                        </span>
                      </div>
                    </div>
                  )
                })()}
              </div>
            </div>
          </div>
        ) : images.length > 0 && (
          <div className="w-full">
            <div
              className="relative w-full bg-gray-100 dark:bg-gray-900 overflow-hidden group cursor-pointer"
              onClick={() => handleMediaClick(images[currentImageIndex])}
            >
              {/* Current Image - Smaller size with 16:9 aspect ratio */}
              <div className="relative w-full aspect-[16/9]">
                <img
                  src={images[currentImageIndex].url}
                  alt={`${name} - Image ${currentImageIndex + 1}`}
                  className="w-full h-full object-cover"
                />

                {/* Navigation Arrows - Show on hover */}
                {images.length > 1 && (
                  <>
                    <button
                      onClick={prevImage}
                      className="absolute left-2 top-1/2 -translate-y-1/2 p-2 rounded-full bg-black/50 hover:bg-black/70 text-white opacity-0 group-hover:opacity-100 transition-opacity z-10"
                      aria-label="Image précédente"
                    >
                      <ChevronLeft className="w-5 h-5" />
                    </button>
                    <button
                      onClick={nextImage}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-full bg-black/50 hover:bg-black/70 text-white opacity-0 group-hover:opacity-100 transition-opacity z-10"
                      aria-label="Image suivante"
                    >
                      <ChevronRight className="w-5 h-5" />
                    </button>
                  </>
                )}

                {/* Image Counter */}
                {images.length > 1 && (
                  <div className="absolute bottom-2 right-2 bg-black/60 text-white text-xs px-2 py-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
                    {currentImageIndex + 1} / {images.length}
                  </div>
                )}

                {/* Dots Indicator */}
                {images.length > 1 && (
                  <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1.5">
                    {images.map((_, idx) => (
                      <button
                        key={idx}
                        onClick={(e) => {
                          e.stopPropagation()
                          setCurrentImageIndex(idx)
                        }}
                        className={`w-1.5 h-1.5 rounded-full transition-all ${idx === currentImageIndex
                            ? 'bg-white w-4'
                            : 'bg-white/50 hover:bg-white/75'
                          }`}
                        aria-label={`Aller à l'image ${idx + 1}`}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Author and Description - Moved to bottom */}
        <div className="px-4 sm:px-5 pt-3 sm:pt-4 pb-3">
          <div className="flex items-start gap-3 mb-3">
            {/* Avatar */}
            <div className="flex-shrink-0 relative cursor-pointer" onClick={() => userId && router.push(`/dashboard/users/${userId}`)}>
              {avatar && avatar !== '/default-avatar.png' && (avatar.startsWith('http') || avatar.startsWith('/')) ? (
                <div className="w-10 h-10 rounded-full overflow-hidden bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary ring-2 ring-gray-200 dark:ring-gray-700 hover:ring-myhigh5-primary transition-all">
                  <img
                    src={avatar}
                    alt=""
                    className="w-full h-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                </div>
              ) : (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center ring-2 ring-gray-200 dark:ring-gray-700 hover:ring-myhigh5-primary transition-all flex-shrink-0">
                  <span className="text-sm font-bold text-white">{name?.split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase() || '?'}</span>
                </div>
              )}

            </div>

            {/* Name and Location */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <h3
                        className="text-sm font-semibold text-gray-900 dark:text-white hover:text-myhigh5-primary dark:hover:text-myhigh5-primary-light transition-colors cursor-pointer truncate"
                        onClick={() => userId && router.push(`/dashboard/users/${userId}`)}
                        onMouseEnter={onHoverAuthor}
                        onMouseLeave={onHoverEnd}
                      >
                        {name}
                      </h3>
                    </TooltipTrigger>
                    <TooltipContent className="bg-white text-gray-900 border-gray-200 shadow-lg dark:bg-gray-800 dark:text-white dark:border-gray-700">
                      <p className="text-xs">{t('dashboard.contests.tooltip_author') || 'Voir le profil du participant'}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>

              </div>
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-gray-400"></span>
                {locationDisplay || [country, city].filter(Boolean).join(' · ') || t('dashboard.contests.participant') || 'Participant'}
              </p>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <p
                      className="text-xs text-gray-500 dark:text-gray-500 mt-1 cursor-help hover:text-myhigh5-primary"
                      onMouseEnter={currentUserId === userId ? onHoverVotes : undefined}
                      onMouseLeave={currentUserId === userId ? onHoverEnd : undefined}
                    >
                      {totalPoints} pts
                    </p>
                  </TooltipTrigger>
                  <TooltipContent className="bg-white text-gray-900 border-gray-200 shadow-lg dark:bg-gray-800 dark:text-white dark:border-gray-700">
                    <p className="text-xs">
                      {currentUserId === userId
                        ? (t('dashboard.contests.tooltip_votes_author') || `${currentVotes} vote${currentVotes > 1 ? 's' : ''} reçu${currentVotes > 1 ? 's' : ''}. Survolez pour voir la liste.`)
                        : (t('dashboard.contests.tooltip_votes') || `${currentVotes} vote${currentVotes > 1 ? 's' : ''} reçu${currentVotes > 1 ? 's' : ''} au total`)}
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>

            </div>
          </div>

          {/* Description */}
          <div className="mt-1">
            <ContestantDescription description={description} maxLength={60} />
          </div>
        </div>

        {/* Vote Status Banner */}
        {!effectiveCanVote && effectiveVoteRestrictionReason && currentUserId && currentUserId !== userId && (
          <div className={`mx-4 mb-2 rounded-xl px-3.5 py-2.5 flex items-start gap-2.5 text-sm ${
            voteRestrictionReason === 'voting_not_open'
              ? 'bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800/50'
              : voteRestrictionReason === 'already_voted'
              ? 'bg-green-50 dark:bg-green-950/40 border border-green-200 dark:border-green-800/50'
              : 'bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/50'
          }`}>
            {voteRestrictionReason === 'voting_not_open' ? (
              <Clock className="w-4 h-4 text-blue-500 dark:text-blue-400 flex-shrink-0 mt-0.5" />
            ) : voteRestrictionReason === 'already_voted' ? (
              <ThumbsUp className="w-4 h-4 text-green-500 dark:text-green-400 flex-shrink-0 mt-0.5 fill-current" />
            ) : (
              <Info className="w-4 h-4 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <p className={`text-xs font-medium leading-relaxed ${
                voteRestrictionReason === 'voting_not_open'
                  ? 'text-blue-700 dark:text-blue-300'
                  : voteRestrictionReason === 'already_voted'
                  ? 'text-green-700 dark:text-green-300'
                  : 'text-amber-700 dark:text-amber-300'
              }`}>
                {(() => {
                  switch (voteRestrictionReason) {
                    case 'voting_not_open':
                      return t('dashboard.contests.voting_not_open') || "Le vote n'est pas encore ouvert pour ce concours."
                    case 'already_voted':
                      return t('dashboard.contests.already_voted_message') || "Vous avez d\u00e9j\u00e0 vot\u00e9 pour ce participant."
                    case 'own_contestant':
                      return t('dashboard.contests.restriction_own_contestant_desc') || 'Vous ne pouvez pas voter pour votre propre candidature.'
                    case 'not_authenticated':
                      return t('dashboard.contests.restriction_not_authenticated_desc') || 'Veuillez vous connecter pour voter.'
                    case 'different_city':
                      return t('dashboard.contests.restriction_different_city_desc') || 'Vous ne pouvez voter que pour les candidats de votre ville.'
                    case 'different_country':
                      return t('dashboard.contests.restriction_different_country_desc') || 'Vous ne pouvez voter que pour les candidats de votre pays.'
                    case 'different_region':
                      return t('dashboard.contests.restriction_different_region_desc') || 'Vous ne pouvez voter que pour les candidats de votre r\u00e9gion.'
                    case 'different_continent':
                      return t('dashboard.contests.restriction_different_continent_desc') || 'Vous ne pouvez voter que pour les candidats de votre continent.'
                    case 'geographic_restriction':
                      return t('dashboard.contests.restriction_geographic_desc') || 'Restriction g\u00e9ographique.'
                    default:
                      return t('dashboard.contests.cannot_vote') || 'Le vote est indisponible.'
                  }
                })()}
              </p>
            </div>
          </div>
        )}

        {/* Action Buttons - Facebook Style with Counts */}
        <div className="px-1 border-t border-gray-100 dark:border-gray-700/30">
          <div className="grid grid-cols-4">
            <div
              onMouseEnter={currentUserId === userId ? onHoverVotes : undefined}
              onMouseLeave={currentUserId === userId ? onHoverEnd : undefined}
            >
              <VoteButton
                contestantId={Number(id)}
                canVote={voteButtonCanVote}
                hasVoted={userHasVotedThisContestant}
                isVoting={isVoting}
                onVote={handleVote}
                isAuthor={currentUserId === userId}
                votesCount={currentVotes}
                voteRestrictionReason={effectiveVoteRestrictionReason}
              />
            </div>
            <CommentsButton
              onClick={handleOpenComments}
              commentsCount={currentComments}
            />
            <div
              onMouseEnter={currentUserId === userId ? onHoverReactions : undefined}
              onMouseLeave={currentUserId === userId ? onHoverEnd : undefined}
            >
              <ReactionsButton
                contestantId={Number(id)}
                selectedReaction={selectedReaction}
                onReactionSelect={handleReaction}
                isAuthor={currentUserId === userId}
                reactionsCount={reactionsCount}
                onReactionSuccess={() => {
                  // Les stats sont déjà rechargées dans handleReaction
                }}
              />
            </div>
            <div
              onMouseEnter={currentUserId === userId ? onHoverFavorites : undefined}
              onMouseLeave={currentUserId === userId ? onHoverEnd : undefined}
            >
              <FavoriteButton
                contestantId={Number(id)}
                isFavorite={isFavorite}
                onToggle={onToggleFavorite}
                isAuthor={currentUserId === userId}
                favoritesCount={favoritesCount}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Video Preview Dialog */}
      {selectedVideo && (
        <VideoPreviewDialog
          isOpen={showVideoDialog}
          videoUrl={selectedVideo.url}
          videoTitle={participationTitle || name}
          onClose={() => {
            setShowVideoDialog(false)
            setSelectedVideo(null)
          }}
          canVote={voteButtonCanVote}
          hasVoted={userHasVotedThisContestant}
          isVoting={isVoting}
          isAuthor={currentUserId === userId}
          votesCount={currentVotes}
          onVote={handleVote}
          voteRestrictionReason={effectiveVoteRestrictionReason}
          authorName={name}
          authorAvatar={avatar}
          rank={rank}
          contestantId={id}
          commentsCount={currentComments}
        />
      )}

      {/* Media Viewer Modal for Images and Videos */}
      {selectedMedia && (
        <MediaViewerModal
          media={{
            id: selectedMedia.id,
            type: selectedMedia.type,
            url: selectedMedia.url
          }}
          allMedia={allMedia.map(m => ({
            id: m.id,
            type: m.type,
            url: m.url
          }))}
          onClose={() => {
            setShowMediaViewer(false)
            setSelectedMedia(null)
          }}
          onMediaChange={(newMedia) => {
            const found = allMedia.find(m => m.id === newMedia.id)
            if (found) handleMediaChange(found)
          }}
        />
      )}

      {/* Comments Dialog */}
      <CommentsSection
        contestantId={id}
        initialCount={comments}
        isOpen={showCommentsDialog}
        onOpenChange={setShowCommentsDialog}
        onCountChange={(count) => setCurrentComments(count)}
      />

      {/* Share Dialog */}
      <ShareDialog
        isOpen={showShareDialog}
        onOpenChange={setShowShareDialog}
        shareLink={shareLink}
        title={participationTitle || name}
        description={description}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        title={t('dashboard.contests.delete') || 'Supprimer'}
        message={t('dashboard.contests.my_applications.delete_confirm_message') || 'Êtes-vous sûr de vouloir supprimer cette candidature ? Cette action ne peut pas être annulée.'}
        confirmText={t('dashboard.contests.delete') || 'Supprimer'}
        cancelText={t('common.cancel') || 'Annuler'}
        onConfirm={async () => {
          if (onDelete) {
            setIsDeleting(true)
            try {
              await onDelete()
              setShowDeleteDialog(false)
              addToast(t('common.deleted_successfully') || 'Candidature supprimée avec succès', 'success')
            } catch (error: any) {
              console.error('Error deleting:', error)
              const errorMessage = error?.response?.data?.detail || error?.message || t('common.delete_error') || 'Erreur lors de la suppression'
              addToast(errorMessage, 'error')
            } finally {
              setIsDeleting(false)
            }
          }
        }}
        isLoading={isDeleting}
        isDangerous={true}
      />
    </>
  )
}
