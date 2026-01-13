'use client'

import { useState, useEffect, useRef } from 'react'
import * as React from 'react'
import { Play, ChevronLeft, ChevronRight } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { VideoPreviewDialog } from '@/components/ui/video-preview-dialog'
import { MediaViewerModal } from '@/components/media/media-viewer-modal'
import { VideoEmbed } from '@/components/ui/video-embed'
import { detectVideoPlatform } from '@/lib/utils/video-platforms'
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
  const [isOpen, setIsOpen] = useState(false)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const shouldTruncate = description && description.length > maxLength
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
    return null
  }

  if (!shouldTruncate) {
    return (
      <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words">
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
            <h4 className="font-semibold text-sm text-gray-900 dark:text-white">Description complète</h4>
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
              {description}
            </p>
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
  const [showCommentsDialog, setShowCommentsDialog] = useState(false)
  const [isVoting, setIsVoting] = useState(false)
  const [currentVotes, setCurrentVotes] = useState(votes)
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
    if (!canVote || isVoting) return

    try {
      setIsVoting(true)
      await contestService.voteForContestant(Number(id), 5)
      setIsLiked(true)
      setCurrentVotes(prev => prev + 1)
      addToast(t('dashboard.contests.vote_success') || 'Vote enregistré avec succès!', 'success')
      onVote()
    } catch (error: any) {
      console.error('Error voting:', error)
      const errorMessage = error.response?.data?.detail || ''

      // Déterminer le message d'erreur approprié selon la réponse du backend
      let toastMessage = t('dashboard.contests.vote_error') || 'Erreur lors du vote. Veuillez réessayer.'

      const errorLower = errorMessage.toLowerCase()

      if (errorLower.includes('vote') && errorLower.includes('ouvert')) {
        toastMessage = t('dashboard.contests.voting_not_open') || 'Le vote n\'est pas encore ouvert pour ce concours.'
      } else if (errorLower.includes('déjà voté') || errorLower.includes('already voted')) {
        toastMessage = t('dashboard.contests.already_voted_error') || 'Vous avez déjà voté pour ce participant.'
      } else if (errorLower.includes('propre candidature') || errorLower.includes('own entry')) {
        toastMessage = t('dashboard.contests.cannot_vote_own') || 'Vous ne pouvez pas voter pour votre propre candidature.'
      } else if (errorLower.includes('masculins') && errorLower.includes('féminines') && errorLower.includes('voter')) {
        toastMessage = t('dashboard.contests.vote_gender_restriction_male') || 'Ce concours est réservé aux participants masculins. Seules les participantes féminines peuvent voter.'
      } else if (errorLower.includes('féminines') && errorLower.includes('masculins') && errorLower.includes('voter')) {
        toastMessage = t('dashboard.contests.vote_gender_restriction_female') || 'Ce concours est réservé aux participantes féminines. Seuls les participants masculins peuvent voter.'
      } else if (errorLower.includes('genre') && errorLower.includes('voter')) {
        toastMessage = t('dashboard.contests.vote_gender_not_set') || 'Votre profil ne contient pas d\'information de genre. Veuillez compléter votre profil pour voter dans ce concours.'
      } else if (errorMessage) {
        // Utiliser le message d'erreur du backend s'il est disponible
        toastMessage = errorMessage
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
    // Construire le lien de partage avec l'id du contestant
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''
    const shareUrl = new URL(`${baseUrl}/dashboard/contests/${contestId}/contestant/${id}`)

    // Ajouter uniquement le referral code (pas de fallback sur l'ID utilisateur)
    const referralCode = user?.personal_referral_code
    if (referralCode) {
      shareUrl.searchParams.set('ref', referralCode)
    }

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
      <div className="bg-white dark:bg-gray-800/90 rounded-xl border border-gray-200/50 dark:border-gray-700/50 shadow-md hover:shadow-xl transition-all duration-300 max-w-2xl mx-auto backdrop-blur-sm overflow-hidden">
        {/* Header */}
        <div className="p-5 pb-4 bg-gradient-to-r from-gray-50/50 to-transparent dark:from-gray-800/50 border-b border-gray-100 dark:border-gray-700/50">
          <div className="flex items-start justify-between">
            {participationTitle && (
              <h4
                onClick={(e) => {
                  e.stopPropagation()
                  onViewDetails()
                }}
                className="text-lg font-bold text-gray-900 dark:text-white hover:text-myhigh5-primary dark:hover:text-myhigh5-blue-400 transition-colors cursor-pointer flex-1 line-clamp-2"
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
                ) : (
                  <VideoEmbed
                    url={firstVideo.url}
                    className="w-full h-full"
                    allowFullscreen={true}
                  />
                )}
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
        <div className="px-5 pt-4 pb-3 border-t border-gray-100 dark:border-gray-700/50 bg-gradient-to-b from-transparent to-gray-50/30 dark:to-gray-800/30">
          <div className="flex items-start gap-3 mb-3">
            {/* Avatar */}
            <div className="flex-shrink-0 relative">
              {avatar && (avatar.startsWith('http') || avatar.startsWith('/')) ? (
                <div className="w-12 h-12 rounded-full overflow-hidden bg-gradient-to-br from-myhigh5-primary/20 to-myhigh5-secondary/20 ring-2 ring-gray-200 dark:ring-gray-700">
                  <img src={avatar} alt={name} className="w-full h-full object-cover" />
                </div>
              ) : (
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center text-lg ring-2 ring-gray-200 dark:ring-gray-700">
                  {avatar || '👤'}
                </div>
              )}
              {rank && rank <= 3 && (
                <span className="absolute -top-1 -right-1 text-[10px] font-bold bg-gradient-to-br from-yellow-400 to-amber-500 text-white rounded-full w-5 h-5 flex items-center justify-center shadow-lg">
                  {rank === 1 ? '🥇' : rank === 2 ? '🥈' : '🥉'}
                </span>
              )}
            </div>

            {/* Name and Location */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <h3
                        className="text-base font-bold text-gray-900 dark:text-white hover:text-myhigh5-primary dark:hover:text-myhigh5-blue-400 transition-colors cursor-help"
                        onMouseEnter={onHoverAuthor}
                        onMouseLeave={onHoverEnd}
                      >
                        {name}
                      </h3>
                    </TooltipTrigger>
                    <TooltipContent className="bg-gray-800 text-white border-gray-700">
                      <p className="text-xs">{t('dashboard.contests.tooltip_author') || 'Voir le profil du participant'}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                {rank && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="text-xs font-bold bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary text-white px-2.5 py-1 rounded-full cursor-help shadow-sm">
                          #{rank}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent className="bg-gray-800 text-white border-gray-700">
                        <p className="text-xs">
                          {t('dashboard.contests.tooltip_rank') || `Classement ${rank === 1 ? 'premier' : rank === 2 ? 'deuxième' : rank === 3 ? 'troisième' : `${rank}ème`} dans ce concours`}
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
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
                      {currentVotes} {t('dashboard.contests.votes')}
                    </p>
                  </TooltipTrigger>
                  <TooltipContent className="bg-gray-800 text-white border-gray-700">
                    <p className="text-xs">
                      {currentUserId === userId
                        ? (t('dashboard.contests.tooltip_votes_author') || `${currentVotes} vote${currentVotes > 1 ? 's' : ''} reçu${currentVotes > 1 ? 's' : ''}. Survolez pour voir la liste.`)
                        : (t('dashboard.contests.tooltip_votes') || `${currentVotes} vote${currentVotes > 1 ? 's' : ''} reçu${currentVotes > 1 ? 's' : ''} au total`)}
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              {/* Affichage de la restriction de vote */}
              {!canVote && voteRestrictionReason && currentUserId && currentUserId !== userId && (
                <div className="mt-1.5 flex items-center gap-1.5 text-xs">
                  <span className="text-amber-600 dark:text-amber-400 font-medium">
                    {(() => {
                      switch (voteRestrictionReason) {
                        case 'already_voted':
                          return t('dashboard.contests.already_voted') || 'Already voted'
                        case 'different_city':
                          return t('dashboard.contests.restriction_different_city') || 'Different city'
                        case 'different_country':
                          return t('dashboard.contests.restriction_different_country') || 'Different country'
                        case 'different_region':
                          return t('dashboard.contests.restriction_different_region') || 'Different region'
                        case 'different_continent':
                          return t('dashboard.contests.restriction_different_continent') || 'Different continent'
                        case 'own_contestant':
                          return t('dashboard.contests.restriction_own_contestant') || 'Your own contestant'
                        case 'not_authenticated':
                          return t('dashboard.contests.restriction_not_authenticated') || 'Login required'
                        case 'geographic_restriction':
                          return t('dashboard.contests.restriction_geographic') || 'Geographic restriction'
                        case 'user_not_found':
                          return t('dashboard.contests.restriction_user_not_found') || 'User not found'
                        default:
                          return t('dashboard.contests.cannot_vote') || 'Cannot vote'
                      }
                    })()}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Description */}
          <div className="ml-[52px]">
            <ContestantDescription description={description} maxLength={150} />
          </div>
        </div>

        {/* Action Buttons - Facebook Style with Counts */}
        <div className="px-2 border-t border-gray-100 dark:border-gray-700/50 bg-gray-50/50 dark:bg-gray-800/30">
          <div className="grid grid-cols-4 divide-x divide-gray-200/50 dark:divide-gray-700/50">
            <div
              onMouseEnter={currentUserId === userId ? onHoverVotes : undefined}
              onMouseLeave={currentUserId === userId ? onHoverEnd : undefined}
            >
              <VoteButton
                contestantId={Number(id)}
                canVote={canVote}
                hasVoted={isLiked}
                isVoting={isVoting}
                onVote={handleVote}
                isAuthor={currentUserId === userId}
                votesCount={currentVotes}
                voteRestrictionReason={voteRestrictionReason}
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
