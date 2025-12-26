'use client'

import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { fr } from 'date-fns/locale'
import { Send, Heart } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { UserAvatar } from '@/components/user/user-avatar'
import { socialService, PostComment } from '@/services/social-service'
import { cn } from '@/lib/utils'

interface CommentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  postId: number
  onCommentAdded?: () => void
}

export function CommentDialog({ open, onOpenChange, postId, onCommentAdded }: CommentDialogProps) {
  const [comments, setComments] = useState<PostComment[]>([])
  const [content, setContent] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (open && postId) {
      loadComments()
    }
  }, [open, postId])

  const loadComments = async () => {
    setIsLoading(true)
    try {
      const data = await socialService.getPostComments(postId)
      setComments(data)
    } catch (error) {
      console.error('Error loading comments:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!content.trim()) return

    setIsSubmitting(true)
    try {
      await socialService.createComment(postId, { content: content.trim() })
      setContent('')
      await loadComments()
      onCommentAdded?.()
    } catch (error) {
      console.error('Error creating comment:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleLike = async (commentId: number) => {
    try {
      await socialService.likeComment(commentId)
      await loadComments()
    } catch (error) {
      console.error('Error liking comment:', error)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Commentaires</DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 min-h-0">
          {isLoading ? (
            <div className="text-center py-8 text-gray-500">Chargement...</div>
          ) : comments.length === 0 ? (
            <div className="text-center py-8 text-gray-500">Aucun commentaire</div>
          ) : (
            comments.map((comment) => (
              <div key={comment.id} className="flex gap-3">
                <UserAvatar user={comment.author} className="w-8 h-8" />
                <div className="flex-1">
                  <div className="bg-gray-100 dark:bg-gray-700 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm text-gray-900 dark:text-white">
                        {comment.author?.full_name || comment.author?.username}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {formatDistanceToNow(new Date(comment.created_at), { addSuffix: true, locale: fr })}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                      {comment.content}
                    </p>
                  </div>
                  <div className="flex items-center gap-4 mt-1 ml-2">
                    <button
                      onClick={() => handleLike(comment.id)}
                      className={cn(
                        "flex items-center gap-1 text-xs text-gray-500 hover:text-myfav-primary",
                        comment.is_liked && "text-myfav-primary"
                      )}
                    >
                      <Heart className={cn("h-3 w-3", comment.is_liked && "fill-current")} />
                      {comment.likes_count}
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="border-t pt-4 space-y-2">
          <Textarea
            placeholder="Ajouter un commentaire..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="min-h-[80px] resize-none"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.ctrlKey) {
                handleSubmit()
              }
            }}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Ctrl+Entrée pour publier</span>
            <Button
              onClick={handleSubmit}
              disabled={!content.trim() || isSubmitting}
              size="sm"
            >
              <Send className="h-4 w-4 mr-2" />
              {isSubmitting ? 'Publication...' : 'Publier'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

