'use client'

import { useLanguage } from '@/contexts/language-context'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface HoverInfoDialogProps {
  isOpen?: boolean
  onOpenChange?: (open: boolean) => void
  type: 'author' | 'description' | 'votes' | 'reactions' | 'favorites' | 'shares'
  data?: any
  onClose?: () => void
}

export function HoverInfoDialog({
  isOpen = true,
  onOpenChange,
  type,
  data,
  onClose
}: HoverInfoDialogProps) {
  const { t, language } = useLanguage()
  
  const handleOpenChange = (open: boolean) => {
    if (onOpenChange) {
      onOpenChange(open)
    }
    if (!open && onClose) {
      onClose()
    }
  }

  const getTitle = () => {
    switch (type) {
      case 'author':
        return language === 'fr' ? 'Détails de l\'auteur' : language === 'es' ? 'Detalles del autor' : language === 'de' ? 'Autorendetails' : 'Author Details'
      case 'description':
        return language === 'fr' ? 'Description' : language === 'es' ? 'Descripción' : language === 'de' ? 'Beschreibung' : 'Description'
      case 'votes':
        return t('dashboard.contests.votes') || (language === 'fr' ? 'Votes' : language === 'es' ? 'Votos' : language === 'de' ? 'Stimmen' : 'Votes')
      case 'reactions':
        return language === 'fr' ? 'Réactions' : language === 'es' ? 'Reacciones' : language === 'de' ? 'Reaktionen' : 'Reactions'
      case 'favorites':
        return language === 'fr' ? 'Favoris' : language === 'es' ? 'Favoritos' : language === 'de' ? 'Favoriten' : 'Favorites'
      case 'shares':
        return language === 'fr' ? 'Partages' : language === 'es' ? 'Compartidos' : language === 'de' ? 'Geteilt' : 'Shares'
      default:
        return ''
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{getTitle()}</DialogTitle>
        </DialogHeader>
        <div className="mt-4">
          {type === 'author' && data && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <img
                  src={data.avatar || '/default-avatar.png'}
                  alt={data.name}
                  className="w-16 h-16 rounded-full object-cover"
                />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    {data.name}
                  </h3>
                  {data.country && (
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {data.country}{data.city ? `, ${data.city}` : ''}
                    </p>
                  )}
                </div>
              </div>
              {data.rank && (
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {t('dashboard.contests.rank') || 'Rank'}: {data.rank}
                  </p>
                </div>
              )}
            </div>
          )}
          
          {type === 'description' && data && (
            <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              {data}
            </p>
          )}
          
          {type === 'votes' && data && Array.isArray(data) && (
            <div className="space-y-2">
              {data.map((vote: any, index: number) => (
                <div key={index} className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700">
                  <img
                    src={vote.avatar_url || '/default-avatar.png'}
                    alt={vote.username || 'User'}
                    className="w-8 h-8 rounded-full object-cover"
                  />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {vote.full_name || vote.username || 'User'}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {new Date(vote.vote_date).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {type === 'reactions' && data && typeof data === 'object' && (
            <div className="space-y-4">
              {Object.entries(data).map(([reactionType, reactions]: [string, any]) => (
                <div key={reactionType}>
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 capitalize">
                    {reactionType}
                  </h4>
                  <div className="space-y-2">
                    {Array.isArray(reactions) && reactions.map((reaction: any, index: number) => (
                      <div key={index} className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700">
                        <img
                          src={reaction.avatar_url || '/default-avatar.png'}
                          alt={reaction.username || 'User'}
                          className="w-8 h-8 rounded-full object-cover"
                        />
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          {reaction.full_name || reaction.username || 'User'}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {type === 'favorites' && data && Array.isArray(data) && (
            <div className="space-y-2">
              {data.map((favorite: any, index: number) => (
                <div key={index} className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700">
                  <img
                    src={favorite.avatar_url || '/default-avatar.png'}
                    alt={favorite.username || 'User'}
                    className="w-8 h-8 rounded-full object-cover"
                  />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {favorite.full_name || favorite.username || 'User'}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {new Date(favorite.added_date).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {type === 'shares' && data && Array.isArray(data) && (
            <div className="space-y-2">
              {data.map((share: any, index: number) => (
                <div key={index} className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700">
                  <img
                    src={share.avatar_url || '/default-avatar.png'}
                    alt={share.username || 'User'}
                    className="w-8 h-8 rounded-full object-cover"
                  />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {share.full_name || share.username || 'User'}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      {share.platform && (
                        <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-gray-600 dark:text-gray-400">
                          {share.platform}
                        </span>
                      )}
                      {share.created_at && (
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {new Date(share.created_at).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

