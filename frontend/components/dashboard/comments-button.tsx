'use client'

import { MessageCircle } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

interface CommentsButtonProps {
  onClick: () => void
}

export function CommentsButton({ onClick }: CommentsButtonProps) {
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
    </button>
  )
}

