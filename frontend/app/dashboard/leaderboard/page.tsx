'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { Award, Trophy, Medal, User, MapPin, Calendar, Coins } from 'lucide-react'
import { cacheService } from '@/lib/cache-service'

interface TopSponsor {
  id: number
  username: string
  email: string
  first_name?: string
  last_name?: string
  full_name?: string
  avatar_url?: string
  country?: string
  city?: string
  created_at?: string
  referrals_count: number
}

// Bénéfices par position
const BENEFITS = {
  1: 100,
  2: 80,
  3: 70,
  4: 60,
  5: 50,
  6: 40,
  7: 30,
  8: 20,
  9: 10,
  10: 5
}

type LeaderboardType = 'regular' | 'mfm'

export default function LeaderboardPage() {
  const { t, language } = useLanguage()
  const { isAuthenticated, isLoading } = useAuth()
  const [topSponsors, setTopSponsors] = useState<TopSponsor[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [leaderboardType, setLeaderboardType] = useState<LeaderboardType>('regular')
  
  // Mapping des langues vers les locales
  const localeMap: Record<string, string> = {
    fr: 'fr-FR',
    en: 'en-US',
    es: 'es-ES',
    de: 'de-DE'
  }

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      loadLeaderboard()
    }
  }, [isLoading, isAuthenticated, leaderboardType])

  const loadLeaderboard = async () => {
    try {
      const token = localStorage.getItem('access_token')
      if (!token) return

      setPageLoading(true)
      const endpoint = leaderboardType === 'mfm' 
        ? '/api/v1/affiliates/leaderboard/mfm'
        : '/api/v1/affiliates/leaderboard'
      
      const params = { limit: 10 }
      const cacheKey = endpoint

      // Vérifier le cache
      const cached = cacheService.get<TopSponsor[]>(cacheKey, params)
      if (cached) {
        setTopSponsors(cached)
        setPageLoading(false)
        return
      }

      // Si pas en cache, faire la requête
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}${endpoint}?limit=10`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (response.ok) {
        const data = await response.json()
        setTopSponsors(data)
        // Mettre en cache
        cacheService.set(cacheKey, data, params)
      }
    } catch (error) {
      console.error('Error loading leaderboard:', error)
    } finally {
      setPageLoading(false)
    }
  }

  const getRankIcon = (rank: number) => {
    if (rank === 1) return <Trophy className="w-6 h-6 text-yellow-500 dark:text-yellow-500" />
    if (rank === 2) return <Medal className="w-6 h-6 text-gray-500 dark:text-gray-400" />
    if (rank === 3) return <Medal className="w-6 h-6 text-amber-600 dark:text-amber-500" />
    return <span className="w-6 h-6 flex items-center justify-center text-gray-600 dark:text-gray-400 font-bold">{rank}</span>
  }

  const getRankBadgeColor = (rank: number) => {
    if (rank === 1) return 'bg-yellow-500 text-white'
    if (rank === 2) return 'bg-gray-400 dark:bg-gray-500 text-white'
    if (rank === 3) return 'bg-amber-600 dark:bg-amber-500 text-white'
    return 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
  }

  const formatName = (sponsor: TopSponsor) => {
    if (sponsor.full_name) return sponsor.full_name
    if (sponsor.first_name || sponsor.last_name) {
      return `${sponsor.first_name || ''} ${sponsor.last_name || ''}`.trim()
    }
    return sponsor.username || sponsor.email?.split('@')[0] || 'N/A'
  }

  if (isLoading || pageLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="animate-pulse space-y-4">
            {[...Array(10)].map((_, i) => (
              <div key={i} className="h-20 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-yellow-500 to-amber-600 flex items-center justify-center shadow-lg">
              <Award className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                {t('dashboard.leaderboard.title') || 'Classement des Sponsors'}
              </h1>
              <p className="text-gray-600 dark:text-gray-400 mt-1">
                {leaderboardType === 'mfm'
                  ? (t('dashboard.leaderboard.mfm_subtitle') || 'Les 10 meilleurs sponsors MFM avec le plus de référents directs ayant acheté MFM')
                  : (t('dashboard.leaderboard.subtitle') || 'Les 10 meilleurs sponsors avec le plus de référents directs')
                }
              </p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6 border-b border-gray-200 dark:border-gray-800">
          <div className="flex space-x-1">
            <button
              onClick={() => setLeaderboardType('regular')}
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${
                leaderboardType === 'regular'
                  ? 'border-blue-500 text-blue-500 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
            >
              {t('dashboard.leaderboard.regular_tab') || 'Classement Général'}
            </button>
            <button
              onClick={() => setLeaderboardType('mfm')}
              className={`px-6 py-3 text-base font-semibold transition-colors border-b-2 ${
                leaderboardType === 'mfm'
                  ? 'border-blue-500 text-blue-500 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
            >
              {t('dashboard.leaderboard.mfm_tab') || 'Classement MFM'}
            </button>
          </div>
        </div>

        {/* Leaderboard */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
          {topSponsors.length === 0 ? (
            <div className="p-12 text-center">
              <Award className="w-16 h-16 text-gray-400 dark:text-gray-600 mx-auto mb-4" />
              <p className="text-gray-600 dark:text-gray-400 text-lg">
                {t('dashboard.leaderboard.no_data') || 'Aucun sponsor trouvé'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {topSponsors.map((sponsor, index) => {
                const rank = index + 1
                const isTopThree = rank <= 3
                
                return (
                  <div
                    key={sponsor.id}
                    className={`p-6 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${
                      isTopThree ? 'bg-gray-50/50 dark:bg-gray-700/30' : ''
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      {/* Rank */}
                      <div className={`w-12 h-12 rounded-lg ${getRankBadgeColor(rank)} flex items-center justify-center flex-shrink-0`}>
                        {getRankIcon(rank)}
                      </div>

                      {/* Avatar */}
                      <div className="flex-shrink-0">
                        {sponsor.avatar_url ? (
                          <img
                            src={sponsor.avatar_url}
                            alt={formatName(sponsor)}
                            className="w-14 h-14 rounded-full object-cover border-2 border-gray-300 dark:border-gray-600"
                          />
                        ) : (
                          <div className="w-14 h-14 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center border-2 border-gray-300 dark:border-gray-600">
                            <User className="w-7 h-7 text-gray-500 dark:text-gray-400" />
                          </div>
                        )}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-white truncate">
                            {formatName(sponsor)}
                          </h3>
                          {rank === 1 && (
                            <span className="px-2 py-0.5 bg-yellow-500/20 dark:bg-yellow-500/30 text-yellow-700 dark:text-yellow-400 text-xs font-medium rounded-full">
                              {t('dashboard.leaderboard.champion') || 'Champion'}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                          {sponsor.city && sponsor.country && (
                            <div className="flex items-center gap-1">
                              <MapPin className="w-4 h-4" />
                              <span>{sponsor.city}, {sponsor.country}</span>
                            </div>
                          )}
                          {sponsor.created_at && (
                            <div className="flex items-center gap-1">
                              <Calendar className="w-4 h-4" />
                              <span>
                                {new Date(sponsor.created_at).toLocaleDateString(
                                  localeMap[language] || 'en-US',
                                  { year: 'numeric', month: 'short' }
                                )}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Stats */}
                      <div className="flex items-center gap-6 flex-shrink-0">
                        <div className="text-right">
                          <div className="text-2xl font-bold text-gray-900 dark:text-white">
                            {sponsor.referrals_count}
                          </div>
                          <div className="text-xs text-gray-600 dark:text-gray-400">
                            {t('dashboard.leaderboard.referrals') || 'Référents'}
                          </div>
                        </div>
                        {/* Benefits */}
                        {BENEFITS[rank as keyof typeof BENEFITS] && (
                          <div className="text-right">
                            <div className="flex items-center gap-1 justify-end">
                              <Coins className="w-5 h-5 text-green-600 dark:text-green-400" />
                              <div className="text-xl font-bold text-green-600 dark:text-green-400">
                                {BENEFITS[rank as keyof typeof BENEFITS]}
                              </div>
                              <span className="text-sm text-green-700 dark:text-green-300 font-medium">DSP</span>
                            </div>
                            <div className="text-xs text-gray-600 dark:text-gray-400">
                              {t('dashboard.leaderboard.benefit') || 'Bénéfice'}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Info Box */}
        <div className="mt-8 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700/50 rounded-xl p-6">
          <div className="flex items-start gap-3">
            <Award className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
            <div>
              <h3 className="font-semibold text-blue-900 dark:text-blue-300 mb-1">
                {t('dashboard.leaderboard.info_title') || 'Comment fonctionne le classement ?'}
              </h3>
              <p className="text-sm text-blue-800 dark:text-blue-200/80">
                {t('dashboard.leaderboard.info_description') || 'Le classement est basé sur le nombre de référents directs (niveau 1) de chaque sponsor. Plus vous avez de référents directs, plus votre position dans le classement est élevée.'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

