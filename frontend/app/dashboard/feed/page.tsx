'use client'

import { useState, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { Loader2, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { socialService, Post } from '@/services/social-service'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'

// Lazy load heavy feed components
const PostCard = dynamic(() => import('@/components/feed/post-card').then(mod => ({ default: mod.PostCard })), {
  loading: () => <div className="h-64 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg mb-4" />
})

const PostDialog = dynamic(() => import('@/components/feed/post-dialog').then(mod => ({ default: mod.PostDialog })), {
  ssr: false
})

const CommentDialog = dynamic(() => import('@/components/feed/comment-dialog').then(mod => ({ default: mod.CommentDialog })), {
  ssr: false
})

const CreatePostBox = dynamic(() => import('@/components/feed/create-post-box').then(mod => ({ default: mod.CreatePostBox })), {
  loading: () => <div className="h-32 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg mb-4" />
})

const FloatingActionButton = dynamic(() => import('@/components/ui/floating-action-button').then(mod => ({ default: mod.FloatingActionButton })), {
  ssr: false
})

export default function FeedPage() {
  const { isAuthenticated, user } = useAuth()
  const router = useRouter()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [posts, setPosts] = useState<Post[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isPostDialogOpen, setIsPostDialogOpen] = useState(false)
  const [editingPost, setEditingPost] = useState<Post | null>(null)
  const [commentPostId, setCommentPostId] = useState<number | null>(null)
  const [skip, setSkip] = useState(0)
  const [hasMore, setHasMore] = useState(true)

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }
    loadFeed()
  }, [isAuthenticated, router])

  const loadFeed = async (nextSkip: number = 0) => {
    setIsLoading(true)
    try {
      const data = await socialService.getFeed(nextSkip, 20)
      if (nextSkip === 0) {
        setPosts(data)
      } else {
        setPosts(prev => [...prev, ...data])
      }
      setHasMore(data.length === 20)
    } catch (error: any) {
      console.error('Error loading feed:', error)
      // Don't show alert for feed loading errors, just log
      if (error?.response?.status === 401) {
        router.push('/login')
      }
    } finally {
      setIsLoading(false)
    }
  }

  const loadMore = () => {
    if (!isLoading && hasMore) {
      const nextSkip = skip + 20
      setSkip(nextSkip)
      loadFeed(nextSkip)
    }
  }

  const handlePostCreated = () => {
    setSkip(0)
    setPosts([])
    loadFeed(0)
  }

  const handlePostUpdated = (updatedPost: Post) => {
    setPosts(prev => prev.map((post) => (post.id === updatedPost.id ? updatedPost : post)))
    setEditingPost(null)
    setIsPostDialogOpen(false)
  }

  const handleLike = async (postId: number) => {
    try {
      const post = posts.find(p => p.id === postId)
      if (post?.is_liked) {
        await socialService.unlikePost(postId)
      } else {
        await socialService.likePost(postId)
      }
      const updatedPost = await socialService.getPost(postId)
      setPosts(prev => prev.map(p => p.id === postId ? updatedPost : p))
    } catch (error) {
      console.error('Error liking post:', error)
    }
  }

  const handleReact = async (postId: number, reactionType: string) => {
    try {
      await socialService.reactToPost(postId, reactionType)
      const updatedPost = await socialService.getPost(postId)
      setPosts(prev => prev.map(p => p.id === postId ? updatedPost : p))
    } catch (error) {
      console.error('Error reacting to post:', error)
    }
  }

  const handleRepost = async (postId: number) => {
    try {
      await socialService.sharePost(postId)
      const updatedPost = await socialService.getPost(postId)
      setPosts(prev => prev.map(p => p.id === postId ? updatedPost : p))
    } catch (error) {
      console.error('Error reposting:', error)
      addToast(t('dashboard.feed.repost_failed'), 'error', 6000)
    }
  }

  const handleShareOut = async (post: Post) => {
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    const referralCode = user?.personal_referral_code?.trim()
    const shareUrl = referralCode
      ? `${origin}/s/f/${post.id}?ref=${encodeURIComponent(referralCode)}`
      : `${origin}/s/f/${post.id}`
    const title = post.author?.full_name || post.author?.username || 'MyHigh5'
    const text = (post.content || '').slice(0, 280)

    try {
      if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
        await navigator.share({ title, text, url: shareUrl })
        return
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return }

    try {
      await navigator.clipboard.writeText(shareUrl)
      addToast(t('dashboard.feed.link_copied'), 'success', 4000)
    } catch {
      addToast(t('dashboard.feed.share_failed'), 'error', 6000)
    }
  }

  const handleComment = (postId: number) => {
    setCommentPostId(postId)
  }

  const handleDelete = async (postId: number) => {
    if (confirm(t('dashboard.feed.delete_confirm'))) {
      try {
        await socialService.deletePost(postId)
        setPosts(prev => prev.filter(p => p.id !== postId))
      } catch (error) {
        console.error('Error deleting post:', error)
      }
    }
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-4 md:py-6">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Main Feed - Standalone, centered */}
        <main className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
            {/* Create Post Box */}
            <div className="p-4 md:p-6 border-b border-gray-200 dark:border-gray-700">
              <CreatePostBox
                user={user}
                onPostCreated={handlePostCreated}
                onOpenDialog={() => setIsPostDialogOpen(true)}
              />
            </div>

            {/* Posts Feed */}
            {isLoading && posts.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
              </div>
            ) : posts.length === 0 ? (
              <div className="text-center py-8 md:py-12 px-4">
                <p className="text-gray-500 dark:text-gray-400 mb-3 md:mb-4 text-base md:text-lg">
                  {t('dashboard.feed.welcome')}
                </p>
                <p className="text-gray-400 dark:text-gray-500 mb-4 md:mb-6 text-xs md:text-sm px-2">
                  {t('dashboard.feed.welcome_description')}
                </p>
                <Button 
                  onClick={() => setIsPostDialogOpen(true)}
                  className="rounded-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white font-semibold px-4 md:px-6 text-sm md:text-base"
                >
                  {t('dashboard.feed.create_first_post')}
                </Button>
              </div>
            ) : (
              <div>
                {posts.map((post) => (
                  <PostCard
                    key={post.id}
                    post={post}
                    currentUserId={user?.id}
                    onLike={handleLike}
                    onComment={handleComment}
                    onRepost={handleRepost}
                    onShareOut={handleShareOut}
                    onReact={handleReact}
                    onEdit={(selectedPost) => {
                      setEditingPost(selectedPost)
                      setIsPostDialogOpen(true)
                    }}
                    onDelete={handleDelete}
                  />
                ))}
                {hasMore && (
                  <div className="text-center py-6 px-4 border-t border-gray-100 dark:border-gray-700">
                    <Button
                      variant="ghost"
                      onClick={loadMore}
                      disabled={isLoading}
                      className="rounded-full"
                    >
                      {isLoading ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          {t('dashboard.feed.loading')}
                        </>
                      ) : (
                        t('dashboard.feed.load_more')
                      )}
                    </Button>
                  </div>
                )}
              </div>
            )}
        </main>
      </div>

      {/* Floating Action Button */}
      <FloatingActionButton
        onClick={() => setIsPostDialogOpen(true)}
        label={t('dashboard.feed.create_post')}
        variant="primary"
        position="bottom-right"
      />

      {/* Dialogs */}
      <PostDialog
        open={isPostDialogOpen}
        onOpenChange={(open) => {
          setIsPostDialogOpen(open)
          if (!open) {
            setEditingPost(null)
          }
        }}
        onPostCreated={handlePostCreated}
        postToEdit={editingPost}
        onPostUpdated={handlePostUpdated}
      />
      {commentPostId && (
        <CommentDialog
          open={!!commentPostId}
          onOpenChange={(open) => !open && setCommentPostId(null)}
          postId={commentPostId}
          onCommentAdded={() => {
            socialService.getPost(commentPostId).then(updatedPost => {
              setPosts(prev => prev.map(p => p.id === commentPostId ? updatedPost : p))
            })
          }}
        />
      )}
    </div>
  )
}
