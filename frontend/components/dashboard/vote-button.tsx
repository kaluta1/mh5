'use client'

import { useState, useRef } from 'react'
import { ThumbsUp } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { contestService } from '@/services/contest-service'
import Image from 'next/image'

interface VoteButtonProps {
  contestantId: number
  canVote: boolean
  hasVoted: boolean
  isVoting: boolean
  onVote: () => void
  isAuthor?: boolean
  votesCount?: number
}

export function VoteButton({ contestantId, canVote, hasVoted, isVoting, onVote, isAuthor = false, votesCount = 0 }: VoteButtonProps) {
  const { t } = useLanguage()
  const [showDetailsPopover, setShowDetailsPopover] = useState(false)
  const [voteDetails, setVoteDetails] = useState<any>(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const loadVoteDetails = async () => {
    if (loadingDetails || voteDetails) return
    setLoadingDetails(true)
    try {
      const details = await contestService.getVoteDetails(contestantId)
      setVoteDetails(details)
    } catch (error) {
      console.error('Error loading vote details:', error)
    } finally {
      setLoadingDetails(false)
    }
  }

  const handleMouseEnter = () => {
    if (!isAuthor) return // Afficher le popover uniquement si l'utilisateur est l'auteur
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setShowDetailsPopover(true)
    loadVoteDetails()
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
          if (canVote) onVote()
        }}
        disabled={!canVote || isVoting}
        className={`flex items-center justify-center gap-2 py-3 px-2 text-sm font-medium transition-colors ${
          hasVoted
            ? 'text-blue-600 dark:text-blue-400'
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
        } ${!canVote || isVoting ? 'opacity-50 cursor-not-allowed' : ''}`}
        title={!canVote ? (hasVoted ? t('dashboard.contests.already_voted') : t('dashboard.contests.cannot_vote')) : ''}
      >
        <ThumbsUp className={`w-5 h-5 ${hasVoted ? 'fill-current' : ''}`} />
        <span className="hidden sm:inline">{t('dashboard.contests.vote')}</span>
        {votesCount > 0 && (
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
            {votesCount}
          </span>
        )}
      </button>
      
      {/* Popover avec détails des votes au survol */}
      {showDetailsPopover && isAuthor && (
        <div
          className="absolute bottom-full left-0 mb-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-50 min-w-[280px] max-w-[320px] max-h-[400px] overflow-y-auto"
          onMouseEnter={() => { if (timeoutRef.current) clearTimeout(timeoutRef.current) }}
          onMouseLeave={handleMouseLeave}
        >
          <div className="p-3">
            <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-3">
              {t('dashboard.contests.votes') || 'Votes'}
            </h4>
            {loadingDetails ? (
              <div className="text-sm text-gray-500 dark:text-gray-400 py-2">
                {t('dashboard.contests.loading') || 'Chargement...'}
              </div>
            ) : voteDetails && voteDetails.voters && voteDetails.voters.length > 0 ? (
              <div className="space-y-2">
                {voteDetails.voters.slice(0, 10).map((voter: any) => (
                  <div key={voter.user_id} className="flex items-center justify-between gap-2 text-sm">
                    <div className="flex items-center gap-2 flex-1">
                      {voter.avatar_url ? (
                        <Image
                          src={voter.avatar_url}
                          alt={voter.full_name || voter.username || ''}
                          width={24}
                          height={24}
                          className="rounded-full"
                        />
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center text-xs">
                          {(voter.full_name || voter.username || 'U')[0].toUpperCase()}
                        </div>
                      )}
                      <span className="text-gray-700 dark:text-gray-300">
                        {voter.full_name || voter.username || `User ${voter.user_id}`}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {voter.points} {t('dashboard.contests.points') || 'pts'}
                    </span>
                  </div>
                ))}
                {voteDetails.voters.length > 10 && (
                  <div className="text-xs text-gray-500 dark:text-gray-400 pt-2 border-t border-gray-200 dark:border-gray-700">
                    +{voteDetails.voters.length - 10} {t('dashboard.contests.more') || 'de plus'}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-gray-500 dark:text-gray-400 py-2">
                {t('dashboard.contests.no_votes') || 'Aucun vote'}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

