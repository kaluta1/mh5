'use client'

import { Search, HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useLanguage } from '@/contexts/language-context'
import { ContestResponse } from '@/services/contest-service'

interface ContestDetailsHeaderProps {
  contest: ContestResponse
  participantsCount: number
  searchQuery: string
  onSearchChange: (query: string) => void
  onInfoClick: () => void
}

export function ContestDetailsHeader({
  contest,
  participantsCount,
  searchQuery,
  onSearchChange,
  onInfoClick
}: ContestDetailsHeaderProps) {
  const { t } = useLanguage()

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'country':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      case 'continental':
        return 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
      case 'regional':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
      default:
        return 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'country':
        return t('dashboard.contests.country')
      case 'continental':
        return t('dashboard.contests.continental')
      case 'regional':
        return t('dashboard.contests.regional')
      default:
        return status
    }
  }

  return (
    <div className="sticky top-0 z-40 bg-white dark:bg-gray-900 backdrop-blur-sm border-b border-gray-200 dark:border-gray-800 mb-8 -mx-4 sm:-mx-2 lg:-mx-8 px-4 sm:px-2 lg:px-8 py-6">
      <div className="flex flex-col gap-4 mb-4">
        {/* Title Section */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-gray-900 dark:text-white mb-2">
              {contest.name}
            </h1>
            {contest.contest_type && (
              <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400 font-medium">
                {contest.contest_type}
              </p>
            )}
          </div>
          {/* Info Button */}
          <Button
            onClick={onInfoClick}
            variant="outline"
            size="icon"
            className="rounded-full border-myfav-primary text-myfav-primary hover:bg-myfav-blue-50 dark:hover:bg-myfav-blue-900/20"
          >
            <HelpCircle className="w-5 h-5" />
          </Button>
        </div>
        
        {/* Stats and Badges Section */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Badge className={`${getStatusColor(contest.level)} border-0 text-xs font-semibold px-3 py-1.5`}>
              {getStatusLabel(contest.level)}
            </Badge>
            <Badge
              className={`${
                contest.is_submission_open
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                  : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
              } border-0 text-xs font-semibold px-3 py-1.5`}
            >
              {contest.is_submission_open ? t('dashboard.contests.open') : t('dashboard.contests.closed')}
            </Badge>
            {contest.is_voting_open && (
              <Badge className="bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 border-0 text-xs font-semibold px-3 py-1.5">
                🗳️ {t('dashboard.contests.voting')} {t('dashboard.contests.open')}
              </Badge>
            )}
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <span className="font-semibold">{participantsCount}</span>
              <span>{t('dashboard.contests.contestants')}</span>
            </div>
          </div>
    
          {/* Search Bar */}
          <div className="relative w-full sm:w-auto sm:min-w-[300px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder={t('dashboard.contests.search_contestant') || 'Rechercher un participant...'}
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full pl-10 pr-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary focus:border-transparent"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

