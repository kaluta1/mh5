'use client'

import { useState, useEffect } from 'react'
import { X, Eye, Users, Share2, BarChart3, Radio } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useLanguage } from '@/contexts/language-context'
import { contestService, ContestantWithAuthorAndStats } from '@/services/contest-service'
import { reactionsService, ReactionDetails } from '@/services/reactions-service'
import { sharesService, ShareStats } from '@/services/shares-service'
import { MediaViewerModal } from '@/components/media/media-viewer-modal'
import { VideoEmbed } from '@/components/ui/video-embed'
import { detectVideoPlatform , cleanVideoUrl } from '@/lib/utils/video-platforms'

interface ApplicationDetailsDialogProps {
  isOpen: boolean
  onClose: () => void
  contestantId: number
  contestId: number
}

export function ApplicationDetailsDialog({
  isOpen,
  onClose,
  contestantId,
  contestId
}: ApplicationDetailsDialogProps) {
  const { t } = useLanguage()
  const [loading, setLoading] = useState(true)
  const [contestant, setContestant] = useState<ContestantWithAuthorAndStats | null>(null)
  const [reactionDetails, setReactionDetails] = useState<ReactionDetails | null>(null)
  const [shareStats, setShareStats] = useState<ShareStats | null>(null)
  const [showMediaViewer, setShowMediaViewer] = useState(false)
  const [selectedMedia, setSelectedMedia] = useState<{ id: string; type: 'image' | 'video'; url: string } | null>(null)
  const [activeTab, setActiveTab] = useState<'details' | 'reactions' | 'stats' | 'shares'>('details')

  useEffect(() => {
    if (isOpen && contestantId) {
      loadData()
    }
  }, [isOpen, contestantId])

  const loadData = async () => {
    setLoading(true)
    try {
      const [contestantData, reactions, shares] = await Promise.all([
        contestService.getContestantById(contestantId),
        reactionsService.getReactionDetails(contestantId).catch(() => null),
        sharesService.getShareStats(contestantId).catch(() => null)
      ])
      setContestant(contestantData)
      setReactionDetails(reactions)
      setShareStats(shares)
    } catch (error) {
      console.error('Error loading application details:', error)
    } finally {
      setLoading(false)
    }
  }

  const parseMediaIds = (mediaIds: string | null, type: 'image' | 'video') => {
    if (!mediaIds) return []
    try {
      const parsed = JSON.parse(mediaIds)
      if (Array.isArray(parsed)) {
        return parsed.map((url, index) => ({
          id: `${type}-${index}`,
          type,
          url
        }))
      }
    } catch (e) {
      console.error('Error parsing media IDs:', e)
    }
    return []
  }

  if (!isOpen) return null

  const images = contestant ? parseMediaIds(contestant.image_media_ids || null, 'image') : []
  const videos = contestant ? parseMediaIds(contestant.video_media_ids || null, 'video') : []
  const allMedia = [...images, ...videos]

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <Card className="w-full max-w-4xl dark:bg-gray-800 my-8 max-h-[90vh] overflow-hidden flex flex-col">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b dark:border-gray-700 flex-shrink-0">
          <CardTitle className="text-xl font-bold">
            {t('dashboard.contests.my_applications.details') || 'Détails de la candidature'}
          </CardTitle>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <X className="h-5 w-5" />
          </button>
        </CardHeader>

        <CardContent className="pt-6 space-y-4 overflow-y-auto flex-1">
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
            </div>
          ) : contestant ? (
            <>
              {/* Tabs */}
              <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => setActiveTab('details')}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === 'details'
                      ? 'border-myhigh5-primary text-myhigh5-primary'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  <Eye className="w-4 h-4 inline mr-2" />
                  {t('dashboard.contests.my_applications.details') || 'Détails'}
                </button>
                <button
                  onClick={() => setActiveTab('reactions')}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === 'reactions'
                      ? 'border-myhigh5-primary text-myhigh5-primary'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  <Users className="w-4 h-4 inline mr-2" />
                  {t('dashboard.contests.reactions') || 'Réactions'}
                  {reactionDetails && (
                    <Badge className="ml-2 bg-myhigh5-primary text-white">
                      {Object.values(reactionDetails.reactions_by_type).reduce((acc, arr) => acc + arr.length, 0)}
                    </Badge>
                  )}
                </button>
                <button
                  onClick={() => setActiveTab('stats')}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === 'stats'
                      ? 'border-myhigh5-primary text-myhigh5-primary'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  <BarChart3 className="w-4 h-4 inline mr-2" />
                  {t('dashboard.contests.my_applications.statistics') || 'Statistiques'}
                </button>
                <button
                  onClick={() => setActiveTab('shares')}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === 'shares'
                      ? 'border-myhigh5-primary text-myhigh5-primary'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  <Share2 className="w-4 h-4 inline mr-2" />
                  {t('dashboard.contests.share') || 'Partages'}
                  {shareStats && (
                    <Badge className="ml-2 bg-myhigh5-primary text-white">
                      {shareStats.total_shares}
                    </Badge>
                  )}
                </button>
              </div>

              {/* Tab Content */}
              {activeTab === 'details' && (
                <div className="space-y-6">
                  {/* Title and Description */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                      {contestant.title || t('dashboard.contests.my_applications.no_title')}
                    </h3>
                    {contestant.description && (
                      <p className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                        {contestant.description}
                      </p>
                    )}
                  </div>

                  {/* Media */}
                  {allMedia.length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                        {t('dashboard.contests.my_applications.media') || 'Médias'}
                      </h4>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                        {allMedia.map((media) => (
                          <div
                            key={media.id}
                            className="relative aspect-square rounded-lg overflow-hidden cursor-pointer group bg-black"
                            onClick={() => {
                              setSelectedMedia(media)
                              setShowMediaViewer(true)
                            }}
                          >
                            {media.type === 'image' ? (
                              <img
                                src={media.url}
                                alt={t('dashboard.contests.my_applications.media_alt') || 'Média'}
                                className="w-full h-full object-cover group-hover:opacity-75 transition"
                              />
                            ) : (
                              <VideoEmbed
                                url={media.url}
                                className="w-full h-full object-cover"
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Info */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                        {t('dashboard.contests.votes') || 'Votes'}
                      </p>
                      <p className="text-lg font-bold text-blue-600 dark:text-blue-400">
                        {contestant.votes_count || 0}
                      </p>
                    </div>
                    <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3">
                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                        {t('dashboard.contests.reactions') || 'Réactions'}
                      </p>
                      <p className="text-lg font-bold text-purple-600 dark:text-purple-400">
                        {contestant.reactions_count || 0}
                      </p>
                    </div>
                    <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                        {t('common.comments') || 'Commentaires'}
                      </p>
                      <p className="text-lg font-bold text-green-600 dark:text-green-400">
                        {contestant.comments_count || 0}
                      </p>
                    </div>
                    <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3">
                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                        {t('dashboard.contests.favorites') || 'Favoris'}
                      </p>
                      <p className="text-lg font-bold text-orange-600 dark:text-orange-400">
                        {contestant.favorites_count || 0}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'reactions' && (
                <div className="space-y-4">
                  {reactionDetails && Object.keys(reactionDetails.reactions_by_type).length > 0 ? (
                    Object.entries(reactionDetails.reactions_by_type).map(([type, users]) => (
                      <div key={type} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 capitalize">
                          {type === 'like' ? '👍 ' : type === 'love' ? '❤️ ' : type === 'wow' ? '😮 ' : '👎 '}
                          {t(`dashboard.contests.${type}`) || type} ({users.length})
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {users.map((user) => (
                            <div
                              key={user.user_id}
                              className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2"
                            >
                              {user.avatar_url ? (
                                <img
                                  src={user.avatar_url}
                                  alt={user.full_name || user.username}
                                  className="w-8 h-8 rounded-full"
                                />
                              ) : (
                                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-primary-dark flex items-center justify-center text-white text-xs">
                                  {(user.full_name || user.username || 'U')[0].toUpperCase()}
                                </div>
                              )}
                              <span className="text-sm text-gray-900 dark:text-white">
                                {user.full_name || user.username || t('dashboard.contests.my_applications.user') || 'Utilisateur'}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-center text-gray-500 dark:text-gray-400 py-8">
                      {t('dashboard.contests.no_reactions') || 'Aucune réaction pour le moment'}
                    </p>
                  )}
                </div>
              )}

              {activeTab === 'stats' && (
                <div className="space-y-6">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 text-center">
                      <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                        {contestant.votes_count || 0}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {t('dashboard.contests.votes') || 'Votes'}
                      </p>
                    </div>
                    <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4 text-center">
                      <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                        {contestant.reactions_count || 0}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {t('dashboard.contests.reactions') || 'Réactions'}
                      </p>
                    </div>
                    <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 text-center">
                      <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                        {contestant.comments_count || 0}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {t('common.comments') || 'Commentaires'}
                      </p>
                    </div>
                    <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-4 text-center">
                      <p className="text-2xl font-bold text-orange-600 dark:text-orange-400">
                        {contestant.favorites_count || 0}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
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
                      <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 rounded-lg p-6 text-center border border-blue-200 dark:border-blue-800">
                        <p className="text-4xl font-bold text-blue-600 dark:text-blue-400">
                          {shareStats.total_shares}
                        </p>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                          {t('dashboard.contests.my_applications.total_shares') || 'Total de partages'}
                        </p>
                      </div>

                      {Object.keys(shareStats.shares_by_platform).length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                            {t('dashboard.contests.my_applications.shares_by_platform') || 'Partages par plateforme'}
                          </h4>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {Object.entries(shareStats.shares_by_platform).map(([platform, count]) => (
                              <div
                                key={platform}
                                className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-center"
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
                    <p className="text-center text-gray-500 dark:text-gray-400 py-8">
                      {t('dashboard.contests.my_applications.no_shares') || 'Aucun partage pour le moment'}
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className="text-center text-gray-500 dark:text-gray-400 py-8">
              {t('common.error_loading') || 'Erreur lors du chargement'}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Media Viewer */}
      {showMediaViewer && selectedMedia && (
        <MediaViewerModal
          media={selectedMedia}
          allMedia={allMedia}
          onClose={() => {
            setShowMediaViewer(false)
            setSelectedMedia(null)
          }}
          onMediaChange={(newMedia) => {
            const found = allMedia.find((m) => m.id === newMedia.id)
            if (found) setSelectedMedia(found)
          }}
        />
      )}
    </div>
  )
}

