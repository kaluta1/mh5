'use client'

import { useState } from 'react'
import { MessageCircle, Reply } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'

export interface CommentItemProps {
  id: string
  author_name: string
  author_avatar?: string
  text: string
  created_at: string
  target_type: 'contest' | 'photo' | 'video'
  target_id?: string
  replies?: CommentItemProps[]
  onReply?: (parentCommentId: string, text: string) => void
  depth?: number
}

export function CommentItem({
  id,
  author_name,
  author_avatar,
  text,
  created_at,
  target_type,
  target_id,
  replies = [],
  onReply,
  depth = 0
}: CommentItemProps) {
  const { t } = useLanguage()
  const [showReplyForm, setShowReplyForm] = useState(false)
  const [replyText, setReplyText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmitReply = async () => {
    if (!replyText.trim() || !onReply) return

    setIsSubmitting(true)
    try {
      onReply(id, replyText)
      setReplyText('')
      setShowReplyForm(false)
    } finally {
      setIsSubmitting(false)
    }
  }

  const maxDepth = 2
  const isMaxDepth = depth >= maxDepth

  return (
    <div className={`pb-4 ${depth > 0 ? 'ml-4 md:ml-8 border-l-2 border-gray-200 dark:border-gray-700 pl-4' : 'border-b border-gray-200 dark:border-gray-700'} last:border-b-0`}>
      <div className="flex gap-3">
        {/* Avatar */}
        <div className="flex-shrink-0">
          {author_avatar ? (
            <img
              src={author_avatar}
              alt={author_name}
              className="w-10 h-10 rounded-full object-cover"
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-myfav-primary to-myfav-primary-dark flex items-center justify-center text-white font-bold text-sm">
              {author_name.charAt(0).toUpperCase()}
            </div>
          )}
        </div>

        {/* Comment Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <h4 className="font-semibold text-gray-900 dark:text-white text-sm">
              {author_name}
            </h4>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {new Date(created_at).toLocaleDateString('fr-FR', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
              })}
            </span>
          </div>

          {/* Comment Text */}
          <p className="text-sm text-gray-700 dark:text-gray-300 mt-1 break-words">
            {text}
          </p>

          {/* Target Type Badge */}
          {target_type !== 'contest' && depth === 0 && (
            <span className="inline-block mt-2 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs text-gray-600 dark:text-gray-400">
              {target_type === 'photo' ? t('contestant_detail.comment_on_photo') : t('contestant_detail.comment_on_video')}
            </span>
          )}

          {/* Reply Button */}
          {!isMaxDepth && onReply && (
            <div className="mt-2">
              <Button
                onClick={() => setShowReplyForm(!showReplyForm)}
                variant="ghost"
                size="sm"
                className="text-xs text-myfav-primary hover:bg-myfav-primary/10"
              >
                <Reply className="w-3 h-3 mr-1" />
                {t('contestant_detail.reply')}
              </Button>
            </div>
          )}

          {/* Reply Form */}
          {showReplyForm && (
            <div className="mt-3 space-y-2">
              <textarea
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                placeholder={t('contestant_detail.reply_placeholder')}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary text-sm"
                rows={2}
              />
              <div className="flex gap-2 justify-end">
                <Button
                  onClick={() => {
                    setShowReplyForm(false)
                    setReplyText('')
                  }}
                  variant="outline"
                  size="sm"
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={handleSubmitReply}
                  disabled={!replyText.trim() || isSubmitting}
                  size="sm"
                  className="bg-gradient-to-r from-myfav-primary to-myfav-primary-dark text-white"
                >
                  {isSubmitting ? t('contestant_detail.voting') : t('contestant_detail.reply')}
                </Button>
              </div>
            </div>
          )}

          {/* Nested Replies */}
          {replies && replies.length > 0 && (
            <div className="mt-4 space-y-4">
              {replies.map(reply => (
                <CommentItem
                  key={reply.id}
                  {...reply}
                  onReply={onReply}
                  depth={(depth || 0) + 1}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
