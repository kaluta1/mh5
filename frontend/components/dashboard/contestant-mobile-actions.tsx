'use client'

import { Button } from '@/components/ui/button'
import { MessageCircle } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

interface ContestantMobileActionsProps {
  commentsCount: number
  hasVoted: boolean
  canVote: boolean
  isVoting: boolean
  onCommentsClick: () => void
  onVote: () => void
}

export function ContestantMobileActions({
  commentsCount,
  hasVoted,
  canVote,
  isVoting,
  onCommentsClick,
  onVote
}: ContestantMobileActionsProps) {
  const { t } = useLanguage()

  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 p-4 bg-white/95 dark:bg-gray-900/95 backdrop-blur-md border-t border-gray-200/50 dark:border-gray-700/50 shadow-2xl z-40 flex gap-3">
      <Button
        onClick={onCommentsClick}
        variant="outline"
        className="flex-1 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-xl font-medium hover:bg-gray-50 dark:hover:bg-gray-800 transition-all"
      >
        <MessageCircle className="w-5 h-5 mr-2" />
        {t('contestant_detail.comments')} ({commentsCount})
      </Button>
      <Button
        onClick={onVote}
        disabled={!canVote || isVoting || hasVoted}
        className={`flex-1 font-semibold py-3 text-base rounded-xl transition-all duration-300 ${
          hasVoted
            ? 'bg-gray-400 dark:bg-gray-700 text-white cursor-not-allowed'
            : 'bg-gradient-to-r from-myfav-primary via-myfav-primary-dark to-indigo-600 text-white hover:shadow-lg active:scale-95'
        }`}
      >
        {isVoting ? t('contestant_detail.voting') : hasVoted ? (t('contestant_detail.voted') || 'Voted') : t('contestant_detail.vote')}
      </Button>
    </div>
  )
}

