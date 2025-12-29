'use client'

import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
// import { UserPlus, MessageCircle } from 'lucide-react' // Boutons cachés
import { useLanguage } from '@/contexts/language-context'

interface Contestant {
  id: string
  userId?: number
  name: string
  country?: string
  city?: string
  continent?: string
  region?: string
  avatar: string
  rank?: number
}

interface ContestantsSidebarProps {
  contestants: Contestant[]
  contestId: string
  formatLocation?: (contestant: Contestant) => string
  onShowToast: (message: string, type: 'success' | 'error') => void
}

export function ContestantsSidebar({
  contestants,
  contestId,
  formatLocation,
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
        <div className="bg-white dark:bg-gray-800/90 rounded-xl border border-gray-200/50 dark:border-gray-700/50 shadow-md backdrop-blur-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
              {t('dashboard.contests.contestants') || 'Participants'}
            </h3>
            {contestants.length > 5 && (
              <Button
                variant="outline"
                size="sm"
                className="text-xs border-myhigh5-primary/30 text-myhigh5-primary hover:bg-myhigh5-primary hover:text-white transition-all"
                onClick={() => router.push(`/dashboard/contests/${contestId}/contestants`)}
              >
                {language === 'fr' ? 'Voir tout' : language === 'es' ? 'Ver todo' : language === 'de' ? 'Alle anzeigen' : 'View all'}
              </Button>
            )}
          </div>
          
          <div className="space-y-2">
            {topContestants.map((contestant) => (
              <div
                key={contestant.id}
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-gradient-to-r hover:from-gray-50 hover:to-gray-100/50 dark:hover:from-gray-700/50 dark:hover:to-gray-700/30 transition-all duration-200 border border-transparent hover:border-gray-200 dark:hover:border-gray-700/50 cursor-pointer group"
              >
                <div className="relative flex-shrink-0">
                  <img
                    src={contestant.avatar || '/default-avatar.png'}
                    alt={contestant.name}
                    className="w-12 h-12 rounded-full object-cover ring-2 ring-gray-200 dark:ring-gray-700 group-hover:ring-myhigh5-primary/50 transition-all"
                  />
                  {contestant.rank && contestant.rank <= 3 && (
                    <span className="absolute -top-1 -right-1 text-xs font-bold bg-myhigh5-primary text-white rounded-full w-5 h-5 flex items-center justify-center shadow-lg">
                      {contestant.rank}
                    </span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white truncate group-hover:text-myhigh5-primary dark:group-hover:text-myhigh5-blue-400 transition-colors">
                    {contestant.name}
                  </p>
                  {formatLocation ? (
                    formatLocation(contestant) && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                        {formatLocation(contestant)}
                      </p>
                    )
                  ) : (
                    contestant.country && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                        {contestant.country}{contestant.city ? `, ${contestant.city}` : ''}
                      </p>
                    )
                  )}
                  {contestant.rank && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {language === 'fr' ? 'Rang' : language === 'es' ? 'Rango' : language === 'de' ? 'Rang' : 'Rank'}: {contestant.rank}
                    </p>
                  )}
                </div>
                {/* Boutons Follow et Message cachés */}
                {/* <div className="flex flex-col gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs px-2 py-1 h-auto border-myhigh5-primary/30 text-myhigh5-primary hover:bg-myhigh5-primary hover:text-white transition-all"
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
                    className="text-xs px-2 py-1 h-auto border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-all"
                    onClick={() => {
                      // TODO: Implement message functionality
                      router.push(`/dashboard/messages?user=${contestant.userId}`)
                    }}
                  >
                    <MessageCircle className="w-3 h-3 mr-1" />
                    {language === 'fr' ? 'Message' : language === 'es' ? 'Mensaje' : language === 'de' ? 'Nachricht' : 'Message'}
                  </Button>
                </div> */}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

