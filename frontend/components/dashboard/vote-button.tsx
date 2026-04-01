'use client'

import { useState, useRef } from 'react'
import { ThumbsUp, AlertCircle } from 'lucide-react'
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
  voteRestrictionReason?: string | null
}

export function VoteButton({ contestantId, canVote, hasVoted, isVoting, onVote, isAuthor = false, votesCount = 0, voteRestrictionReason }: VoteButtonProps) {
  const { t } = useLanguage()
  const [showDetailsPopover, setShowDetailsPopover] = useState(false)
  const [showRestrictionPopover, setShowRestrictionPopover] = useState(false)
  const [voteDetails, setVoteDetails] = useState<any>(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const restrictionTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const getVoteButtonText = () => {
    if (isVoting) {
      return t('contestant_detail.voting') || 'Voting...'
    }
    if (isAuthor) {
      return t('dashboard.contests.vote') || 'Vote'
    }
    if (hasVoted) {
      return t('dashboard.contests.already_voted') || 'Already voted'
    }
    if (!canVote && voteRestrictionReason) {
      switch (voteRestrictionReason) {
        case 'already_voted':
          return t('dashboard.contests.already_voted') || 'Already voted'
        case 'different_city':
          return t('dashboard.contests.restriction_different_city') || 'Different city'
        case 'different_country':
          return t('dashboard.contests.restriction_different_country') || 'Different country'
        case 'different_region':
          return t('dashboard.contests.restriction_different_region') || 'Different region'
        case 'different_continent':
          return t('dashboard.contests.restriction_different_continent') || 'Different continent'
        case 'own_contestant':
          return t('dashboard.contests.restriction_own_contestant') || 'Your own contestant'
        case 'not_authenticated':
          return t('dashboard.contests.restriction_not_authenticated') || 'Please login to vote'
        case 'geographic_restriction':
          return t('dashboard.contests.restriction_geographic') || 'Geographic restriction'
        case 'voting_not_open':
          return t('dashboard.contests.voting_not_open') || 'Voting not yet open'
        case 'user_not_found':
          return t('dashboard.contests.restriction_user_not_found') || 'User not found'
        default:
          return t('dashboard.contests.cannot_vote') || 'Cannot vote'
      }
    }
    return t('dashboard.contests.vote') || 'Vote'
  }

  const getVoteButtonTitle = () => {
    if (hasVoted) {
      return t('dashboard.contests.already_voted') || 'Already voted'
    }
    if (!canVote && voteRestrictionReason) {
      switch (voteRestrictionReason) {
        case 'already_voted':
          return t('dashboard.contests.already_voted') || 'Already voted'
        case 'different_city':
          return t('dashboard.contests.restriction_different_city_desc') || 'You can only vote for contestants from your city'
        case 'different_country':
          return t('dashboard.contests.restriction_different_country_desc') || 'You can only vote for contestants from your country'
        case 'different_region':
          return t('dashboard.contests.restriction_different_region_desc') || 'You can only vote for contestants from your region'
        case 'different_continent':
          return t('dashboard.contests.restriction_different_continent_desc') || 'You can only vote for contestants from your continent'
        case 'own_contestant':
          return t('dashboard.contests.restriction_own_contestant_desc') || 'You cannot vote for your own contestant'
        case 'not_authenticated':
          return t('dashboard.contests.restriction_not_authenticated_desc') || 'Please login to vote'
        case 'geographic_restriction':
          return t('dashboard.contests.restriction_geographic_desc') || 'You cannot vote due to geographic restrictions'
        case 'voting_not_open':
          return t('dashboard.contests.voting_not_open') || "Le vote n'est pas encore ouvert"
        case 'user_not_found':
          return t('dashboard.contests.restriction_user_not_found_desc') || 'User not found'
        default:
          return t('dashboard.contests.cannot_vote') || 'Cannot vote'
      }
    }
    return ''
  }

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
    if (isAuthor) {
      // Afficher le popover avec les détails des votes si l'utilisateur est l'auteur
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      setShowDetailsPopover(true)
      loadVoteDetails()
    } else if (!canVote && voteRestrictionReason) {
      // Afficher le popover avec la restriction si l'utilisateur ne peut pas voter
      if (restrictionTimeoutRef.current) clearTimeout(restrictionTimeoutRef.current)
      setShowRestrictionPopover(true)
    }
  }

  const handleMouseLeave = () => {
    if (isAuthor) {
      timeoutRef.current = setTimeout(() => {
        setShowDetailsPopover(false)
      }, 200)
    } else if (!canVote && voteRestrictionReason) {
      restrictionTimeoutRef.current = setTimeout(() => {
        setShowRestrictionPopover(false)
      }, 200)
    }
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
          if (canVote && !isAuthor) onVote()
        }}
        disabled={!canVote || isVoting || isAuthor}
        className={`flex items-center justify-center gap-1.5 py-2.5 px-1 text-xs font-medium transition-colors w-full truncate ${
          hasVoted
            ? 'text-blue-600 dark:text-blue-400'
            : isAuthor
            ? 'text-gray-400 dark:text-gray-500'
            : canVote
            ? 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
            : 'text-gray-400 dark:text-gray-500'
        } ${!canVote || isVoting || isAuthor ? 'opacity-50 cursor-not-allowed' : ''}`}
        title={isAuthor ? (t('dashboard.contests.owner_cannot_vote') || 'Owner, cannot vote') : getVoteButtonTitle()}
      >
        <ThumbsUp className={`w-4 h-4 flex-shrink-0 ${hasVoted ? 'fill-current' : ''}`} />
        <span className="hidden sm:inline truncate">{getVoteButtonText()}</span>
        {votesCount > 0 && (
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
            {votesCount}
          </span>
        )}
      </button>
      
      {/* Popover avec détails des votes au survol (pour l'auteur) */}
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

      {/* Popover avec restriction au survol (si l'utilisateur ne peut pas voter) */}
      {showRestrictionPopover && !canVote && voteRestrictionReason && (
        <div
          className="absolute bottom-full left-0 mb-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-red-200 dark:border-red-800 overflow-hidden z-50 min-w-[250px] max-w-[300px]"
          onMouseEnter={() => { if (restrictionTimeoutRef.current) clearTimeout(restrictionTimeoutRef.current) }}
          onMouseLeave={handleMouseLeave}
        >
          <div className="p-3">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red-500 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h4 className="text-xs font-semibold text-red-600 dark:text-red-400 mb-1">
                  {t('dashboard.contests.vote_restriction') || 'Restriction de vote'}
                </h4>
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  {getVoteButtonTitle() || t('dashboard.contests.cannot_vote') || 'Vous ne pouvez pas voter pour ce participant.'}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

