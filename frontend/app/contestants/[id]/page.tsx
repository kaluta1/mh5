'use client'

import { Suspense, useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { Loader2, MapPin, Heart } from 'lucide-react'
import { PublicShareShell } from '@/components/public/public-share-shell'
import { contestService, ContestantWithAuthorAndStats } from '@/services/contest-service'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { htmlToPlainText } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'

function PublicContestantPageContent() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t } = useLanguage()
  const { isAuthenticated, isLoading: authLoading, user } = useAuth()
  const contestantId = params.id as string
  const refCode = searchParams.get('ref')

  const [contestant, setContestant] = useState<ContestantWithAuthorAndStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (refCode) {
      localStorage.setItem('referral_code', refCode)
    }
  }, [refCode])

  useEffect(() => {
    if (!authLoading && isAuthenticated && contestant?.contest_id && contestantId) {
      router.replace(
        `/dashboard/contests/${contestant.contest_id}/contestant/${contestantId}${
          refCode ? `?ref=${encodeURIComponent(refCode)}` : ''
        }`
      )
    }
  }, [authLoading, isAuthenticated, contestant, contestantId, refCode, router])

  useEffect(() => {
    if (!contestantId) return

    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await contestService.getContestant(Number(contestantId))
        if (!cancelled) {
          setContestant(data)
          setNotFound(false)
        }
      } catch {
        if (!cancelled) {
          setContestant(null)
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
  }, [contestantId])

  if (authLoading || (isAuthenticated && user)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
      </div>
    )
  }

  const formattedDate = contestant?.registration_date
    ? new Date(contestant.registration_date).toLocaleDateString()
    : null

  const coverImage =
    contestant?.contestant_image_url ||
    contestant?.contest_image_url ||
    contestant?.author_avatar_url ||
    undefined

  return (
    <PublicShareShell
      refCode={refCode}
      ctaLabel={t('public_share.vote_cta') || 'Join to vote and support'}
    >
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
        </div>
      ) : notFound || !contestant ? (
        <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 text-center">
          <p className="text-gray-600 dark:text-gray-300">
            {t('public_share.contestant_not_found') || 'This entry is unavailable.'}
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="relative h-56 md:h-72 rounded-2xl overflow-hidden bg-gradient-to-br from-myhigh5-primary to-indigo-700">
            {coverImage ? (
              <img src={coverImage} alt="" className="absolute inset-0 h-full w-full object-cover" />
            ) : null}
            <div className="absolute inset-0 bg-black/40" />
            <div className="absolute bottom-0 left-0 right-0 p-5 md:p-6 text-white">
              <div className="flex items-end gap-4">
                {contestant.author_avatar_url ? (
                  <img
                    src={contestant.author_avatar_url}
                    alt={contestant.author_name || 'Contestant'}
                    className="h-20 w-20 rounded-full border-4 border-white object-cover"
                  />
                ) : (
                  <div className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-white bg-white/20 text-2xl font-bold">
                    {contestant.author_name?.charAt(0).toUpperCase() || '?'}
                  </div>
                )}
                <div>
                  <h1 className="text-2xl md:text-3xl font-bold">
                    {contestant.author_name || contestant.title || 'Contestant'}
                  </h1>
                  <div className="mt-1 flex flex-wrap items-center gap-3 text-white/90 text-sm">
                    {contestant.author_city ? (
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="h-4 w-4" />
                        {contestant.author_city}
                      </span>
                    ) : null}
                    {contestant.author_country ? <span>{contestant.author_country}</span> : null}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                  {contestant.title || t('contestant_detail.entry_fallback_title') || 'Contest entry'}
                </h2>
                {formattedDate ? (
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    {t('contestant_detail.registered_on') || 'Registered on'}: {formattedDate}
                  </p>
                ) : null}
              </div>
              {typeof contestant.rank === 'number' ? (
                <Badge variant="secondary">#{contestant.rank}</Badge>
              ) : null}
            </div>

            {contestant.description ? (
              <div>
                <h3 className="mb-2 font-semibold text-gray-900 dark:text-white">
                  {t('contestant_detail.description_section') || 'Description'}
                </h3>
                <p className="whitespace-pre-wrap break-words text-gray-700 dark:text-gray-300 leading-relaxed">
                  {htmlToPlainText(contestant.description)}
                </p>
              </div>
            ) : null}

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div className="rounded-xl bg-myhigh5-primary/10 p-4">
                <div className="text-2xl font-bold text-myhigh5-primary">
                  {contestant.votes_count ?? 0}
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  {t('contestant_detail.votes') || 'Votes'}
                </div>
              </div>
              <div className="rounded-xl bg-pink-50 dark:bg-pink-900/20 p-4">
                <div className="flex items-center gap-2 text-2xl font-bold text-pink-600 dark:text-pink-300">
                  <Heart className="h-5 w-5" />
                  {contestant.favorites_count ?? 0}
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  {t('contestant_detail.favorites') || 'Favorites'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </PublicShareShell>
  )
}

export default function PublicContestantPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
          <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
        </div>
      }
    >
      <PublicContestantPageContent />
    </Suspense>
  )
}
