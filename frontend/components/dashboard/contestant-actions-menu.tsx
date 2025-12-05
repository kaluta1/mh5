'use client'

import { MoreHorizontal, Edit, Trash2, Heart, Share2, Flag } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useLanguage } from '@/contexts/language-context'

interface ContestantActionsMenuProps {
  isAuthor: boolean
  isFavorite: boolean
  onEdit?: () => void
  onDelete?: () => void
  onToggleFavorite: () => void
  onShare: () => void
  onReport?: () => void
}

export function ContestantActionsMenu({
  isAuthor,
  isFavorite,
  onEdit,
  onDelete,
  onToggleFavorite,
  onShare,
  onReport
}: ContestantActionsMenuProps) {
  const { t } = useLanguage()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          onClick={(e) => {
            e.stopPropagation()
          }}
          className="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <MoreHorizontal className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        {isAuthor && (
          <>
            {onEdit && (
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onEdit()
                }}
              >
                <Edit className="w-4 h-4 mr-2" />
                {t('dashboard.contests.edit')}
              </DropdownMenuItem>
            )}
            {onDelete && (
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete()
                }}
                className="text-red-600 dark:text-red-400"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                {t('dashboard.contests.delete')}
              </DropdownMenuItem>
            )}
            <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
          </>
        )}
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation()
            onToggleFavorite()
          }}
        >
          <Heart className={`w-4 h-4 mr-2 ${isFavorite ? 'fill-current text-red-500' : ''}`} />
          {isFavorite ? t('dashboard.contests.remove_from_favorites') : t('dashboard.contests.add_to_favorites')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation()
            onShare()
          }}
        >
          <Share2 className="w-4 h-4 mr-2" />
          {t('dashboard.contests.share') || 'Partager'}
        </DropdownMenuItem>
        {onReport && (
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onReport()
            }}
          >
            <Flag className="w-4 h-4 mr-2" />
            {t('dashboard.contests.report') || 'Signaler'}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

