'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { VoteHistorySkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Heart, ThumbsUp, Smile, ThumbsDown, ArrowLeft, Calendar, User } from 'lucide-react'
import api from '@/lib/api'

interface VoteHistoryItem {
  id: number
  contestant_id: number
  contestant_name: string
  contestant_avatar?: string
  reaction_type: 'like' | 'love' | 'wow' | 'dislike' | 'vote'
  vote_date: string
  contest_name?: string
}

export default function VoteHistoryPage() {
  const router = useRouter()
  const { t } = useLanguage()
  const { isAuthenticated, isLoading } = useAuth()
  
  const [voteHistory, setVoteHistory] = useState<VoteHistoryItem[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    const loadVoteHistory = async () => {
      try {
        setPageLoading(true)
        // TODO: Récupérer l'historique des votes depuis l'API
        // const response = await api.get('/api/v1/votes/my-history')
        // setVoteHistory(response.data)
        
        // Mock data for now
        setVoteHistory([
          {
            id: 1,
            contestant_id: 2,
            contestant_name: 'Jean Dupont',
            reaction_type: 'vote',
            vote_date: new Date().toISOString(),
            contest_name: 'Talent Show 2025'
          },
          {
            id: 2,
            contestant_id: 3,
            contestant_name: 'Marie Martin',
            reaction_type: 'love',
            vote_date: new Date(Date.now() - 86400000).toISOString(),
            contest_name: 'Singing Competition'
          },
          {
            id: 3,
            contestant_id: 4,
            contestant_name: 'Pierre Bernard',
            reaction_type: 'wow',
            vote_date: new Date(Date.now() - 172800000).toISOString(),
            contest_name: 'Dance Battle'
          }
        ])
      } catch (err) {
        setError('Erreur lors du chargement de l\'historique')
        console.error(err)
      } finally {
        setPageLoading(false)
      }
    }

    if (isAuthenticated) {
      loadVoteHistory()
    }
  }, [isAuthenticated])

  const getReactionIcon = (type: string) => {
    switch (type) {
      case 'like':
        return <ThumbsUp className="w-5 h-5 text-blue-500" />
      case 'love':
        return <Heart className="w-5 h-5 text-red-500" />
      case 'wow':
        return <Smile className="w-5 h-5 text-yellow-500" />
      case 'dislike':
        return <ThumbsDown className="w-5 h-5 text-gray-500" />
      case 'vote':
        return <Heart className="w-5 h-5 text-myhigh5-primary" />
      default:
        return null
    }
  }

  const getReactionLabel = (type: string) => {
    switch (type) {
      case 'like':
        return t('contestant_detail.like')
      case 'love':
        return t('contestant_detail.love')
      case 'wow':
        return t('contestant_detail.wow')
      case 'dislike':
        return t('contestant_detail.dislike')
      case 'vote':
        return t('contestant_detail.vote')
      default:
        return type
    }
  }

  if (isLoading || pageLoading) {
    return <VoteHistorySkeleton />
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="container mx-auto px-4 md:px-6 lg:px-8 py-6">
          <div className="flex items-center gap-4 mb-4">
            <Button
              onClick={() => router.back()}
              variant="outline"
              className="border-gray-200 dark:border-gray-700"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t('common.back')}
            </Button>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white">
            {t('contestant_detail.vote_history')}
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-2">
            Consultez tous vos votes et réactions
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 md:px-6 lg:px-8 py-8">
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
            <p className="text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {voteHistory.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-2xl p-12 text-center shadow-md">
            <Heart className="w-16 h-16 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              {t('contestant_detail.no_votes')}
            </h2>
            <p className="text-gray-600 dark:text-gray-400">
              Commencez à voter pour voir votre historique ici
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {voteHistory.map((item) => (
              <div
                key={item.id}
                className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md hover:shadow-lg transition-shadow"
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white line-clamp-1">
                      {item.contestant_name}
                    </h3>
                    {item.contest_name && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-1">
                        {item.contest_name}
                      </p>
                    )}
                  </div>
                  <div className="flex-shrink-0">
                    {getReactionIcon(item.reaction_type)}
                  </div>
                </div>

                {/* Reaction Type */}
                <div className="mb-4">
                  <span className="inline-block px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full text-sm font-medium text-gray-700 dark:text-gray-300">
                    {getReactionLabel(item.reaction_type)}
                  </span>
                </div>

                {/* Date */}
                <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <Calendar className="w-4 h-4" />
                  <span>
                    {new Date(item.vote_date).toLocaleDateString('fr-FR', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </span>
                </div>

                {/* Action Button */}
                <Button
                  onClick={() => router.push(`/dashboard/contests/1/contestant/${item.contestant_id}`)}
                  className="w-full mt-4 bg-gradient-to-r from-myhigh5-primary to-myhigh5-primary-dark text-white hover:shadow-lg"
                >
                  Voir le profil
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
