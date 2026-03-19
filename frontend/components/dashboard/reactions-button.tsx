'use client'

import { useState, useEffect, useRef } from 'react'
import { ThumbsUp, Heart, Smile, ThumbsDown, Star } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { reactionsService, ReactionDetails } from '@/services/reactions-service'
import Image from 'next/image'

interface ReactionsButtonProps {
  contestantId: number
  selectedReaction?: string | null
  onReactionSelect: (reactionType: string) => void
  onReactionSuccess?: () => void
  isAuthor?: boolean
  reactionsCount?: number
}

export function ReactionsButton({ contestantId, selectedReaction, onReactionSelect, onReactionSuccess, isAuthor = false, reactionsCount = 0 }: ReactionsButtonProps) {
  const { t } = useLanguage()
  const [showPopover, setShowPopover] = useState(false)
  const [showDetailsPopover, setShowDetailsPopover] = useState(false)
  const [reactionDetails, setReactionDetails] = useState<ReactionDetails | null>(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const reactions = [
    { key: 'like', icon: ThumbsUp, color: 'text-blue-500', label: t('dashboard.contests.like') || 'J\'aime' },
    { key: 'love', icon: Heart, color: 'text-red-500', label: t('dashboard.contests.love') || 'J\'adore' },
    { key: 'wow', icon: Smile, color: 'text-yellow-500', label: t('dashboard.contests.wow') || 'Wow' },
    { key: 'dislike', icon: ThumbsDown, color: 'text-gray-500', label: t('dashboard.contests.dislike') || 'Je n\'aime pas' }
  ]

  const selectedReactionData = reactions.find(r => r.key === selectedReaction)
  const IconComponent = selectedReactionData?.icon || Star

  const handleReactionClick = async (reactionType: string) => {
    const wasSelected = selectedReaction === reactionType
    await onReactionSelect(reactionType)
    setShowPopover(false)
    if (onReactionSuccess) {
      onReactionSuccess()
    }
  }

  const loadReactionDetails = async () => {
    if (loadingDetails || reactionDetails) return
    setLoadingDetails(true)
    try {
      const details = await reactionsService.getReactionDetails(contestantId)
      setReactionDetails(details)
    } catch (error) {
      console.error('Error loading reaction details:', error)
    } finally {
      setLoadingDetails(false)
    }
  }

  const handleMouseEnter = () => {
    if (!isAuthor) return // Afficher le popover uniquement si l'utilisateur est l'auteur
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setShowDetailsPopover(true)
    loadReactionDetails()
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
          setShowPopover(!showPopover)
        }}
        className={`flex items-center justify-center gap-1.5 py-2.5 px-1 text-xs font-medium transition-colors w-full ${
          selectedReaction
            ? 'text-purple-600 dark:text-purple-400'
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
        }`}
      >
        <IconComponent className={`w-4 h-4 flex-shrink-0 ${selectedReaction ? 'fill-current' : ''}`} />
        <span className="hidden sm:inline">{t('dashboard.contests.reaction') || 'Réaction'}</span>
        {reactionsCount > 0 && (
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
            {reactionsCount}
          </span>
        )}
      </button>
      
      {/* Popover avec détails des réactions au survol */}
      {showDetailsPopover && isAuthor && (
        <div
          className="absolute bottom-full left-0 mb-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-50 min-w-[280px] max-w-[320px] max-h-[400px] overflow-y-auto"
          onMouseEnter={() => { if (timeoutRef.current) clearTimeout(timeoutRef.current) }}
          onMouseLeave={handleMouseLeave}
        >
          <div className="p-3">
            <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-3">
              {t('dashboard.contests.reactions') || 'Réactions'}
            </h4>
            {loadingDetails ? (
              <div className="text-sm text-gray-500 dark:text-gray-400 py-2">
                {t('dashboard.contests.loading') || 'Chargement...'}
              </div>
            ) : reactionDetails && Object.keys(reactionDetails.reactions_by_type).length > 0 ? (
              <div className="space-y-4">
                {['like', 'love', 'wow', 'dislike'].map((reactionType) => {
                  const users = reactionDetails.reactions_by_type[reactionType] || []
                  if (users.length === 0) return null
                  
                  const reactionData = reactions.find(r => r.key === reactionType)
                  const Icon = reactionData?.icon || Star
                  
                  return (
                    <div key={reactionType} className="space-y-2">
                      <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                        <Icon className={`w-4 h-4 ${reactionData?.color || 'text-gray-500'}`} />
                        <span>{reactionData?.label || reactionType}</span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">({users.length})</span>
                      </div>
                      <div className="space-y-1 pl-6">
                        {users.slice(0, 5).map((user) => (
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
                            <span className="text-gray-700 dark:text-gray-300">
                              {user.full_name || user.username || `User ${user.user_id}`}
                            </span>
                          </div>
                        ))}
                        {users.length > 5 && (
                          <div className="text-xs text-gray-500 dark:text-gray-400 pl-6">
                            +{users.length - 5} {t('dashboard.contests.more') || 'de plus'}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="text-sm text-gray-500 dark:text-gray-400 py-2">
                {t('dashboard.contests.no_reactions') || 'Aucune réaction'}
              </div>
            )}
          </div>
        </div>
      )}
      
      {/* Reactions Dropdown - Only shows on click */}
      {showPopover && (
        <>
          {/* Backdrop to close on outside click */}
          <div
            className="fixed inset-0 z-40"
            onClick={(e) => {
              e.stopPropagation()
              setShowPopover(false)
            }}
          />
          <div 
            className="absolute bottom-full left-0 mb-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-50 min-w-[200px]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-2">
              <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2 px-2">
                {t('dashboard.contests.reactions') || 'Réactions'}
              </h4>
              <div className="space-y-1">
                {reactions.map(({ key, icon: Icon, color, label }) => (
                  <button
                    key={key}
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      handleReactionClick(key)
                    }}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors text-left ${
                      selectedReaction === key
                        ? 'bg-gray-100 dark:bg-gray-700'
                        : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                    }`}
                  >
                    <Icon className={`w-5 h-5 ${color} ${selectedReaction === key ? 'fill-current' : ''}`} />
                    <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

