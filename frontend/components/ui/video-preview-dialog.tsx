'use client'

import React, { useState, useEffect, useRef } from 'react'
import { X, Play, ThumbsUp, MessageCircle, Send, Clock, Info } from 'lucide-react'
import { VideoEmbed } from './video-embed'
import { detectVideoPlatform } from '@/lib/utils/video-platforms'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { commentsService, Comment } from '@/lib/services/comments-service'
import { contestService } from '@/services/contest-service'

// Icônes SVG plateformes
function TikTokIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1v-3.5a6.37 6.37 0 00-.79-.05A6.34 6.34 0 003.15 15.2a6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.34-6.34V8.56a8.28 8.28 0 004.76 1.5v-3.5a4.81 4.81 0 01-1-.13z" />
    </svg>
  )
}

function YouTubeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
    </svg>
  )
}

function InstagramIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z" />
    </svg>
  )
}

const PLATFORM_CONFIG: Record<string, { label: string; bgClass: string; Icon: React.FC<{ className?: string }> }> = {
  tiktok: { label: 'TikTok', bgClass: 'bg-black', Icon: TikTokIcon },
  youtube: { label: 'YouTube', bgClass: 'bg-red-600', Icon: YouTubeIcon },
  instagram: { label: 'Instagram', bgClass: 'bg-gradient-to-br from-purple-600 via-pink-500 to-orange-400', Icon: InstagramIcon },
  vimeo: { label: 'Vimeo', bgClass: 'bg-blue-500', Icon: Play },
  facebook: { label: 'Facebook', bgClass: 'bg-blue-600', Icon: Play },
}

interface VideoPreviewDialogProps {
  isOpen: boolean
  videoUrl: string
  videoTitle?: string
  onClose: () => void
  canVote?: boolean
  hasVoted?: boolean
  isVoting?: boolean
  isAuthor?: boolean
  votesCount?: number
  onVote?: () => void
  voteRestrictionReason?: string | null
  authorName?: string
  authorAvatar?: string
  rank?: number
  contestantId?: string
  commentsCount?: number
}

