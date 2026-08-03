'use client'

import { Suspense, useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { PostCard } from '@/components/feed/post-card'
import { PublicShareShell } from '@/components/public/public-share-shell'
import { socialService, Post } from '@/services/social-service'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'

function PublicFeedPostPageContent() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t } = useLanguage()
  const { isAuthenticated, isLoading: authLoading, user } = useAuth()
  const postId = parseInt(params.id as string, 10)
  const refCode = searchParams.get('ref')

  const [post, setPost] = useState<Post | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (refCode) {
      localStorage.setItem('referral_code', refCode)
    }
  }, [refCode])

  useEffect(() => {
    if (!authLoading && isAuthenticated && postId) {
      router.replace(`/dashboard/feed/${postId}${refCode ? `?ref=${encodeURIComponent(refCode)}` : ''}`)
    }
  }, [authLoading, isAuthenticated, postId, refCode, router])

  useEffect(() => {
    if (!postId || Number.isNaN(postId)) {
      setNotFound(true)
      setLoading(false)
      return
    }

    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await socialService.getPost(postId)
        if (!cancelled) {
          setPost(data)
          setNotFound(false)
        }
      } catch {
        if (!cancelled) {
          setPost(null)
          setNotFound(true)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [postId])

  if (authLoading || (isAuthenticated && !user)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
      </div>
    )
  }

  if (isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
      </div>
    )
  }

  return (
    <PublicShareShell refCode={refCode}>
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
        </div>
      ) : notFound || !post ? (
        <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 text-center">
          <p className="text-gray-600 dark:text-gray-300">
            {t('public_share.post_not_found') || 'This post is unavailable or private.'}
          </p>
        </div>
      ) : (
        <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden shadow-sm">
          <PostCard post={post} showFullContent readOnly />
        </div>
      )}
    </PublicShareShell>
  )
}

export default function PublicFeedPostPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
          <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
        </div>
      }
    >
      <PublicFeedPostPageContent />
    </Suspense>
  )
}
