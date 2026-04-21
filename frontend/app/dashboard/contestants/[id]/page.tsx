'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { ContestantDetailSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ArrowLeft, MapPin, Heart } from 'lucide-react'
import api from '@/lib/api'
import { htmlToPlainText } from '@/lib/utils'

interface ContestantDetail {
  id: number
  season_id: number
  user_id: number
  title?: string | null
  description?: string | null
  image_media_ids?: string | null
  video_media_ids?: string | null
  registration_date?: string
  is_qualified?: boolean
  
  // Infos auteur
  author_name?: string
  author_country?: string
  author_city?: string
  author_avatar_url?: string
  
  // Stats
  rank?: number
  votes_count?: number
  images_count?: number
  videos_count?: number
  
  // État du vote
  has_voted?: boolean
  can_vote?: boolean
}

export default function ContestantDetailPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const contestantId = params.id as string

  const [contestant, setContestant] = useState<ContestantDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    const fetchContestant = async () => {
      try {
        setLoading(true)
        setError(null)
        const response = await api.get(`/api/v1/contestants/${contestantId}`)
        setContestant(response.data)
      } catch (err) {
        console.error('Error loading contestant details:', err)
        setError('error_loading_contestant')
      } finally {
        setLoading(false)
      }
    }

    if (!isLoading && isAuthenticated && contestantId) {
      fetchContestant()
    }
  }, [isLoading, isAuthenticated, contestantId])

  // Count view only after user stays on page for 30 seconds.
  useEffect(() => {
    if (!contestantId || loading || !isAuthenticated) return
    let cancelled = false
    const timer = setTimeout(() => {
      if (cancelled) return
      void api
        .post(`/api/v1/contestants/${contestantId}/view`, { watched_seconds: 30 })
        .catch(() => {
          // Analytics tracking should not affect UX.
        })
    }, 30000)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [contestantId, loading, isAuthenticated])

  if (isLoading || loading) {
    return <ContestantDetailSkeleton />
  }

  if (!isAuthenticated || !user || !contestant) {
    return null
  }

  const formattedDate = contestant.registration_date
    ? new Date(contestant.registration_date).toLocaleDateString()
    : null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Button
          onClick={() => router.back()}
          variant="outline"
          className="text-myfav-primary border-myfav-primary hover:bg-myfav-blue-50"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          {t('common.back')}
        </Button>
      </div>

      {/* Author Card */}
      <div className="bg-gradient-to-r from-myfav-primary to-myfav-primary-dark rounded-2xl p-6 text-white">
        <div className="flex items-center gap-6">
          {/* Avatar */}
          <div className="flex-shrink-0">
            {contestant.author_avatar_url ? (
              <img
                src={contestant.author_avatar_url}
                alt={contestant.author_name}
                className="w-24 h-24 rounded-full object-cover border-4 border-white/20"
              />
            ) : (
              <div className="w-24 h-24 rounded-full bg-white/20 flex items-center justify-center text-4xl font-bold">
                {contestant.author_name?.charAt(0).toUpperCase() || '?'}
              </div>
            )}
          </div>

          {/* Author Info */}
          <div className="flex-1">
            <h1 className="text-3xl font-bold mb-2">
              {contestant.author_name || 'Contestant'}
            </h1>
            <div className="flex items-center gap-4 text-white/90">
              {contestant.author_city && (
                <div className="flex items-center gap-1">
                  <MapPin className="w-4 h-4" />
                  <span>{contestant.author_city}</span>
                </div>
              )}
              {contestant.author_country && (
                <span className="text-white/80">{contestant.author_country}</span>
              )}
            </div>
          </div>

          {/* Rank Badge */}
          {contestant.rank && (
            <div className="text-center">
              <div className="text-4xl font-bold mb-1">#{contestant.rank}</div>
              <p className="text-sm text-white/80">{t('contestant_detail.contest_rank_label')}</p>
            </div>
          )}
        </div>
      </div>

      {/* Main Content Card */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700 space-y-6">
        {/* Title and Status */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
              {contestant.title || t('contestant_detail.entry_fallback_title')}
            </h2>
            {formattedDate && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('contestant_detail.registered_on')}: {formattedDate}
              </p>
            )}
          </div>

          {contestant.is_qualified !== undefined && (
            <Badge
              className={`border-0 ${
                contestant.is_qualified
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                  : 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300'
              }`}
            >
              {contestant.is_qualified ? t('contestant_detail.qualified') : t('contestant_detail.pending')}
            </Badge>
          )}
        </div>

        {/* Description */}
        {contestant.description && (
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">
              {t('contestant_detail.description_section')}
            </h3>
            <p className="text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
              {htmlToPlainText(contestant.description)}
            </p>
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg p-4">
            <div className="text-2xl font-bold text-myfav-primary mb-1">
              {contestant.votes_count || 0}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Votes</p>
          </div>
          <div className="bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg p-4">
            <div className="text-2xl font-bold text-myfav-primary mb-1">
              {contestant.images_count || 0}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Images</p>
          </div>
          <div className="bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg p-4">
            <div className="text-2xl font-bold text-myfav-primary mb-1">
              {contestant.videos_count || 0}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">{t('contestant_detail.videos')}</p>
          </div>
          <div className="bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg p-4">
            <div className="text-2xl font-bold text-myfav-primary mb-1">
              {contestant.rank || '-'}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">{t('contestant_detail.rank')}</p>
          </div>
        </div>

        {/* Additional Info */}
        <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <p className="font-semibold text-gray-900 dark:text-white mb-1">{t('contestant_detail.candidacy_id')}</p>
              <p className="text-gray-600 dark:text-gray-400">{contestant.id}</p>
            </div>
            <div>
              <p className="font-semibold text-gray-900 dark:text-white mb-1">{t('contestant_detail.season_label')}</p>
              <p className="text-gray-600 dark:text-gray-400">{contestant.season_id}</p>
            </div>
          </div>
        </div>

        {error && (
          <p className="text-sm text-red-500 mt-2">
            {t('errors.generic') || 'Une erreur est survenue.'}
          </p>
        )}
      </div>
    </div>
  )
}
