'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { commentsService, Comment, CommentListResponse } from '@/lib/services/comments-service'
import { CommentItem } from './comment-item'
import { MentionAutocomplete } from './mention-autocomplete'

interface CommentsSectionProps {
  contestantId: string
  initialCount: number
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  onCountChange?: (count: number) => void
}

export function CommentsSection({ 
  contestantId, 
  initialCount, 
  isOpen, 
  onOpenChange, 
  onCountChange 
}: CommentsSectionProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [commentsList, setCommentsList] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [currentCount, setCurrentCount] = useState(initialCount)
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [skip, setSkip] = useState(0)
  const limit = 20
  const observerTarget = useRef<HTMLDivElement>(null)
  const [commenters, setCommenters] = useState<Array<{
    id: number
    username: string
    name: string
    avatar_url?: string
  }>>([])

  const loadComments = async (reset: boolean = false) => {
    if (loading) return
    
    try {
      setLoading(true)
      const currentSkip = reset ? 0 : skip
      const response: CommentListResponse = await commentsService.getContestantComments(
        contestantId, 
        currentSkip, 
        limit
      )
      
      console.log('Comments loaded:', response.comments.length, 'Total:', response.total)
      console.log('First comment:', response.comments[0])
      
      if (reset) {
        setCommentsList(response.comments)
        setSkip(limit)
      } else {
        setCommentsList(prev => [...prev, ...response.comments])
        setSkip(prev => prev + limit)
      }
      
      setHasMore(response.comments.length === limit && response.comments.length < response.total)
      setCurrentCount(response.total)
      if (onCountChange) onCountChange(response.total)
    } catch (error) {
      console.error('Error loading comments:', error)
      addToast('Erreur lors du chargement des commentaires', 'error')
    } finally {
      setLoading(false)
    }
  }

  // Load comments and commenters when dialog opens
  useEffect(() => {
    if (isOpen) {
      setSkip(0)
      setHasMore(true)
      loadComments(true)
      // Charger la liste des commentateurs
      commentsService.getContestantCommenters(contestantId).then(setCommenters)
    } else {
      // Reset when dialog closes
      setCommentsList([])
      setSkip(0)
      setHasMore(true)
      setCommenters([])
    }
  }, [isOpen, contestantId])

  // Infinite scroll observer
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading && isOpen) {
          loadComments(false)
        }
      },
      { threshold: 0.1 }
    )

    const currentTarget = observerTarget.current
    if (currentTarget) {
      observer.observe(currentTarget)
    }

    return () => {
      if (currentTarget) {
        observer.unobserve(currentTarget)
      }
    }
  }, [hasMore, loading, isOpen, skip])

  const handleAddComment = async () => {
    if (!newComment.trim() || isSubmitting) return

    const commentText = newComment.trim()
    setNewComment('')
    setIsSubmitting(true)

    try {
      // Ajouter le commentaire de manière optimiste
      const newCommentData = await commentsService.addContestantComment(contestantId, commentText)
      
      // Ajouter le nouveau commentaire en haut de la liste
      setCommentsList(prev => [newCommentData, ...prev])
      setCurrentCount(prev => prev + 1)
      if (onCountChange) onCountChange(currentCount + 1)
      
      addToast(t('dashboard.contests.comment_added') || 'Commentaire ajouté', 'success')
    } catch (error: any) {
      console.error('Error adding comment:', error)
      // Restaurer le texte en cas d'erreur
      setNewComment(commentText)
      addToast(error.response?.data?.detail || 'Erreur lors de l\'ajout du commentaire', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReply = async (parentId: number, text: string) => {
    try {
      // Ajouter la réponse de manière optimiste
      const newReply = await commentsService.addContestantComment(contestantId, text, parentId)
      
      // Trouver le commentaire parent et ajouter la réponse
      const updateCommentWithReply = (comment: Comment): Comment => {
        if (comment.id === parentId) {
          return {
            ...comment,
            replies: [...(comment.replies || []), newReply],
            reply_count: (comment.reply_count || 0) + 1
          }
        }
        if (comment.replies && comment.replies.length > 0) {
          return {
            ...comment,
            replies: comment.replies.map(updateCommentWithReply)
          }
        }
        return comment
      }
      
      setCommentsList(prev => prev.map(updateCommentWithReply))
      setCurrentCount(prev => prev + 1)
      if (onCountChange) onCountChange(currentCount + 1)
      
      addToast(t('dashboard.contests.reply_added') || 'Réponse ajoutée', 'success')
    } catch (error: any) {
      console.error('Error adding reply:', error)
      addToast(error.response?.data?.detail || 'Erreur lors de l\'ajout de la réponse', 'error')
      throw error
    }
  }

  const handleUpdateComment = async (commentId: number) => {
    // La mise à jour est déjà gérée dans CommentItem pour les likes
    // Cette fonction peut être utilisée pour d'autres mises à jour si nécessaire
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700">
        <DialogHeader>
          <DialogTitle className="text-gray-900 dark:text-white">
            {t('dashboard.contests.comments')} ({currentCount})
          </DialogTitle>
          <DialogDescription className="text-gray-600 dark:text-gray-400">
            {t('dashboard.contests.comments_description') || 'Partagez vos pensées sur ce participant'}
          </DialogDescription>
        </DialogHeader>
        
        <div className="flex-1 overflow-y-auto space-y-0 mt-4 pr-2">
          {commentsList.length > 0 ? (
            <>
              {commentsList.map((comment) => (
                <CommentItem
                  key={comment.id}
                  comment={comment}
                  depth={0}
                  onReply={handleReply}
                  onUpdate={handleUpdateComment}
                  commenters={commenters}
                />
              ))}
              {/* Infinite scroll trigger */}
              {hasMore && (
                <div ref={observerTarget} className="h-10 flex items-center justify-center">
                  {loading && (
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      {t('dashboard.contests.loading') || 'Chargement...'}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : !loading ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              {t('dashboard.contests.no_comments') || 'Aucun commentaire pour le moment'}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              {t('dashboard.contests.loading') || 'Chargement...'}
            </div>
          )}
        </div>

        {/* Add Comment Form */}
        <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4">
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="flex-1 space-y-2">
                <MentionAutocomplete
                  value={newComment}
                  onChange={setNewComment}
                  onMentionSelect={(username) => {
                    // La mention est déjà ajoutée par le composant
                    console.log('Mention sélectionnée:', username)
                  }}
                  users={commenters}
                  placeholder={t('dashboard.contests.add_comment_placeholder') || 'Ajouter un commentaire...'}
                  className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-full bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary focus:border-transparent transition-all"
                  disabled={isSubmitting}
                />
                <div className="flex items-center justify-between">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('dashboard.contests.mention_hint') || 'Tapez @ pour mentionner quelqu\'un'}
                  </p>
                  <Button
                    onClick={handleAddComment}
                    disabled={!newComment.trim() || isSubmitting}
                    className="px-6 py-2 bg-myfav-primary hover:bg-myfav-primary-dark text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? t('dashboard.contests.sending') || 'Envoi...' : t('dashboard.contests.send') || 'Envoyer'}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

