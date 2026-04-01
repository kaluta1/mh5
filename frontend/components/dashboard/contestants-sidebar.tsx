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
  totalPoints?: number
}

interface ContestantsSidebarProps {
  contestants: Contestant[]
  contestId: string
  formatLocation?: (contestant: Contestant) => string
  onShowToast: (message: string, type: 'success' | 'error') => void
  /** When set, "View all" link includes these filters so contestants page shows same list as contest page */
  filterCountry?: string
  filterContinent?: string
  /** Calendar round (March vs April) — must match contest detail query */
  roundId?: string
}

export function ContestantsSidebar({
  contestants,
  contestId,
  formatLocation,
  onShowToast,
  filterCountry,
  filterContinent,
  roundId
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
        <div className="bg-white dark:bg-gray-800/90 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 shadow-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-yellow-400 to-amber-500 flex items-center justify-center text-sm shadow-sm">&#127942;</span>
              {language === 'fr' ? 'Classement' : language === 'es' ? 'Clasificación' : language === 'de' ? 'Rangliste' : 'Leaderboard'}
            </h3>
            {contestants.length >= 1 && (
              <Button
                variant="outline"
                size="sm"
                className="text-xs border-myhigh5-primary/30 dark:border-gray-500 text-myhigh5-primary dark:text-white hover:bg-myhigh5-primary hover:text-white transition-all"
                onClick={() => {
                  const params = new URLSearchParams()
                  if (roundId) params.set('roundId', roundId)
                  if (filterCountry) params.set('country', filterCountry)
                  if (filterContinent && filterContinent !== 'all') params.set('continent', filterContinent)
                  const qs = params.toString()
                  router.push(`/dashboard/contests/${contestId}/contestants${qs ? `?${qs}` : ''}`)
                }}
              >
                {language === 'fr' ? 'Voir tout' : language === 'es' ? 'Ver todo' : language === 'de' ? 'Alle anzeigen' : 'View all'}
              </Button>
            )}
          </div>
          
          <div className="space-y-2">
            {topContestants.map((contestant) => (
              <div
                key={contestant.id}
                className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-all duration-200 cursor-pointer group"
              >

                <div className="relative flex-shrink-0">
                  {contestant.avatar && contestant.avatar !== '/default-avatar.png' ? (
                    <img
                      src={contestant.avatar}
                      alt={contestant.name}
                      className="w-10 h-10 rounded-full object-cover ring-2 ring-gray-200 dark:ring-gray-700 group-hover:ring-myhigh5-primary/50 transition-all"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; (e.target as HTMLImageElement).nextElementSibling?.classList.remove('hidden') }}
                    />
                  ) : null}
                  {(!contestant.avatar || contestant.avatar === '/default-avatar.png') && (
                    <div className="w-10 h-10 rounded-full ring-2 ring-gray-200 dark:ring-gray-700 group-hover:ring-myhigh5-primary/50 transition-all bg-gradient-to-br from-myhigh5-primary to-blue-600 flex items-center justify-center">
                      <span className="text-sm font-bold text-white">
                        {contestant.name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || '?'}
                      </span>
                    </div>
                  )}

                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white truncate group-hover:text-myhigh5-primary dark:group-hover:text-white transition-colors">
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
                  {contestant.totalPoints !== undefined && contestant.totalPoints > 0 && (
                    <p className="text-xs font-medium text-myhigh5-primary dark:text-blue-400">
                      {contestant.totalPoints} pts
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