export function VideoPreviewDialog({
  isOpen,
  videoUrl,
  videoTitle = '',
  onClose,
  canVote = false,
  hasVoted = false,
  isVoting = false,
  isAuthor = false,
  votesCount = 0,
  onVote,
  voteRestrictionReason,
  authorName,
  authorAvatar,
  rank,
  contestantId,
  commentsCount: initialCommentsCount = 0,
}: VideoPreviewDialogProps) {
  const { t } = useLanguage()
  const { user } = useAuth()
  const [showComments, setShowComments] = useState(false)
  const [comments, setComments] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [commentsLoading, setCommentsLoading] = useState(false)
  const [submittingComment, setSubmittingComment] = useState(false)
  const [commentsCount, setCommentsCount] = useState(initialCommentsCount)
  const [viewTracked, setViewTracked] = useState(false)
  const commentsEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Charger les commentaires
  useEffect(() => {
    if (showComments && contestantId) {
      setCommentsLoading(true)
      commentsService.getContestantComments(contestantId, 0, 50)
        .then((res) => {
          setComments(res.comments || [])
          setCommentsCount(res.total || 0)
        })
        .catch(() => {})
        .finally(() => setCommentsLoading(false))
    }
  }, [showComments, contestantId])

  // Scroll to bottom on new comment
  useEffect(() => {
    if (commentsEndRef.current) {
      commentsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [comments.length])

  const handleSubmitComment = async () => {
    if (!newComment.trim() || !contestantId || submittingComment) return
    setSubmittingComment(true)
    try {
      const result = await commentsService.addContestantComment(contestantId, newComment.trim())
      if (result) {
        setComments(prev => [...prev, {
          id: result.id || Date.now(),
          author_name: user?.username || user?.full_name || '',
          author_avatar: user?.avatar_url || '',
          content: newComment.trim(),
          text: newComment.trim(),
          user_id: user?.id || 0,
          created_at: new Date().toISOString(),
          like_count: 0,
          reply_count: 0,
          is_liked: false,
          replies: [],
        }])
        setCommentsCount(prev => prev + 1)
        setNewComment('')
      }
    } catch (e) {
      console.error('Comment error:', e)
    } finally {
      setSubmittingComment(false)
    }
  }

  if (!isOpen) return null

  const platform = detectVideoPlatform(videoUrl)
  const config = PLATFORM_CONFIG[platform]
  const isTikTok = platform === 'tiktok'
  const isInstagram = platform === 'instagram'
  const isVertical = isTikTok || isInstagram

  useEffect(() => {
    if (!isOpen) {
      setViewTracked(false)
    }
  }, [isOpen, contestantId, videoUrl])

  const handleViewed30s = async () => {
    if (!contestantId || viewTracked) return
    try {
      await contestService.trackContestantView(Number(contestantId), 30)
      setViewTracked(true)
    } catch {
      // Ignore analytics errors in preview dialog.
    }
  }

  return (
    <div className="fixed inset-0 z-[999999] flex items-center justify-center" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/80 backdrop-blur-md" />

      {/* Dialog container */}
      <div
        className={`relative z-[9999999] flex overflow-hidden rounded-2xl shadow-2xl border border-white/10 ${
          isVertical
            ? 'flex-col sm:flex-row w-[95vw] sm:w-[900px] lg:w-[1000px] max-h-[90vh]'
            : 'flex-col lg:flex-row w-[95vw] lg:w-[85vw] xl:w-[80vw] max-h-[90vh] lg:h-[85vh]'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-2 bg-black/50 hover:bg-black/70 rounded-full transition-all z-[99999999] cursor-pointer group"
        >
          <X className="w-4 h-4 text-white/80 group-hover:text-white" />
        </button>

        {/* Platform Badge */}
        {config && (
          <div className={`absolute top-3 left-3 z-[99999999] flex items-center gap-1.5 px-2.5 py-1 rounded-full ${config.bgClass} text-white text-[11px] font-semibold shadow-lg`}>
            <config.Icon className="w-3.5 h-3.5" />
            {config.label}
          </div>
        )}

        {/* Video */}
        <div className={`relative bg-black flex items-center justify-center flex-shrink-0 ${
          isVertical
            ? 'w-full sm:w-[480px] h-[55vh] sm:h-[85vh]'
            : 'w-full lg:w-[65%] aspect-video lg:aspect-auto lg:h-full'
        }`}>
          <VideoEmbed
            url={videoUrl}
            className="w-full h-full"
            autoplay={true}
            allowFullscreen={true}
            width="100%"
            height="100%"
            onViewed30s={handleViewed30s}
          />
        </div>

        {/* Right / Bottom Panel */}
        <div className={`flex flex-col bg-white dark:bg-gray-900 min-h-0 overflow-hidden ${
          isVertical
            ? 'w-full sm:w-[400px] sm:min-w-[350px] max-h-[35vh] sm:max-h-none flex-1'
            : 'w-full lg:w-[35%] max-h-[40vh] lg:max-h-none lg:h-full overflow-y-auto'
        }`}>
          {/* Author Info */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            {authorAvatar ? (
              <div className="w-10 h-10 rounded-full overflow-hidden bg-gray-200 dark:bg-gray-700 flex-shrink-0 ring-2 ring-gray-100 dark:ring-gray-800">
                <img src={authorAvatar} alt="" className="w-full h-full object-cover" />
              </div>
            ) : (
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0 text-white text-sm font-bold">
                {(authorName || '?')[0].toUpperCase()}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                {authorName || videoTitle}
              </p>
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                {rank && (
                  <span className="bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded-md font-semibold">
                    #{rank}
                  </span>
                )}
                <span>{votesCount} {t('dashboard.contests.votes') || 'votes'}</span>
              </div>
            </div>
          </div>

          {/* Title */}
          {videoTitle && (
            <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-800">
              <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">{videoTitle}</p>
            </div>
          )}

          {/* Vote + Comment buttons */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            {/* Vote Button */}
            {onVote && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  if (!isAuthor && canVote && !isVoting && !hasVoted) onVote()
                }}
                disabled={isAuthor || !canVote || isVoting || hasVoted}
                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all cursor-pointer ${
                  isAuthor
                    ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed'
                    : hasVoted
                    ? 'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 border border-green-200 dark:border-green-700'
                    : canVote
                    ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-md hover:shadow-lg active:scale-[0.98]'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed'
                }`}
              >
                <ThumbsUp className={`w-4 h-4 ${hasVoted ? 'fill-current' : ''}`} />
                {isVoting
                  ? (t('dashboard.contests.voting') || 'Vote...')
                  : isAuthor
                  ? 'Auteur'
                  : hasVoted
                  ? (t('dashboard.contests.already_voted') || 'Voté')
                  : !canVote && voteRestrictionReason
                  ? (t('dashboard.contests.restricted') || 'Restreint')
                  : (t('dashboard.contests.vote') || 'Voter')}
              </button>
            )}

            {/* Comments toggle */}
            {contestantId && (
              <button
                onClick={() => {
                  setShowComments(!showComments)
                  if (!showComments) setTimeout(() => inputRef.current?.focus(), 200)
                }}
                className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium transition-all cursor-pointer ${
                  showComments
                    ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-700'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                }`}
              >
                <MessageCircle className="w-4 h-4" />
                {commentsCount > 0 && <span>{commentsCount}</span>}
              </button>
            )}
          </div>

          {/* Vote restriction message */}
          {!canVote && voteRestrictionReason && !isAuthor && (
            <div className={`px-4 py-2.5 flex items-center gap-2 border-b border-gray-100 dark:border-gray-800 ${
              voteRestrictionReason === 'voting_not_open'
                ? 'bg-blue-50 dark:bg-blue-950/30'
                : voteRestrictionReason === 'already_voted'
                ? 'bg-green-50 dark:bg-green-950/30'
                : 'bg-amber-50 dark:bg-amber-950/30'
            }`}>
              {voteRestrictionReason === 'voting_not_open' ? (
                <Clock className="w-3.5 h-3.5 text-blue-500 dark:text-blue-400 flex-shrink-0" />
              ) : voteRestrictionReason === 'already_voted' ? (
                <ThumbsUp className="w-3.5 h-3.5 text-green-500 dark:text-green-400 flex-shrink-0 fill-current" />
              ) : (
                <Info className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400 flex-shrink-0" />
              )}
              <p className={`text-xs font-medium ${
                voteRestrictionReason === 'voting_not_open'
                  ? 'text-blue-600 dark:text-blue-300'
                  : voteRestrictionReason === 'already_voted'
                  ? 'text-green-600 dark:text-green-300'
                  : 'text-amber-600 dark:text-amber-300'
              }`}>
                {voteRestrictionReason === 'voting_not_open'
                  ? (t('dashboard.contests.voting_not_open') || "Le vote n'est pas encore ouvert pour ce concours.")
                  : voteRestrictionReason === 'already_voted'
                  ? (t('dashboard.contests.already_voted_message') || 'Vous avez d\u00e9j\u00e0 vot\u00e9 pour ce participant.')
                  : voteRestrictionReason === 'own_contestant'
                  ? (t('dashboard.contests.restriction_own_contestant_desc') || 'Vous ne pouvez pas voter pour votre propre candidature.')
                  : voteRestrictionReason === 'not_authenticated'
                  ? (t('dashboard.contests.restriction_not_authenticated_desc') || 'Veuillez vous connecter pour voter.')
                  : (t('dashboard.contests.cannot_vote') || 'Le vote est indisponible.')}
              </p>
            </div>
          )}

          {/* Comments Section */}
          {showComments && contestantId && (
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden max-h-[30vh] lg:max-h-none">
              {/* Comments List */}
              <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3">
                {commentsLoading ? (
                  <div className="text-center py-6">
                    <div className="inline-block w-5 h-5 border-2 border-gray-300 dark:border-gray-600 border-t-blue-500 rounded-full animate-spin" />
                  </div>
                ) : comments.length === 0 ? (
                  <div className="text-center py-6 text-sm text-gray-400 dark:text-gray-500">
                    {t('dashboard.contests.no_comments') || 'Aucun commentaire'}
                  </div>
                ) : (
                  <>
                    {comments.map((c) => (
                      <div key={c.id} className="flex gap-2.5">
                        <div className="w-7 h-7 rounded-full overflow-hidden bg-gray-200 dark:bg-gray-700 flex-shrink-0">
                          {c.author_avatar ? (
                            <img src={c.author_avatar} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center text-white text-[10px] font-bold">
                              {(c.author_name || '?')[0].toUpperCase()}
                            </div>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="bg-gray-50 dark:bg-gray-800 rounded-xl px-3 py-2">
                            <p className="text-xs font-semibold text-gray-900 dark:text-white">{c.author_name || 'Utilisateur'}</p>
                            <p className="text-xs text-gray-700 dark:text-gray-300 mt-0.5 break-words">{c.content || c.text}</p>
                          </div>
                          <p className="text-[10px] text-gray-400 mt-1 px-1">
                            {new Date(c.created_at).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                          </p>
                        </div>
                      </div>
                    ))}
                    <div ref={commentsEndRef} />
                  </>
                )}
              </div>

              {/* Comment Input */}
              <div className="border-t border-gray-100 dark:border-gray-800 px-3 py-2.5 bg-gray-50/50 dark:bg-gray-900/50">
                <div className="flex items-center gap-2">
                  <input
                    ref={inputRef}
                    type="text"
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmitComment() } }}
                    placeholder={t('dashboard.contests.add_comment_placeholder') || 'Ajouter un commentaire...'}
                    className="flex-1 h-9 px-3 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all"
                    disabled={submittingComment}
                  />
                  <button
                    onClick={handleSubmitComment}
                    disabled={!newComment.trim() || submittingComment}
                    className="w-9 h-9 flex items-center justify-center rounded-full bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer active:scale-95 flex-shrink-0"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
