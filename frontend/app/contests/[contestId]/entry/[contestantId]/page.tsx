'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { VideoPreviewDialog } from '@/components/ui/video-preview-dialog'
import { contestService, ContestantWithAuthorAndStats } from '@/services/contest-service'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { cleanVideoUrl } from '@/lib/utils/video-platforms'
import { getEffectiveApiUrl } from '@/lib/config'

function unwrapMediaEntries(raw: unknown): string[] {
  if (raw == null) return []
  if (typeof raw === 'string') {
    const trimmed = raw.trim()
    if (!trimmed) return []
    if (trimmed.startsWith('[') || trimmed.startsWith('{') || trimmed.startsWith('"')) {
      try {
        return unwrapMediaEntries(JSON.parse(trimmed))
      } catch {
        return [trimmed]
      }
    }
    return [trimmed]
  }
  if (Array.isArray(raw)) {
    return raw.flatMap((item) => unwrapMediaEntries(item))
  }
  return []
}

function parseMediaUrls(mediaIds: string | undefined): string[] {
  if (!mediaIds) return []
  try {
    const entries = unwrapMediaEntries(JSON.parse(mediaIds))
    const apiBase = typeof window !== 'undefined' ? getEffectiveApiUrl() : ''
    return entries
      .filter((url) => url && url.trim() !== '')
      .map((url) => {
        let fullUrl = cleanVideoUrl(url) || url
        if (fullUrl && !fullUrl.startsWith('http') && !fullUrl.startsWith('data:')) {
          fullUrl = fullUrl.startsWith('/') ? `${apiBase}${fullUrl}` : `${apiBase}/${fullUrl}`
        }
        return fullUrl
      })
  } catch {
    return unwrapMediaEntries(mediaIds)
      .filter((url) => url && url.trim() !== '')
      .map((url) => cleanVideoUrl(url) || url)
  }
}

function PublicContestantEntryContent() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()

  const contestId = params.contestId as string
  const contestantId = params.contestantId as string
  const refCode = searchParams.get('ref')
  const roundId = searchParams.get('roundId')

  const [contestant, setContestant] = useState<ContestantWithAuthorAndStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [isVoting, setIsVoting] = useState(false)
  const [hasVoted, setHasVoted] = useState(false)
  const [votesCount, setVotesCount] = useState(0)

  useEffect(() => {
    if (refCode) localStorage.setItem('referral_code', refCode)
  }, [refCode])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await contestService.getContestant(Number(contestantId))
        if (cancelled) return
        setContestant(data)
        setHasVoted(Boolean(data.has_voted))
        setVotesCount(data.votes_count ?? 0)
      } catch {
        if (!cancelled) setContestant(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [contestantId])

  const videoUrl = useMemo(() => {
    if (!contestant) return ''
    const videos = parseMediaUrls(contestant.video_media_ids)
    const fromVideos = videos.find((url) =>
      /youtube|youtu\.be|vimeo|tiktok|instagram|facebook|\.mp4|\/media\//i.test(url)
    )
    if (fromVideos) return fromVideos
    const fromField = contestant.contestant_image_url?.trim()
    if (fromField) return fromField
    return videos[0] || ''
  }, [contestant])

  const handleVote = useCallback(async () => {
    if (!contestant || isVoting || hasVoted) return
    setIsVoting(true)
    try {
      const cid = Number(contestId)
      const rid = roundId ? Number(roundId) : undefined
      const result = await contestService.voteForContestant(Number(contestantId), {
        contestId: Number.isFinite(cid) ? cid : undefined,
        roundId: rid && Number.isFinite(rid) ? rid : undefined,
      })
      if (result.success) {
        setHasVoted(true)
        setVotesCount((v) => v + 1)
        addToast(t('dashboard.contests.vote_success') || 'Vote recorded!', 'success')
      } else if (result.code === 'already_voted') {
        setHasVoted(true)
        addToast(t('dashboard.contests.already_voted_error') || 'Already voted.', 'info')
      }
    } catch {
      addToast(t('dashboard.contests.vote_error') || 'Unable to vote.', 'error')
    } finally {
      setIsVoting(false)
    }
  }, [contestant, contestId, contestantId, roundId, isVoting, hasVoted, addToast, t])

  const handleLoginRequired = useCallback(() => {
    const returnUrl = typeof window !== 'undefined' ? window.location.href : '/'
    router.push(`/login?returnUrl=${encodeURIComponent(returnUrl)}`)
  }, [router])

  if (loading || authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <Loader2 className="h-10 w-10 animate-spin text-white" />
      </div>
    )
  }

  if (!contestant || !videoUrl) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black text-white px-6 text-center">
        <p>{t('public_share.contestant_not_found') || 'This entry is unavailable.'}</p>
      </div>
    )
  }

  const isAuthor = Boolean(user?.id && contestant.user_id === user.id)
  const canVote = isAuthenticated ? Boolean(contestant.can_vote) && !isAuthor : false
  const voteRestrictionReason = !isAuthenticated
    ? 'not_authenticated'
    : isAuthor
      ? 'own_contestant'
      : contestant.can_vote
        ? undefined
        : contestant.has_voted
          ? 'already_voted'
          : 'voting_not_open'

  return (
    <VideoPreviewDialog
      variant="page"
      isOpen
      videoUrl={videoUrl}
      videoTitle={contestant.title || contestant.author_name || ''}
      onClose={() => router.push('/')}
      canVote={canVote}
      hasVoted={hasVoted}
      isVoting={isVoting}
      isAuthor={isAuthor}
      votesCount={votesCount}
      onVote={isAuthenticated ? handleVote : undefined}
      onLoginRequired={handleLoginRequired}
      voteRestrictionReason={voteRestrictionReason}
      authorName={contestant.author_name}
      authorAvatar={contestant.author_avatar_url}
      rank={contestant.rank}
      contestantId={contestantId}
      commentsCount={contestant.comments_count || 0}
    />
  )
}

export default function PublicContestantEntryPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-black">
          <Loader2 className="h-10 w-10 animate-spin text-white" />
        </div>
      }
    >
      <PublicContestantEntryContent />
    </Suspense>
  )
}
