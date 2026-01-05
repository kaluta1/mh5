'use client'

import { useState } from 'react'
import Link from 'next/link'
import { formatDistanceToNow } from 'date-fns'
import { fr } from 'date-fns/locale'
import { 
  Heart, 
  MessageCircle, 
  Share2, 
  MoreHorizontal,
  Repeat2
} from 'lucide-react'
import { Post } from '@/services/social-service'
import { UserAvatar } from '@/components/user/user-avatar'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ReactionButton } from './reaction-button'
import { PostMediaGallery } from './post-media-gallery'
import { PostPoll } from './post-poll'
import { LinkPreview } from './link-preview'
import { cn } from '@/lib/utils'

interface PostCardProps {
  post: Post
  onLike?: (postId: number) => void
  onComment?: (postId: number) => void
  onShare?: (postId: number) => void
  onReact?: (postId: number, reactionType: string) => void
  onDelete?: (postId: number) => void
  showFullContent?: boolean
}

export function PostCard({ 
  post, 
  onLike, 
  onComment, 
  onShare, 
  onReact,
  onDelete,
  showFullContent = false 
}: PostCardProps) {
  const [isLiked, setIsLiked] = useState(post.is_liked)
  const [likesCount, setLikesCount] = useState(post.likes_count)

  const handleLike = () => {
    setIsLiked(!isLiked)
    setLikesCount(prev => isLiked ? prev - 1 : prev + 1)
    onLike?.(post.id)
  }

  const hasMedia = post.media && post.media.length > 0
  const hasPoll = post.poll !== undefined
  const hasLink = post.content.includes('http')

  return (
    <article className="hover:bg-gray-50 dark:hover:bg-gray-900/50 transition-colors px-4 py-3">
      <div className="flex gap-3">
        {/* Avatar */}
        <div className="flex-shrink-0">
          <Link href={`/profile/${post.author_id}`}>
            <UserAvatar 
              user={post.author}
              className="w-12 h-12"
            />
          </Link>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-start justify-between mb-1">
            <div className="flex items-center gap-2 flex-wrap">
              <Link 
                href={`/profile/${post.author_id}`}
                className="font-semibold text-gray-900 dark:text-white hover:underline"
              >
                {post.author?.full_name || post.author?.username}
              </Link>
              <span className="text-gray-500 dark:text-gray-400 text-[15px]">
                @{post.author?.username}
              </span>
              <span className="text-gray-500 dark:text-gray-400">·</span>
              <span className="text-gray-500 dark:text-gray-400 text-[15px]">
                {formatDistanceToNow(new Date(post.created_at), { addSuffix: true, locale: fr })}
              </span>
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  className="h-8 w-8 rounded-full hover:bg-blue-100 dark:hover:bg-blue-900/20"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {onDelete && (
                  <DropdownMenuItem 
                    onClick={() => onDelete(post.id)}
                    className="text-red-600 dark:text-red-400"
                  >
                    Supprimer
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem>Signaler</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Text Content */}
          <div className={cn(
            "text-gray-900 dark:text-white text-[15px] leading-6 whitespace-pre-wrap break-words mb-3",
            !showFullContent && "line-clamp-none"
          )}>
            {post.content}
          </div>

          {/* Media */}
          {hasMedia && (
            <div className="mb-3 rounded-2xl overflow-hidden">
              <PostMediaGallery media={post.media!} />
            </div>
          )}

          {/* Poll */}
          {hasPoll && (
            <div className="mb-3">
              <PostPoll poll={post.poll!} postId={post.id} />
            </div>
          )}

          {/* Link Preview */}
          {hasLink && !hasMedia && !hasPoll && (
            <div className="mb-3">
              <LinkPreview url={extractUrl(post.content)} />
            </div>
          )}

          {/* Actions - Twitter style */}
          <div className="flex items-center justify-between max-w-md mt-3">
            {/* Comment */}
            <button
              onClick={() => onComment?.(post.id)}
              className="group flex items-center gap-2 text-gray-500 dark:text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
            >
              <div className="p-2 rounded-full group-hover:bg-blue-100 dark:group-hover:bg-blue-900/20 transition-colors">
                <MessageCircle className="h-5 w-5" />
              </div>
              {post.comments_count > 0 && (
                <span className="text-sm">{post.comments_count}</span>
              )}
            </button>

            {/* Share/Retweet */}
            <button
              onClick={() => onShare?.(post.id)}
              className="group flex items-center gap-2 text-gray-500 dark:text-gray-400 hover:text-green-500 dark:hover:text-green-400 transition-colors"
            >
              <div className="p-2 rounded-full group-hover:bg-green-100 dark:group-hover:bg-green-900/20 transition-colors">
                <Repeat2 className="h-5 w-5" />
              </div>
              {post.shares_count > 0 && (
                <span className="text-sm">{post.shares_count}</span>
              )}
            </button>

            {/* Like/Reaction */}
            <ReactionButton
              postId={post.id}
              isLiked={isLiked}
              likesCount={likesCount}
              userReaction={post.user_reaction}
              onLike={handleLike}
              onReact={onReact}
            />

            {/* Share */}
            <button
              onClick={() => onShare?.(post.id)}
              className="group flex items-center gap-2 text-gray-500 dark:text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
            >
              <div className="p-2 rounded-full group-hover:bg-blue-100 dark:group-hover:bg-blue-900/20 transition-colors">
                <Share2 className="h-5 w-5" />
              </div>
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}

function extractUrl(text: string): string | null {
  const urlRegex = /(https?:\/\/[^\s]+)/g
  const match = text.match(urlRegex)
  return match ? match[0] : null
}
