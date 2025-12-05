'use client'

import { useState } from 'react'
import { MessageCircle, Send } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { CommentItem, CommentItemProps } from './comment-item'

export interface CommentsSectionProps {
  comments: CommentItemProps[]
  onAddComment: (text: string) => Promise<void>
  onReplyComment?: (parentId: string, text: string) => Promise<void>
  isLoading?: boolean
}

export function CommentsSection({
  comments,
  onAddComment,
  onReplyComment,
  isLoading = false
}: CommentsSectionProps) {
  const { t } = useLanguage()
  const [commentText, setCommentText] = useState('')
  const [isPostingComment, setIsPostingComment] = useState(false)
  
  // S'assurer que comments est toujours un tableau
  const safeComments = Array.isArray(comments) ? comments : []

  const handlePostComment = async () => {
    if (!commentText.trim()) return

    setIsPostingComment(true)
    try {
      await onAddComment(commentText)
      setCommentText('')
    } finally {
      setIsPostingComment(false)
    }
  }

  const handleReply = async (parentId: string, text: string) => {
    if (onReplyComment) {
      await onReplyComment(parentId, text)
    }
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 md:p-8 shadow-md">
      <h2 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white mb-6">
        {t('contestant_detail.comments')} ({safeComments.length})
      </h2>

      {/* Comment Input */}
      <div className="mb-6 pb-6 border-b border-gray-200 dark:border-gray-700">
        <div className="space-y-2">
          <textarea
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            placeholder={t('contestant_detail.comment_placeholder')}
            className="w-full px-4 py-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            rows={3}
          />
          <div className="flex gap-2 justify-end">
            <Button
              onClick={handlePostComment}
              disabled={!commentText.trim() || isPostingComment || isLoading}
              className="bg-gradient-to-r from-myfav-primary to-myfav-primary-dark text-white"
            >
              <Send className="w-4 h-4 mr-2" />
              {isPostingComment ? t('contestant_detail.voting') : t('contestant_detail.add_comment')}
            </Button>
          </div>
        </div>
      </div>

      {/* Comments List */}
      <div className="space-y-4">
        {safeComments.length === 0 ? (
          <div className="text-center py-8">
            <MessageCircle className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
            <p className="text-gray-600 dark:text-gray-400">
              {t('contestant_detail.no_comments')}
            </p>
          </div>
        ) : (
          safeComments.map(comment => (
            <CommentItem
              key={comment.id}
              {...comment}
              onReply={onReplyComment ? handleReply : undefined}
            />
          ))
        )}
      </div>
    </div>
  )
}
