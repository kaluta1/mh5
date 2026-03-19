'use client'

import { Search, HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
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
    <div className="sticky top-0 z-40 bg-white/95 dark:bg-gray-900/95 backdrop-blur-md border-b border-gray-200/50 dark:border-gray-800/50 mb-8 -mx-4 sm:-mx-2 lg:-mx-8 px-4 sm:px-2 lg:px-8 py-6 shadow-sm">
      <div className="flex flex-col gap-4 mb-4">
        {/* Title Section */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 dark:from-white dark:via-gray-100 dark:to-white bg-clip-text text-transparent mb-2">
              {contest.name}
            </h1>
            {contest.contest_type && (
              <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400 font-medium mt-1">
                {contest.contest_type}
              </p>
            )}
          </div>
          {/* Info Button */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  onClick={onInfoClick}
                  variant="outline"
                  size="icon"
                  className="rounded-full border-myhigh5-primary text-myhigh5-primary hover:bg-myhigh5-blue-50 dark:hover:bg-myhigh5-blue-900/20 cursor-help"
                >
                  <HelpCircle className="w-5 h-5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent className="bg-white text-gray-900 border-gray-200 shadow-lg dark:bg-gray-800 dark:text-white dark:border-gray-700">
                <p className="text-xs">{t('dashboard.contests.tooltip_info') || 'Voir les détails et les conditions du concours'}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        
        {/* Stats and Badges Section */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge className={`${getStatusColor(contest.level)} border-0 text-xs font-semibold px-3 py-1.5 cursor-help`}>
                    {getStatusLabel(contest.level)}
                  </Badge>
                </TooltipTrigger>
                <TooltipContent className="bg-white text-gray-900 border-gray-200 shadow-lg dark:bg-gray-800 dark:text-white dark:border-gray-700">
                  <p className="text-xs">
                    {contest.level === 'city' 
                      ? (t('dashboard.contests.tooltip_level_city') || 'Concours au niveau de la ville')
                      : contest.level === 'country'
                      ? (t('dashboard.contests.tooltip_level_country') || 'Concours au niveau national')
                      : contest.level === 'regional'
                      ? (t('dashboard.contests.tooltip_level_regional') || 'Concours au niveau régional')
                      : contest.level === 'continental'
                      ? (t('dashboard.contests.tooltip_level_continental') || 'Concours au niveau continental')
                      : (t('dashboard.contests.tooltip_level_global') || 'Concours au niveau mondial')}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge
                    className={`${
                      contest.is_submission_open
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                        : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                    } border-0 text-xs font-semibold px-3 py-1.5 cursor-help`}
                  >
                    {contest.is_submission_open ? t('dashboard.contests.open') : t('dashboard.contests.closed')}
                  </Badge>
                </TooltipTrigger>
                <TooltipContent className="bg-white text-gray-900 border-gray-200 shadow-lg dark:bg-gray-800 dark:text-white dark:border-gray-700">
                  <p className="text-xs">
                    {contest.is_submission_open 
                      ? (t('dashboard.contests.tooltip_open') || 'Le concours est actuellement ouvert. Vous pouvez concourir à ce concours.')
                      : (t('dashboard.contests.tooltip_closed') || 'Le concours est fermé. Les inscriptions ne sont plus acceptées.')}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            {contest.is_voting_open && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge className="bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 border-0 text-xs font-semibold px-3 py-1.5 cursor-help">
                      🗳️ {t('dashboard.contests.voting')} {t('dashboard.contests.open')}
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent className="bg-white text-gray-900 border-gray-200 shadow-lg dark:bg-gray-800 dark:text-white dark:border-gray-700">
                    <p className="text-xs">
                      {t('dashboard.contests.tooltip_voting_open') || 'Le vote est actuellement ouvert. Vous pouvez voter pour les participants.'}
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-help">
                    <span className="font-semibold">{participantsCount}</span>
                    <span>{t('dashboard.contests.contestants')}</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent className="bg-white text-gray-900 border-gray-200 shadow-lg dark:bg-gray-800 dark:text-white dark:border-gray-700">
                  <p className="text-xs">
                    {t('dashboard.contests.tooltip_contestants') || `${participantsCount} participant${participantsCount > 1 ? 's' : ''} dans ce concours`}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
    
          {/* Search Bar */}
          <div className="relative w-full sm:w-auto sm:min-w-[300px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
            <input
              type="text"
              placeholder={t('dashboard.contests.search_contestant') || 'Rechercher un participant...'}
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 text-sm border border-gray-300 dark:border-gray-700 rounded-xl bg-white dark:bg-gray-800/50 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary/50 focus:border-myhigh5-primary/50 transition-all shadow-sm hover:shadow-md"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

