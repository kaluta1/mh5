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
import { VoteButton } from '@/components/dashboard/vote-button'
import { FavoriteButton } from '@/components/dashboard/favorite-button'
import { ShareDialog } from '@/components/dashboard/share-dialog'
import { CheckCircle, AlertCircle, Info, MessageCircle, Heart, ThumbsUp, ArrowLeft, Edit, Trash2, BarChart3, Share2, Users, Eye } from 'lucide-react'
import { contestService, ContestantWithAuthorAndStats } from '@/services/contest-service'
import { reactionsService, ReactionDetails } from '@/services/reactions-service'
import { sharesService, ShareStats } from '@/services/shares-service'
import { commentsService, Comment as ServiceComment } from '@/lib/services/comments-service'
import { useToast } from '@/components/ui/toast'
import api from '@/lib/api'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import Image from 'next/image'
import * as React from 'react'
import Link from 'next/link'

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

// Composant pour afficher une description tronquée avec popover au hover
function DescriptionWithPopover({ description, maxLength = 200 }: { description: string; maxLength?: number }) {
  const { t } = useLanguage()
  const [isOpen, setIsOpen] = React.useState(false)
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null)
  const containerRef = React.useRef<HTMLDivElement>(null)

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
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400 italic">
        {t('dashboard.contests.my_applications.no_title') || 'Aucune description disponible'}
      </p>
    )
  }

  if (!shouldTruncate) {
    return (
      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
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
      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed cursor-pointer hover:text-myfav-primary dark:hover:text-myfav-secondary transition-colors whitespace-pre-wrap">
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
              {t('dashboard.contests.my_applications.details') || 'Description complète'}
            </h4>
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
              {description}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default function MyApplicationDetailPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const applicationId = params.id as string
  const { addToast } = useToast()

  const [contestant, setContestant] = useState<ContestantWithAuthorAndStats | null>(null)
  const [pageLoading, setPageLoading] = useState(true)
  const [selectedMedia, setSelectedMedia] = useState<Media | null>(null)
  const [isFavorite, setIsFavorite] = useState(false)
  const [showInfoDialog, setShowInfoDialog] = useState(false)
  const [showCommentsDialog, setShowCommentsDialog] = useState(false)
  const [isVoting, setIsVoting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [reactionDetails, setReactionDetails] = useState<ReactionDetails | null>(null)
  const [selectedReaction, setSelectedReaction] = useState<string | null>(null)
  const [reactionStats, setReactionStats] = useState<{ total_reactions: number; like_count: number; love_count: number; wow_count: number; dislike_count: number; user_reaction?: string | null } | null>(null)
  const [shareStats, setShareStats] = useState<ShareStats | null>(null)
  const [showShareDialog, setShowShareDialog] = useState(false)
  const [shareLink, setShareLink] = useState('')
  const [activeTab, setActiveTab] = useState<'details' | 'reactions' | 'stats' | 'shares'>('details')
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [isAuthenticated, isLoading, router])

  // Charger les données du contestant
  useEffect(() => {
    const loadContestant = async () => {
      try {
        setPageLoading(true)
        setError(null)
        
        const contestantData = await contestService.getContestantById(Number(applicationId))
        if (!contestantData) {
          setError(t('common.error_loading') || 'Erreur lors du chargement')
          return
        }
        
        setContestant(contestantData)
        
        // Générer le lien de partage
        if (contestantData.contest_id) {
          setShareLink(`${window.location.origin}/dashboard/contests/${contestantData.contest_id}/contestant/${applicationId}`)
        }
        
        // Vérifier si c'est un favori
        try {
          const favResponse = await api.get(`/api/v1/favorites/contestants/${applicationId}/is-favorite`)
          setIsFavorite(favResponse.data.is_favorite || false)
        } catch (err) {
          console.error('Error checking favorite status:', err)
        }
      } catch (err: any) {
        console.error('Error loading contestant:', err)
        setError(err?.response?.data?.detail || t('common.error_loading') || 'Erreur lors du chargement')
        addToast(t('common.error_loading') || 'Erreur lors du chargement', 'error')
      } finally {
        setPageLoading(false)
      }
    }

    if (!isLoading && isAuthenticated && user && applicationId) {
      loadContestant()
    }
  }, [isLoading, isAuthenticated, user, applicationId, addToast, t])

  // Charger les commentaires, réactions et partages
  useEffect(() => {
    const loadData = async () => {
      if (!applicationId) return

      try {
        // Charger les commentaires
        const commentsResponse = await commentsService.getContestantComments(applicationId)
        const convertedComments: Comment[] = (commentsResponse.comments || []).map((c: ServiceComment) => ({
          id: String(c.id),
          author_name: c.author_name,
          author_avatar: c.author_avatar,
          text: c.text || c.content || '',
          created_at: c.created_at,
          target_type: c.target_type || 'contest',
          target_id: c.target_id
        }))
        setComments(convertedComments)

        // Charger les détails des réactions
        const reactionsResponse = await reactionsService.getReactionDetails(Number(applicationId))
        setReactionDetails(reactionsResponse)

        // Charger les stats de réactions
        const statsResponse = await reactionsService.getReactionStats(Number(applicationId))
        setReactionStats(statsResponse)
        setSelectedReaction(statsResponse.user_reaction || null)

        // Charger les stats de partages
        const sharesResponse = await sharesService.getShareStats(Number(applicationId))
        setShareStats(sharesResponse)
      } catch (err) {
        console.error('Error loading data:', err)
      }
    }

    if (applicationId && contestant) {
      loadData()
    }
  }, [applicationId, contestant])

  const handleReactionSelect = async (reactionType: string) => {
    try {
      if (selectedReaction === reactionType) {
        await reactionsService.removeReaction(Number(applicationId))
        setSelectedReaction(null)
      } else {
        await reactionsService.addReaction(Number(applicationId), reactionType as 'like' | 'love' | 'wow' | 'dislike')
        setSelectedReaction(reactionType)
      }
      
      const stats = await reactionsService.getReactionStats(Number(applicationId))
      setReactionStats(stats)
      const details = await reactionsService.getReactionDetails(Number(applicationId))
      setReactionDetails(details)
    } catch (error: any) {
      console.error('Error handling reaction:', error)
      addToast(error?.response?.data?.detail || t('common.error') || 'Erreur', 'error')
    }
  }

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      await contestService.deleteContestant(Number(applicationId))
      addToast(t('common.deleted_successfully') || 'Candidature supprimée', 'success')
      router.push('/dashboard/my-applications')
    } catch (err: any) {
      console.error('Error deleting:', err)
      const errorMessage = err?.response?.data?.detail || err?.message || t('common.error') || 'Erreur'
      addToast(errorMessage, 'error')
    } finally {
      setIsDeleting(false)
      setShowDeleteDialog(false)
    }
  }

  const handleAddComment = async (text: string, targetType: 'contest' | 'photo' | 'video', targetId?: string) => {
    try {
      let newComment: Comment
      
      if (targetType === 'contest') {
        const response = await commentsService.addContestantComment(applicationId, text)
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
        const response = await commentsService.addMediaComment(
          applicationId,
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
      addToast(t('common.success') || 'Commentaire ajouté', 'success')
    } catch (err) {
      console.error('Error posting comment:', err)
      addToast(t('common.error') || 'Erreur', 'error')
    }
  }

  if (isLoading || pageLoading) {
    return <ContestantDetailSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  if (error || !contestant) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-4">
        <Card className="p-6 text-center max-w-md">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
            {t('common.error') || 'Erreur'}
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            {error || t('common.error_loading') || 'Erreur lors du chargement'}
          </p>
          <Button onClick={() => router.push('/dashboard/my-applications')}>
            {t('common.back') || 'Retour'}
          </Button>
        </Card>
      </div>
    )
  }

  // Parser les médias depuis les IDs
  const parseMediaIds = (mediaIds: string | null | undefined, type: 'image' | 'video'): Media[] => {
    if (!mediaIds) return []
    try {
      const ids = JSON.parse(mediaIds)
      if (Array.isArray(ids)) {
        return ids.map((id: string, index: number) => ({
          id: `${type}-${index}`,
          type,
          url: id,
          thumbnail: undefined
        }))
      }
    } catch {
      return []
    }
    return []
  }

  const images = parseMediaIds(contestant.image_media_ids || null, 'image')
  const videos = parseMediaIds(contestant.video_media_ids || null, 'video')
  const allMedia = [...images, ...videos]

  const isAuthor = user.id === contestant.user_id

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header avec bouton retour et actions */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="container mx-auto px-4 md:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              onClick={() => router.push('/dashboard/my-applications')}
              className="flex items-center gap-2"
            >
              <ArrowLeft className="w-4 h-4" />
              {t('common.back') || 'Retour'}
            </Button>
            
            {isAuthor && (
              <div className="flex items-center gap-2">
                <Link href={`/dashboard/contests/${contestant.contest_id}/apply?edit=true`}>
                  <Button variant="outline" className="flex items-center gap-2">
                    <Edit className="w-4 h-4" />
                    {t('common.edit') || 'Éditer'}
                  </Button>
                </Link>
                <Button
                  variant="outline"
                  onClick={() => setShowDeleteDialog(true)}
                  className="flex items-center gap-2 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-900/20"
                >
                  <Trash2 className="w-4 h-4" />
                  {t('common.delete') || 'Supprimer'}
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>

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
        onBack={() => router.push('/dashboard/my-applications')}
        onFavoriteToggle={async () => {
          try {
            if (isFavorite) {
              await api.delete(`/api/v1/contestants/${applicationId}/favorite`)
              setIsFavorite(false)
              addToast(t('dashboard.contests.removed_from_favorites') || 'Retiré des favoris', 'success')
            } else {
              await api.post(`/api/v1/contestants/${applicationId}/favorite`)
              setIsFavorite(true)
              addToast(t('dashboard.contests.added_to_favorites') || 'Ajouté aux favoris', 'success')
            }
          } catch (error: any) {
            console.error('Error toggling favorite:', error)
            addToast(error?.response?.data?.detail || t('common.error') || 'Erreur', 'error')
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
                {t('dashboard.contests.votes') || 'Votes'}
              </p>
            </div>
            <div className="text-center md:text-left">
              <p className="text-2xl md:text-3xl font-bold text-myfav-primary">
                {contestant.reactions_count || 0}
              </p>
              <p className="text-xs md:text-sm text-gray-600 dark:text-gray-400">
                {t('dashboard.contests.reactions') || 'Réactions'}
              </p>
            </div>
            <div className="text-center md:text-left">
              <p className="text-2xl md:text-3xl font-bold text-myfav-primary">
                {contestant.comments_count || 0}
              </p>
              <p className="text-xs md:text-sm text-gray-600 dark:text-gray-400">
                {t('common.comments') || 'Commentaires'}
              </p>
            </div>
            <div className="text-center md:text-left">
              <p className="text-2xl md:text-3xl font-bold text-myfav-primary">
                {contestant.favorites_count || 0}
              </p>
              <p className="text-xs md:text-sm text-gray-600 dark:text-gray-400">
                {t('dashboard.contests.favorites') || 'Favoris'}
              </p>
            </div>
            {contestant.rank && (
              <div className="text-center md:text-left">
                <p className="text-2xl md:text-3xl font-bold text-myfav-primary">
                  #{contestant.rank}
                </p>
                <p className="text-xs md:text-sm text-gray-600 dark:text-gray-400">
                  {t('dashboard.contests.rank') || 'Rang'}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="py-6 md:py-8">
        <div className="container mx-auto px-4 md:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column - Tabs & Details (1/3) */}
            <div className="lg:col-span-1">
              <Card className="p-4 sticky top-6">
                {/* Tabs */}
                <div className="flex flex-col gap-2 mb-4">
                  <button
                    onClick={() => setActiveTab('details')}
                    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 ${
                      activeTab === 'details'
                        ? 'bg-myfav-primary text-white'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    <Eye className="w-4 h-4" />
                    {t('dashboard.contests.my_applications.details') || 'Détails'}
                  </button>
                  <button
                    onClick={() => setActiveTab('reactions')}
                    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 ${
                      activeTab === 'reactions'
                        ? 'bg-myfav-primary text-white'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    <Users className="w-4 h-4" />
                    {t('dashboard.contests.reactions') || 'Réactions'}
                    {reactionDetails && (
                      <Badge className="ml-auto bg-white/20 text-white">
                        {Object.values(reactionDetails.reactions_by_type).reduce((acc, arr) => acc + arr.length, 0)}
                      </Badge>
                    )}
                  </button>
                  <button
                    onClick={() => setActiveTab('stats')}
                    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 ${
                      activeTab === 'stats'
                        ? 'bg-myfav-primary text-white'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    <BarChart3 className="w-4 h-4" />
                    {t('dashboard.contests.my_applications.statistics') || 'Statistiques'}
                  </button>
                  <button
                    onClick={() => setActiveTab('shares')}
                    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 ${
                      activeTab === 'shares'
                        ? 'bg-myfav-primary text-white'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    <Share2 className="w-4 h-4" />
                    {t('dashboard.contests.share') || 'Partages'}
                    {shareStats && shareStats.total_shares > 0 && (
                      <Badge className="ml-auto bg-white/20 text-white">
                        {shareStats.total_shares}
                      </Badge>
                    )}
                  </button>
                </div>

                {/* Tab Content */}
                {activeTab === 'details' && (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        {t('dashboard.contests.my_applications.contest') || 'Concours'}
                      </h3>
                      <p className="text-sm text-gray-900 dark:text-white">
                        {contestant.contest_title || '-'}
                      </p>
                    </div>
                    {contestant.title && (
                      <div>
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                          {t('dashboard.contests.my_applications.title') || 'Titre'}
                        </h3>
                        <p className="text-sm text-gray-900 dark:text-white">
                          {contestant.title}
                        </p>
                      </div>
                    )}
                    {contestant.description && (
                      <div>
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                          {t('dashboard.contests.my_applications.details') || 'Description'}
                        </h3>
                        <DescriptionWithPopover description={contestant.description} maxLength={150} />
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'reactions' && (
                  <div className="space-y-4">
                    {reactionDetails && Object.keys(reactionDetails.reactions_by_type).length > 0 ? (
                      Object.entries(reactionDetails.reactions_by_type).map(([type, users]) => (
                        <div key={type} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                          <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 capitalize flex items-center gap-2">
                            {type === 'like' ? '👍' : type === 'love' ? '❤️' : type === 'wow' ? '😮' : '👎'}
                            {t(`dashboard.contests.${type}`) || type} ({users.length})
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {users.map((user) => (
                              <div
                                key={user.user_id}
                                className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800 rounded-lg px-2 py-1"
                              >
                                {user.avatar_url ? (
                                  <img
                                    src={user.avatar_url}
                                    alt={user.full_name || user.username || ''}
                                    className="w-6 h-6 rounded-full"
                                  />
                                ) : (
                                  <div className="w-6 h-6 rounded-full bg-gradient-to-br from-myfav-primary to-myfav-primary-dark flex items-center justify-center text-white text-xs">
                                    {(user.full_name || user.username || 'U')[0].toUpperCase()}
                                  </div>
                                )}
                                <span className="text-xs text-gray-900 dark:text-white">
                                  {user.full_name || user.username || t('dashboard.contests.my_applications.user') || 'Utilisateur'}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="text-center text-gray-500 dark:text-gray-400 py-4 text-sm">
                        {t('dashboard.contests.no_reactions') || 'Aucune réaction pour le moment'}
                      </p>
                    )}
                  </div>
                )}

                {activeTab === 'stats' && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-center">
                        <p className="text-xl font-bold text-blue-600 dark:text-blue-400">
                          {contestant.votes_count || 0}
                        </p>
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                          {t('dashboard.contests.votes') || 'Votes'}
                        </p>
                      </div>
                      <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3 text-center">
                        <p className="text-xl font-bold text-purple-600 dark:text-purple-400">
                          {contestant.reactions_count || 0}
                        </p>
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                          {t('dashboard.contests.reactions') || 'Réactions'}
                        </p>
                      </div>
                      <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3 text-center">
                        <p className="text-xl font-bold text-green-600 dark:text-green-400">
                          {contestant.comments_count || 0}
                        </p>
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                          {t('common.comments') || 'Commentaires'}
                        </p>
                      </div>
                      <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3 text-center">
                        <p className="text-xl font-bold text-orange-600 dark:text-orange-400">
                          {contestant.favorites_count || 0}
                        </p>
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                          {t('dashboard.contests.favorites') || 'Favoris'}
                        </p>
                      </div>
                    </div>
                    {contestant.rank && (
                      <div className="bg-gradient-to-r from-yellow-50 to-orange-50 dark:from-yellow-900/20 dark:to-orange-900/20 rounded-lg p-4 text-center border border-yellow-200 dark:border-yellow-800">
                        <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">
                          #{contestant.rank}
                        </p>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                          {t('dashboard.contests.rank') || 'Classement'}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'shares' && (
                  <div className="space-y-4">
                    {shareStats && shareStats.total_shares > 0 ? (
                      <>
                        <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 rounded-lg p-4 text-center border border-blue-200 dark:border-blue-800">
                          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400">
                            {shareStats.total_shares}
                          </p>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                            {t('dashboard.contests.my_applications.total_shares') || 'Total de partages'}
                          </p>
                        </div>
                        {Object.keys(shareStats.shares_by_platform).length > 0 && (
                          <div>
                            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                              {t('dashboard.contests.my_applications.shares_by_platform') || 'Partages par plateforme'}
                            </h4>
                            <div className="grid grid-cols-2 gap-2">
                              {Object.entries(shareStats.shares_by_platform).map(([platform, count]) => (
                                <div
                                  key={platform}
                                  className="bg-gray-50 dark:bg-gray-800 rounded-lg p-2 text-center"
                                >
                                  <p className="text-lg font-bold text-gray-900 dark:text-white">{count}</p>
                                  <p className="text-xs text-gray-600 dark:text-gray-400 capitalize mt-1">
                                    {platform}
                                  </p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="text-center text-gray-500 dark:text-gray-400 py-4 text-sm">
                        {t('dashboard.contests.my_applications.no_shares') || 'Aucun partage pour le moment'}
                      </p>
                    )}
                  </div>
                )}
              </Card>
            </div>

            {/* Right Column - Media & Description (2/3) */}
            <div className="lg:col-span-2 space-y-6">
              {/* Description */}
              {contestant.description && (
                <Card className="p-6">
                  <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-3">
                    {t('dashboard.contests.my_applications.details') || 'Description'}
                  </h2>
                  <DescriptionWithPopover description={contestant.description} maxLength={300} />
                </Card>
              )}

              {/* Media Gallery */}
              {allMedia.length > 0 && (
                <Card className="p-6">
                  <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
                    {t('dashboard.contests.my_applications.media') || 'Médias'}
                  </h2>
                  <MediaGallery
                    images={images}
                    videos={videos}
                    onMediaSelect={setSelectedMedia}
                  />
                </Card>
              )}

              {/* Comments Section */}
              <Card className="p-6">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
                  {t('common.comments') || 'Commentaires'} ({comments.length})
                </h2>
                <CommentsSection
                  comments={comments}
                  onAddComment={(text) => handleAddComment(text, 'contest')}
                />
              </Card>
            </div>
          </div>
        </div>
      </div>

      {/* Media Viewer Modal */}
      {selectedMedia && (
        <MediaViewerModal
          media={selectedMedia}
          allMedia={allMedia}
          onClose={() => setSelectedMedia(null)}
          onMediaChange={setSelectedMedia}
          comments={comments}
          onAddComment={(text) => handleAddComment(text, selectedMedia.type === 'video' ? 'video' : 'photo', selectedMedia.id)}
        />
      )}

      {/* Share Dialog */}
      <ShareDialog
        isOpen={showShareDialog}
        onOpenChange={setShowShareDialog}
        shareLink={shareLink}
        title={contestant.title || contestant.author_name || ''}
        description={contestant.description || ''}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        title={`⚠️ ${t('common.confirm_delete') || 'Confirmer la suppression'}`}
        message={t('dashboard.contests.my_applications.delete_confirm_message') || 'Êtes-vous sûr de vouloir supprimer cette candidature ? Cette action ne peut pas être annulée.'}
        confirmText={t('common.delete') || 'Supprimer'}
        cancelText={t('common.cancel') || 'Annuler'}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        isDangerous={true}
      />
    </div>
  )
}

