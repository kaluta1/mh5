'use client'

import { MoreHorizontal, Edit, Trash2, Heart, Share2, Flag } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useLanguage } from '@/contexts/language-context'

/**
 * Props pour le menu d'actions d'un contestant
 * 
 * Ce composant est réutilisable et peut être utilisé partout où on a besoin d'afficher
 * les actions disponibles pour un contestant (favoris, partage, signalement, etc.)
 * 
 * @example
 * ```tsx
 * <ContestantActionsMenu
 *   isAuthor={currentUserId === contestant.userId}
 *   isFavorite={favorites.includes(contestant.id)}
 *   hasReported={contestant.hasReported}
 *   onToggleFavorite={() => handleToggleFavorite(contestant.id)}
 *   onShare={() => handleShare(contestant.id)}
 *   onReport={!hasReported && !isAuthor ? () => handleReport(contestant.id) : undefined}
 * />
 * ```
 */
interface ContestantActionsMenuProps {
  /** Indique si l'utilisateur actuel est l'auteur du contestant */
  isAuthor: boolean
  /** Indique si le contestant est dans les favoris de l'utilisateur */
  isFavorite: boolean
  /** Indique si l'utilisateur a déjà signalé ce contestant */
  hasReported?: boolean
  /** Callback pour l'édition (seulement si isAuthor est true) */
  onEdit?: () => void
  /** Callback pour la suppression (seulement si isAuthor est true) */
  onDelete?: () => void
  /** Callback pour ajouter/retirer des favoris */
  onToggleFavorite: () => void
  /** Callback pour partager */
  onShare: () => void
  /** 
   * Callback pour signaler
   * Ne sera affiché que si :
   * - onReport est défini (l'utilisateur n'est pas l'auteur)
   * - hasReported est false (l'utilisateur n'a pas déjà signalé)
   */
  onReport?: () => void
}

/**
 * Menu d'actions pour un contestant
 * 
 * Affiche un menu déroulant avec les actions disponibles :
 * - Édition/Suppression (si l'utilisateur est l'auteur)
 * - Ajouter/Retirer des favoris
 * - Partager
 * - Signaler (si l'utilisateur n'est pas l'auteur et n'a pas déjà signalé)
 * 
 * Le bouton "Signaler" est automatiquement masqué si :
 * - hasReported est true
 * - onReport est undefined (l'utilisateur est l'auteur)
 */

export function ContestantActionsMenu({
  isAuthor,
  isFavorite,
  hasReported = false,
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
        
        {/* Bouton de signalement - affiché uniquement si :
            - onReport est défini (l'utilisateur n'est pas l'auteur)
            - hasReported est false (l'utilisateur n'a pas déjà signalé)
        */}
        {onReport && !hasReported ? (
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onReport()
            }}
          >
            <Flag className="w-4 h-4 mr-2" />
            {t('dashboard.contests.report') || 'Signaler'}
          </DropdownMenuItem>
        ) : hasReported ? (
          <DropdownMenuItem disabled className="text-gray-400 dark:text-gray-500 cursor-not-allowed">
            <Flag className="w-4 h-4 mr-2" />
            {t('dashboard.contests.already_reported') || 'Déjà signalé'}
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

