'use client'

import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { UserPlus, MessageCircle } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

interface Contestant {
  id: string
  userId?: number
  name: string
  country?: string
  city?: string
  avatar: string
  rank?: number
}

interface ContestantsSidebarProps {
  contestants: Contestant[]
  contestId: string
  onShowToast: (message: string, type: 'success' | 'error') => void
}

export function ContestantsSidebar({
  contestants,
  contestId,
  onShowToast
}: ContestantsSidebarProps) {
  const { t, language } = useLanguage()
  const router = useRouter()

  const topContestants = contestants.slice(0, 5)

  if (topContestants.length === 0) {
    return null
  }

  return (
    <div className="hidden lg:block lg:col-span-1">
      <div className="sticky top-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">
            {t('dashboard.contests.contestants') || 'Participants'}
          </h3>
          {contestants.length > 5 && (
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              onClick={() => router.push(`/dashboard/contests/${contestId}/contestants`)}
            >
              {language === 'fr' ? 'Voir tout' : language === 'es' ? 'Ver todo' : language === 'de' ? 'Alle anzeigen' : 'View all'}
            </Button>
          )}
        </div>
        
        <div className="space-y-3">
          {topContestants.map((contestant) => (
            <div
              key={contestant.id}
              className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <img
                src={contestant.avatar || '/default-avatar.png'}
                alt={contestant.name}
                className="w-12 h-12 rounded-full object-cover"
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                  {contestant.name}
                </p>
                {contestant.country && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                    {contestant.country}{contestant.city ? `, ${contestant.city}` : ''}
                  </p>
                )}
                {contestant.rank && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {language === 'fr' ? 'Rang' : language === 'es' ? 'Rango' : language === 'de' ? 'Rang' : 'Rank'}: {contestant.rank}
                  </p>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs px-2 py-1 h-auto"
                  onClick={() => {
                    // TODO: Implement follow functionality
                    onShowToast(t('common.follow') || 'Follow functionality coming soon', 'success')
                  }}
                >
                  <UserPlus className="w-3 h-3 mr-1" />
                  {language === 'fr' ? 'Suivre' : language === 'es' ? 'Seguir' : language === 'de' ? 'Folgen' : 'Follow'}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs px-2 py-1 h-auto"
                  onClick={() => {
                    // TODO: Implement message functionality
                    router.push(`/dashboard/messages?user=${contestant.userId}`)
                  }}
                >
                  <MessageCircle className="w-3 h-3 mr-1" />
                  {language === 'fr' ? 'Message' : language === 'es' ? 'Mensaje' : language === 'de' ? 'Nachricht' : 'Message'}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

