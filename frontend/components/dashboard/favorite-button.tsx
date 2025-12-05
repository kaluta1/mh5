'use client'

import { useState, useRef } from 'react'
import { Heart } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { contestService } from '@/services/contest-service'
import Image from 'next/image'

interface FavoriteButtonProps {
  contestantId: number
  isFavorite: boolean
  onToggle: () => void
}

export function FavoriteButton({ contestantId, isFavorite, onToggle }: FavoriteButtonProps) {
  const { t } = useLanguage()
  const [showDetailsPopover, setShowDetailsPopover] = useState(false)
  const [favoriteDetails, setFavoriteDetails] = useState<any>(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const loadFavoriteDetails = async () => {
    if (loadingDetails || favoriteDetails) return
    setLoadingDetails(true)
    try {
      const details = await contestService.getFavoriteDetails(contestantId)
      setFavoriteDetails(details)
    } catch (error) {
      console.error('Error loading favorite details:', error)
    } finally {
      setLoadingDetails(false)
    }
  }

  const handleMouseEnter = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setShowDetailsPopover(true)
    loadFavoriteDetails()
  }

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setShowDetailsPopover(false)
    }, 200)
  }

  return (
    <div 
      ref={containerRef}
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        onClick={(e) => {
          e.stopPropagation()
          onToggle()
        }}
        className={`flex items-center justify-center gap-2 py-3 px-2 text-sm font-medium transition-colors ${
          isFavorite
            ? 'text-red-600 dark:text-red-400'
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
        }`}
      >
        <Heart className={`w-5 h-5 ${isFavorite ? 'fill-current' : ''}`} />
        <span className="hidden sm:inline">{t('dashboard.contests.favorite') || 'Favori'}</span>
      </button>
      
      {/* Popover avec détails des favoris au survol */}
      {showDetailsPopover && (
        <div
          className="absolute bottom-full left-0 mb-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-50 min-w-[280px] max-w-[320px] max-h-[400px] overflow-y-auto"
          onMouseEnter={() => { if (timeoutRef.current) clearTimeout(timeoutRef.current) }}
          onMouseLeave={handleMouseLeave}
        >
          <div className="p-3">
            <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-3">
              {t('dashboard.contests.favorites') || 'Favoris'}
            </h4>
            {loadingDetails ? (
              <div className="text-sm text-gray-500 dark:text-gray-400 py-2">
                {t('dashboard.contests.loading') || 'Chargement...'}
              </div>
            ) : favoriteDetails && favoriteDetails.users && favoriteDetails.users.length > 0 ? (
              <div className="space-y-2">
                {favoriteDetails.users.slice(0, 10).map((user: any) => (
                  <div key={user.user_id} className="flex items-center gap-2 text-sm">
                    {user.avatar_url ? (
                      <Image
                        src={user.avatar_url}
                        alt={user.full_name || user.username || ''}
                        width={24}
                        height={24}
                        className="rounded-full"
                      />
                    ) : (
                      <div className="w-6 h-6 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center text-xs">
                        {(user.full_name || user.username || 'U')[0].toUpperCase()}
                      </div>
                    )}
                    <span className="text-gray-700 dark:text-gray-300 flex-1">
                      {user.full_name || user.username || `User ${user.user_id}`}
                    </span>
                    {user.position && (
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        #{user.position}
                      </span>
                    )}
                  </div>
                ))}
                {favoriteDetails.users.length > 10 && (
                  <div className="text-xs text-gray-500 dark:text-gray-400 pt-2 border-t border-gray-200 dark:border-gray-700">
                    +{favoriteDetails.users.length - 10} {t('dashboard.contests.more') || 'de plus'}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-gray-500 dark:text-gray-400 py-2">
                {t('dashboard.contests.no_favorites') || 'Aucun favori'}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

