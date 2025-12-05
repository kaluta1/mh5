'use client'

import { useState } from 'react'
import { ThumbsUp, MessageCircle, Heart, Smile, ThumbsDown, Star, Reply } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { commentsService, Comment } from '@/lib/services/comments-service'
import { useToast } from '@/components/ui/toast'
import { MentionAutocomplete } from './mention-autocomplete'
import Image from 'next/image'

interface CommentItemProps {
  comment: Comment
  depth?: number
  onReply?: (parentId: number, text: string) => Promise<void>
  onUpdate?: (commentId: number) => void
  currentUserId?: number
  commenters?: Array<{
    id: number
    username: string
    name: string
    avatar_url?: string
  }>
}

export function CommentItem({ 
  comment, 
  depth = 0, 
  onReply, 
  onUpdate,
  currentUserId,
  commenters = []
}: CommentItemProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [showReplyForm, setShowReplyForm] = useState(false)
  const [replyText, setReplyText] = useState('')
  const [isSubmittingReply, setIsSubmittingReply] = useState(false)
  const [isLiked, setIsLiked] = useState(comment.is_liked || false)
  const [likeCount, setLikeCount] = useState(comment.like_count || 0)
  const [showReactions, setShowReactions] = useState(false)
  // Les réponses de niveau 2+ sont masquées par défaut
  const isReply = comment.parent_id !== null && comment.parent_id !== undefined
  const [expandedReplies, setExpandedReplies] = useState(!isReply) // false pour les réponses, true pour les commentaires principaux
  const [loadingReplies, setLoadingReplies] = useState(false)
  // Utiliser les réponses déjà présentes dans le commentaire, ou un tableau vide
  const [replies, setReplies] = useState<Comment[]>(comment.replies || [])

  // Pas de limite de profondeur - afficher tous les niveaux au même niveau visuel
  const isMaxDepth = false

  // Extraire les mentions dans le texte (format @username) - toujours afficher les mentions en couleur
  const parseMentions = (text: string) => {
    const mentionRegex = /@(\w+)/g
    const parts = []
    let lastIndex = 0
    let match

    while ((match = mentionRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push({ type: 'text', content: text.substring(lastIndex, match.index) })
      }
      parts.push({ type: 'mention', username: match[1], fullMatch: match[0] })
      lastIndex = match.index + match[0].length
    }

    if (lastIndex < text.length) {
      parts.push({ type: 'text', content: text.substring(lastIndex) })
    }

    return parts.length > 0 ? parts : [{ type: 'text', content: text }]
  }

  const handleLike = async () => {
    try {
      if (isLiked) {
        await commentsService.unlikeComment(comment.id)
        setIsLiked(false)
        setLikeCount(prev => Math.max(0, prev - 1))
        addToast(t('dashboard.contests.like_removed') || 'Like retiré', 'success')
      } else {
        await commentsService.likeComment(comment.id)
        setIsLiked(true)
        setLikeCount(prev => prev + 1)
        addToast(t('dashboard.contests.like_added') || 'Like ajouté', 'success')
      }
      if (onUpdate) onUpdate(Number(comment.id))
    } catch (error: any) {
      console.error('Error toggling like:', error)
      addToast(error.response?.data?.detail || 'Erreur lors du like', 'error')
    }
  }

  const handleReply = async () => {
    if (!replyText.trim() || !onReply || isSubmittingReply) return

    try {
      setIsSubmittingReply(true)
      // Ajouter @username si on répond à un commentaire (depth > 0)
      let finalText = replyText
      if (depth > 0 && comment.author_name) {
        const username = comment.author_name.split(' ')[0] // Prendre le prénom
        if (!replyText.startsWith(`@${username}`)) {
          finalText = `@${username} ${replyText}`
        }
      }
      
      await onReply(Number(comment.id), finalText)
      setReplyText('')
      setShowReplyForm(false)
      // Recharger les réponses
      await loadReplies()
    } catch (error: any) {
      console.error('Error adding reply:', error)
      addToast(error.response?.data?.detail || 'Erreur lors de l\'ajout de la réponse', 'error')
    } finally {
      setIsSubmittingReply(false)
    }
  }

  const loadReplies = async () => {
    // Si les réponses sont déjà présentes, ne pas les recharger
    if (replies.length > 0 || loadingReplies) return
    
    setLoadingReplies(true)
    try {
      const response = await commentsService.getCommentReplies(comment.id)
      setReplies(response.comments || [])
    } catch (error) {
      console.error('Error loading replies:', error)
      // En cas d'erreur, utiliser les réponses déjà présentes dans le commentaire
      if (comment.replies && comment.replies.length > 0) {
        setReplies(comment.replies)
      }
    } finally {
      setLoadingReplies(false)
    }
  }

  const textParts = parseMentions(comment.content || comment.text || '')
  const showMentions = depth >= 2 && textParts.some(p => p.type === 'mention')

  return (
    <>
      <div className={`border-b border-gray-200 dark:border-gray-700 last:border-b-0 pb-3 last:pb-0 ${isReply ? 'pl-4 md:pl-6 border-l-2 border-gray-200 dark:border-gray-700 ml-4 md:ml-6' : ''}`}>
        <div className="flex gap-3">
          <div className="flex-shrink-0">
            {comment.author_avatar ? (
              <Image
                src={comment.author_avatar}
                alt={comment.author_name}
                width={40}
                height={40}
                className="w-10 h-10 rounded-full"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-myfav-primary to-myfav-primary-dark flex items-center justify-center text-white">
                {comment.author_name.charAt(0).toUpperCase()}
              </div>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-sm text-gray-900 dark:text-white">
                  {comment.author_name}
                </p>
                {isReply && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
                    <Reply className="w-3 h-3" />
                    <span>{t('dashboard.contests.reply') || 'Réponse'}</span>
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300 mt-1 break-words">
                {textParts.map((part, idx) => {
                  if (part.type === 'mention') {
                    return (
                      <span key={idx} className="text-myfav-primary dark:text-myfav-primary-light font-medium">
                        {part.fullMatch}
                      </span>
                    )
                  }
                  return <span key={idx}>{part.content}</span>
                })}
              </p>
            </div>
            
            {/* Actions bar */}
            <div className="flex items-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
              <button
                onClick={handleLike}
                className={`flex items-center gap-1 hover:text-blue-600 dark:hover:text-blue-400 transition-colors ${
                  isLiked ? 'text-blue-600 dark:text-blue-400' : ''
                }`}
              >
                <ThumbsUp className={`w-4 h-4 ${isLiked ? 'fill-current' : ''}`} />
                <span>{likeCount > 0 ? likeCount : ''}</span>
              </button>
              
              {!isMaxDepth && (
                <button
                  onClick={() => setShowReplyForm(!showReplyForm)}
                  className="flex items-center gap-1 text-myfav-primary dark:text-myfav-primary-light hover:text-myfav-primary-dark dark:hover:text-myfav-primary transition-colors ml-auto"
                >
                  <Reply className="w-4 h-4" />
                  <span>{t('dashboard.contests.reply') || 'Répondre'}</span>
                </button>
              )}
              
              <span className="text-xs">
                {new Date(comment.created_at).toLocaleDateString('fr-FR', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </span>
            </div>

            {/* Reply form */}
            {showReplyForm && !isMaxDepth && onReply && (
              <div className="mt-3 space-y-2">
                <MentionAutocomplete
                  value={replyText}
                  onChange={setReplyText}
                  onMentionSelect={(username) => {
                    console.log('Mention sélectionnée:', username)
                  }}
                  users={commenters}
                  placeholder={t('dashboard.contests.reply_placeholder') || 'Écrire une réponse...'}
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-full bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary focus:border-transparent transition-all"
                  disabled={isSubmittingReply}
                />
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => {
                      setShowReplyForm(false)
                      setReplyText('')
                    }}
                    className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                  >
                    {t('dashboard.contests.cancel') || 'Annuler'}
                  </button>
                  <button
                    onClick={handleReply}
                    disabled={!replyText.trim() || isSubmittingReply}
                    className="px-4 py-1.5 text-sm bg-myfav-primary hover:bg-myfav-primary-dark text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {isSubmittingReply ? t('dashboard.contests.sending') || 'Envoi...' : t('dashboard.contests.reply') || 'Répondre'}
                  </button>
                </div>
              </div>
            )}

            {/* Replies toggle */}
            {comment.reply_count > 0 && (
              <div className="mt-2">
                <button
                  onClick={() => {
                    const newExpanded = !expandedReplies
                    setExpandedReplies(newExpanded)
                    // Charger les réponses seulement si elles ne sont pas déjà présentes
                    if (newExpanded && replies.length === 0 && (!comment.replies || comment.replies.length === 0)) {
                      loadReplies()
                    } else if (newExpanded && replies.length === 0 && comment.replies && comment.replies.length > 0) {
                      // Utiliser les réponses déjà présentes dans le commentaire
                      setReplies(comment.replies)
                    }
                  }}
                  className="text-xs text-myfav-primary dark:text-myfav-primary-light hover:underline font-medium"
                >
                  {expandedReplies 
                    ? (t('dashboard.contests.hide_replies') || `Masquer ${comment.reply_count} réponse(s)`).replace('{count}', String(comment.reply_count))
                    : (t('dashboard.contests.show_replies') || `Voir ${comment.reply_count} réponse(s)`).replace('{count}', String(comment.reply_count))
                  }
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Replies - toutes les réponses (niveau 2, 3, 4+) ont exactement le même padding, alignées au même niveau */}
      {expandedReplies && comment.reply_count > 0 && (
        <>
          {loadingReplies ? (
            <div className="text-xs text-gray-500 dark:text-gray-400 py-2 pl-4 md:pl-6">
              {t('dashboard.contests.loading') || 'Chargement...'}
            </div>
          ) : (
            replies.map((reply) => (
              <CommentItem
                key={reply.id}
                comment={reply}
                depth={0}
                onReply={onReply}
                onUpdate={onUpdate}
                currentUserId={currentUserId}
                commenters={commenters}
              />
            ))
          )}
        </>
      )}
    </>
  )
}

