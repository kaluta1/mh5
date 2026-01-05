'use client'

import { useState, useEffect } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PostCard } from '@/components/feed/post-card'
import { PostDialog } from '@/components/feed/post-dialog'
import { CommentDialog } from '@/components/feed/comment-dialog'
import { CreatePostBox } from '@/components/feed/create-post-box'
import { SuggestedUsers } from '@/components/feed/suggested-users'
import { SuggestedGroups } from '@/components/feed/suggested-groups'
import { Advertisement } from '@/components/feed/advertisement'
import { FloatingActionButton } from '@/components/ui/floating-action-button'
import { socialService, Post } from '@/services/social-service'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'

export default function FeedPage() {
  const { isAuthenticated, user } = useAuth()
  const router = useRouter()
  const [posts, setPosts] = useState<Post[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isPostDialogOpen, setIsPostDialogOpen] = useState(false)
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

  const loadFeed = async () => {
    setIsLoading(true)
    try {
      const data = await socialService.getFeed(skip, 20)
      if (skip === 0) {
        setPosts(data)
      } else {
        setPosts(prev => [...prev, ...data])
      }
      setHasMore(data.length === 20)
    } catch (error) {
      console.error('Error loading feed:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const loadMore = () => {
    if (!isLoading && hasMore) {
      setSkip(prev => prev + 20)
      loadFeed()
    }
  }

  const handlePostCreated = () => {
    setSkip(0)
    setPosts([])
    loadFeed()
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

  const handleShare = async (postId: number) => {
    try {
      await socialService.sharePost(postId)
      const updatedPost = await socialService.getPost(postId)
      setPosts(prev => prev.map(p => p.id === postId ? updatedPost : p))
    } catch (error) {
      console.error('Error sharing post:', error)
    }
  }

  const handleComment = (postId: number) => {
    setCommentPostId(postId)
  }

  const handleDelete = async (postId: number) => {
    if (confirm('Êtes-vous sûr de vouloir supprimer ce post ?')) {
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
    <div className="space-y-6 pt-6 pb-24">
      {/* Main Content - 3 columns layout */}
      <div className="grid grid-cols-12 gap-6">
        {/* Left Sidebar - Suggested Users & Ads */}
        <aside className="hidden lg:block lg:col-span-3 space-y-6">
          <SuggestedUsers currentUserId={user?.id} />
          <Advertisement />
        </aside>

        {/* Main Feed */}
        <main className="col-span-12 lg:col-span-6 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm overflow-hidden">
            {/* Create Post Box */}
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
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
              <div className="text-center py-12 px-4">
                <p className="text-gray-500 dark:text-gray-400 mb-4 text-lg">
                  Bienvenue sur votre feed !
                </p>
                <p className="text-gray-400 dark:text-gray-500 mb-6 text-sm">
                  Commencez à suivre des personnes pour voir leurs posts ici.
                </p>
                <Button 
                  onClick={() => setIsPostDialogOpen(true)}
                  className="rounded-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white font-semibold px-6"
                >
                  Créer votre premier post
                </Button>
              </div>
            ) : (
              <div>
                {posts.map((post) => (
                  <PostCard
                    key={post.id}
                    post={post}
                    onLike={handleLike}
                    onComment={handleComment}
                    onShare={handleShare}
                    onReact={handleReact}
                    onDelete={handleDelete}
                  />
                ))}
                {hasMore && (
                  <div className="text-center py-8">
                    <Button
                      variant="ghost"
                      onClick={loadMore}
                      disabled={isLoading}
                      className="rounded-full"
                    >
                      {isLoading ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Chargement...
                        </>
                      ) : (
                        'Charger plus'
                      )}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </main>

        {/* Right Sidebar - Suggested Groups */}
        <aside className="hidden lg:block lg:col-span-3">
          <SuggestedGroups currentUserId={user?.id} />
        </aside>
      </div>

      {/* Floating Action Button */}
      <FloatingActionButton
        onClick={() => setIsPostDialogOpen(true)}
        label="Créer un post"
        variant="primary"
        position="bottom-right"
      />

      {/* Dialogs */}
      <PostDialog
        open={isPostDialogOpen}
        onOpenChange={setIsPostDialogOpen}
        onPostCreated={handlePostCreated}
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
