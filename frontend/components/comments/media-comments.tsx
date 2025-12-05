'use client'

import { useState } from 'react'
import { MessageCircle, Send, Heart, Image, Video } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { CommentItem, CommentItemProps } from './comment-item'

export interface MediaCommentsProps {
  mediaId: string
  mediaType: 'photo' | 'video'
  comments: CommentItemProps[]
  onAddComment: (text: string) => Promise<void>
  onReplyComment?: (parentId: string, text: string) => Promise<void>
  isLoading?: boolean
}

export function MediaComments({
  mediaId,
  mediaType,
  comments,
  onAddComment,
  onReplyComment,
  isLoading = false
}: MediaCommentsProps) {
  const { t } = useLanguage()
  const [commentText, setCommentText] = useState('')
  const [isPostingComment, setIsPostingComment] = useState(false)

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
    <div className="bg-gray-900 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700 flex-shrink-0">
        <MessageCircle className="w-4 h-4 text-myfav-primary" />
        <h3 className="text-gray-200 font-semibold text-sm">
          {t('contestant_detail.comments')} ({comments.length})
        </h3>
      </div>

      {/* Media Context Bar */}
      <div className="px-4 py-2 bg-gray-800/50 border-b border-gray-700 flex items-center gap-2 flex-shrink-0">
        {mediaType === 'video' ? (
          <Video className="w-3 h-3 text-blue-400" />
        ) : (
          <Image className="w-3 h-3 text-purple-400" />
        )}
        <span className="text-xs text-gray-400">
          {mediaType === 'video' ? 'Commentaires vidéo' : 'Commentaires photo'}
        </span>
      </div>

      {/* Comments List - Scrollable */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {comments.length === 0 ? (
          <div className="text-center py-8">
            <MessageCircle className="w-8 h-8 text-gray-600 mx-auto mb-2 opacity-50" />
            <p className="text-gray-400 text-xs">
              {t('contestant_detail.no_comments')}
            </p>
          </div>
        ) : (
          comments.map(comment => (
            <div key={comment.id} className="group">
              <div className="flex gap-2 hover:bg-gray-800/50 rounded-lg p-2 transition-colors">
                {/* Avatar */}
                <div className="flex-shrink-0">
                  {comment.author_avatar ? (
                    <img
                      src={comment.author_avatar}
                      alt={comment.author_name}
                      className="w-7 h-7 rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-myfav-primary to-myfav-primary-dark flex items-center justify-center text-white font-bold text-xs">
                      {comment.author_name.charAt(0).toUpperCase()}
                    </div>
                  )}
                </div>

                {/* Comment Content */}
                <div className="flex-1 min-w-0">
                  <div className="bg-gray-800 rounded-lg px-3 py-2 border-l-2 border-myfav-primary/50">
                    <h4 className="font-semibold text-gray-200 text-xs">
                      {comment.author_name}
                    </h4>
                    <p className="text-xs text-gray-300 mt-1 break-words">
                      {comment.text}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 mt-1 px-2 text-xs text-gray-400">
                    <span>
                      {new Date(comment.created_at).toLocaleDateString('fr-FR', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                    <button className="hover:text-myfav-primary transition-colors flex items-center gap-1">
                      <Heart className="w-3 h-3" />
                      <span>{t('contestant_detail.like_comment')}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Comment Input */}
      <div className="border-t border-gray-700 px-4 py-3 flex-shrink-0 space-y-2">
        <div className="flex gap-2">
          <textarea
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            placeholder={t('contestant_detail.comment_placeholder')}
            className="flex-1 px-3 py-2 rounded-lg border border-gray-700 bg-gray-800 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-myfav-primary text-xs resize-none"
            rows={2}
          />
        </div>
        <div className="flex gap-2 justify-end">
          <Button
            onClick={handlePostComment}
            disabled={!commentText.trim() || isPostingComment || isLoading}
            size="sm"
            className="bg-gradient-to-r from-myfav-primary to-myfav-primary-dark text-white text-xs h-8"
          >
            <Send className="w-3 h-3 mr-1" />
            {isPostingComment ? t('contestant_detail.voting') : t('contestant_detail.add_comment')}
          </Button>
        </div>
      </div>
    </div>
  )
}
