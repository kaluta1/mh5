'use client'

import { Suspense, useEffect } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { contestService } from '@/services/contest-service'
import { publicContestantEntryPath } from '@/lib/public-share-urls'

function ContestantLegacyRedirectContent() {
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const contestantId = params.id as string

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const data = await contestService.getContestant(Number(contestantId))
        if (cancelled) return
        const contestId = data.contest_id || searchParams.get('contestId')
        if (!contestId) {
          router.replace('/')
          return
        }
        const qs = searchParams.toString()
        router.replace(publicContestantEntryPath(contestId, contestantId, qs ? `?${qs}` : ''))
      } catch {
        if (!cancelled) router.replace('/')
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [contestantId, router, searchParams])

  return (
    <div className="min-h-screen flex items-center justify-center bg-black">
      <Loader2 className="h-10 w-10 animate-spin text-white" />
    </div>
  )
}

export default function ContestantLegacyRedirectPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-black">
          <Loader2 className="h-10 w-10 animate-spin text-white" />
        </div>
      }
    >
      <ContestantLegacyRedirectContent />
    </Suspense>
  )
}
