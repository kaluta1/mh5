'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PostCard } from '@/components/feed/post-card'
import { CommentDialog } from '@/components/feed/comment-dialog'
import { socialService, Post } from '@/services/social-service'
import { useAuth } from '@/hooks/use-auth'

export default function PostDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { isAuthenticated } = useAuth()
  const postId = parseInt(params.id as string)
  
  const [post, setPost] = useState<Post | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [commentPostId, setCommentPostId] = useState<number | null>(null)

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }
    if (postId) {
      loadPost()
    }
  }, [isAuthenticated, postId, router])

  const loadPost = async () => {
    setIsLoading(true)
    try {
      const data = await socialService.getPost(postId)
      setPost(data)
    } catch (error) {
      console.error('Error loading post:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleLike = async () => {
    if (!post) return
    try {
      if (post.is_liked) {
        await socialService.unlikePost(post.id)
      } else {
        await socialService.likePost(post.id)
      }
      await loadPost()
    } catch (error) {
      console.error('Error liking post:', error)
    }
  }

  const handleReact = async (postId: number, reactionType: string) => {
    if (!post || post.id !== postId) return
    try {
      await socialService.reactToPost(postId, reactionType)
      await loadPost()
    } catch (error) {
      console.error('Error reacting to post:', error)
    }
  }

  const handleShare = async () => {
    if (!post) return
    try {
      await socialService.sharePost(post.id)
      await loadPost()
    } catch (error) {
      console.error('Error sharing post:', error)
    }
  }

  const handleComment = () => {
    setCommentPostId(postId)
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Back Button */}
        <Button
          variant="ghost"
          onClick={() => router.back()}
          className="mb-6"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Retour
        </Button>

        {/* Post */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-myfav-primary" />
          </div>
        ) : post ? (
          <PostCard
            post={post}
            onLike={handleLike}
            onComment={handleComment}
            onShare={handleShare}
            onReact={handleReact}
            showFullContent={true}
          />
        ) : (
          <div className="text-center py-12">
            <p className="text-gray-500 dark:text-gray-400">
              Post introuvable
            </p>
          </div>
        )}
      </div>

      {/* Comment Dialog */}
      {commentPostId && (
        <CommentDialog
          open={!!commentPostId}
          onOpenChange={(open) => !open && setCommentPostId(null)}
          postId={commentPostId}
          onCommentAdded={loadPost}
        />
      )}
    </div>
  )
}

