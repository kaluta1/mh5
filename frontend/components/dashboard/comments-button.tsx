'use client'

import { MessageCircle } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

interface CommentsButtonProps {
  onClick: () => void
  commentsCount?: number
}

export function CommentsButton({ onClick, commentsCount }: CommentsButtonProps) {
  const { t } = useLanguage()

  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className="flex items-center justify-center gap-2 py-3 px-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
    >
      <MessageCircle className="w-5 h-5" />
      <span className="hidden sm:inline">{t('dashboard.contests.comments')}</span>
      {commentsCount !== undefined && commentsCount > 0 && (
        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
          ({commentsCount})
        </span>
      )}
    </button>
  )
}

