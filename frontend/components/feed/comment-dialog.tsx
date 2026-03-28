'use client'

import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { fr, enUS } from 'date-fns/locale'
import { Send, Heart } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { UserAvatar } from '@/components/user/user-avatar'
import { socialService, PostComment } from '@/services/social-service'
import { cn } from '@/lib/utils'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { MentionTextarea } from '@/components/feed/mention-textarea'
import { MentionText } from '@/components/feed/mention-text'

interface CommentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  postId: number
  onCommentAdded?: () => void
}

export function CommentDialog({ open, onOpenChange, postId, onCommentAdded }: CommentDialogProps) {
  const { t, language } = useLanguage()
  const { addToast } = useToast()
  const [comments, setComments] = useState<PostComment[]>([])
  const [content, setContent] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  
  // Get date-fns locale based on current language
  const dateLocale = language === 'fr' ? fr : enUS

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
      // Show success message
      addToast(t('dashboard.feed.comment_success') || 'Comment posted successfully!', 'success')
    } catch (error) {
      console.error('Error creating comment:', error)
      addToast(t('dashboard.feed.comment_error') || 'Failed to post comment. Please try again.', 'error')
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
          <DialogTitle>{t('dashboard.feed.comments') || 'Comments'}</DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 min-h-0">
          {isLoading ? (
            <div className="text-center py-8 text-gray-500">{t('dashboard.feed.loading') || 'Loading...'}</div>
          ) : comments.length === 0 ? (
            <div className="text-center py-8 text-gray-500">{t('dashboard.feed.no_comments') || 'No comments'}</div>
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
                        {formatDistanceToNow(new Date(comment.created_at), { addSuffix: true, locale: dateLocale })}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                      <MentionText text={comment.content} />
                    </p>
                  </div>
                  <div className="flex items-center gap-4 mt-1 ml-2">
                    <button
                      onClick={() => handleLike(comment.id)}
                      className={cn(
                        "flex items-center gap-1 text-xs text-gray-500 hover:text-myhigh5-primary",
                        comment.is_liked && "text-myhigh5-primary"
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
          <MentionTextarea
            placeholder={t('dashboard.feed.add_comment_placeholder') || 'Add a comment...'}
            value={content}
            onChange={setContent}
            className="min-h-[80px] resize-none"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.ctrlKey) {
                handleSubmit()
              }
            }}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">{t('dashboard.feed.comment_shortcut') || 'Ctrl+Enter to post'}</span>
            <Button
              onClick={handleSubmit}
              disabled={!content.trim() || isSubmitting}
              size="sm"
            >
              <Send className="h-4 w-4 mr-2" />
              {isSubmitting ? (t('dashboard.feed.posting') || 'Posting...') : (t('dashboard.feed.post') || 'Post')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

