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
  voteRestrictionReason?: string | null
  showActions?: boolean
  isSelf?: boolean
  isFollowing?: boolean
  isFollowLoading?: boolean
  onFollowToggle?: () => void
  onMessage?: () => void
}

export function ContestantMobileActions({
  commentsCount,
  hasVoted,
  canVote,
  isVoting,
  onCommentsClick,
  onVote,
  voteRestrictionReason,
  showActions = false,
  isSelf = false,
  isFollowing = false,
  isFollowLoading = false,
  onFollowToggle,
  onMessage
}: ContestantMobileActionsProps) {
  const { t } = useLanguage()

  const getVoteButtonText = () => {
    if (isVoting) {
      return t('contestant_detail.voting') || 'Voting...'
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
        case 'user_not_found':
          return t('dashboard.contests.restriction_user_not_found') || 'User not found'
        default:
          return t('dashboard.contests.cannot_vote') || 'Cannot vote'
      }
    }
    return t('contestant_detail.vote') || 'Vote'
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
        case 'user_not_found':
          return t('dashboard.contests.restriction_user_not_found_desc') || 'User not found'
        default:
          return t('dashboard.contests.cannot_vote') || 'Cannot vote'
      }
    }
    return ''
  }

  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 p-4 bg-white/95 dark:bg-gray-900/95 backdrop-blur-md border-t border-gray-200/50 dark:border-gray-700/50 shadow-2xl z-40 space-y-3">
      {showActions && !isSelf && (
        <div className="flex gap-3">
          <Button
            onClick={onFollowToggle}
            disabled={isFollowLoading || !onFollowToggle}
            className="flex-1 rounded-xl bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
          >
            {isFollowLoading
              ? (t('common.loading') || 'Loading...')
              : isFollowing
                ? (t('dashboard.following.unfollow') || 'Unfollow')
                : (t('dashboard.following.follow') || 'Follow')}
          </Button>
          <Button
            onClick={onMessage}
            disabled={!onMessage}
            variant="outline"
            className="flex-1 rounded-xl"
          >
            {t('dashboard.messages.message_button') || 'Message'}
          </Button>
        </div>
      )}
      <div className="flex gap-3">
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
          title={getVoteButtonTitle()}
          className={`flex-1 font-semibold py-3 text-base rounded-xl transition-all duration-300 ${
            hasVoted
              ? 'bg-gray-400 dark:bg-gray-700 text-white cursor-not-allowed'
              : canVote
              ? 'bg-gradient-to-r from-myhigh5-primary via-myhigh5-primary-dark to-indigo-600 text-white hover:shadow-lg active:scale-95'
              : 'bg-gray-400 dark:bg-gray-700 text-white cursor-not-allowed'
          }`}
        >
          {getVoteButtonText()}
        </Button>
      </div>
    </div>
  )
}

