'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PostCard } from '@/components/feed/post-card'
import { CommentDialog } from '@/components/feed/comment-dialog'
import { PostDialog } from '@/components/feed/post-dialog'
import { socialService, Post } from '@/services/social-service'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'

export default function PostDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { isAuthenticated, user } = useAuth()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const postId = parseInt(params.id as string)
  
  const [post, setPost] = useState<Post | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [commentPostId, setCommentPostId] = useState<number | null>(null)
  const [isPostDialogOpen, setIsPostDialogOpen] = useState(false)

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

  const handleRepost = async (pid: number) => {
    if (!post || post.id !== pid) return
    try {
      await socialService.sharePost(post.id)
      await loadPost()
    } catch (error) {
      console.error('Error reposting:', error)
      addToast(t('dashboard.feed.repost_failed'), 'error', 6000)
    }
  }

  const handleShareOut = async (p: Post) => {
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    const referralCode = user?.personal_referral_code?.trim()
    const shareUrl = referralCode
      ? `${origin}/s/f/${p.id}?ref=${encodeURIComponent(referralCode)}`
      : `${origin}/s/f/${p.id}`
    const title = p.author?.full_name || p.author?.username || 'MyHigh5'
    const text = (p.content || '').slice(0, 280)
    try {
      if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
        await navigator.share({ title, text, url: shareUrl })
        return
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
    }
    try {
      await navigator.clipboard.writeText(shareUrl)
      addToast(t('dashboard.feed.link_copied'), 'success', 4000)
    } catch {
      addToast(t('dashboard.feed.share_failed'), 'error', 6000)
    }
  }

  const handleComment = () => {
    setCommentPostId(postId)
  }

  const handleDelete = async (postIdToDelete: number) => {
    if (!confirm('Are you sure you want to delete this post?')) return

    try {
      await socialService.deletePost(postIdToDelete)
      router.push('/dashboard/feed')
    } catch (error) {
      console.error('Error deleting post:', error)
    }
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
          {t('common.back')}
        </Button>

        {/* Post */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
          </div>
        ) : post ? (
          <PostCard
            post={post}
            currentUserId={user?.id}
            onLike={handleLike}
            onComment={handleComment}
            onRepost={handleRepost}
            onShareOut={handleShareOut}
            onReact={handleReact}
            onEdit={() => setIsPostDialogOpen(true)}
            onDelete={handleDelete}
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
      {post && (
        <PostDialog
          open={isPostDialogOpen}
          onOpenChange={setIsPostDialogOpen}
          postToEdit={post}
          onPostUpdated={(updatedPost) => {
            setPost(updatedPost)
            setIsPostDialogOpen(false)
          }}
        />
      )}
    </div>
  )
}

