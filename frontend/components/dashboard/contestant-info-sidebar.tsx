'use client'

import { useLanguage } from '@/contexts/language-context'
import { ReactionsButton } from './reactions-button'
import { Button } from '@/components/ui/button'
import { ThumbsUp, Heart } from 'lucide-react'
import Image from 'next/image'
import { ReactionDetails } from '@/services/reactions-service'

interface ContestantInfoSidebarProps {
  candidateTitle?: string
  registrationDate?: string
  followersCount?: number | null
  isAuthor: boolean
  contestantId: number
  selectedReaction: string | null
  onReactionSelect: (reactionType: string) => void
  reactionDetails: ReactionDetails | null
  voters: Array<{ id?: number; user_id: number; username?: string; full_name?: string; avatar_url?: string; vote_date?: string; contest_id?: number; season_id?: number }>
  hasVoted: boolean
  canVote: boolean
  isVoting: boolean
  onVote: () => void
  voteRestrictionReason?: string | null
  showActions?: boolean
  isSelf?: boolean
  isFollowing?: boolean
  isFollowLoading?: boolean
  onFollowToggle?: () => void
  onMessage?: () => void
}

export function ContestantInfoSidebar({
  candidateTitle,
  registrationDate,
  followersCount = null,
  isAuthor,
  contestantId,
  selectedReaction,
  onReactionSelect,
  reactionDetails,
  voters,
  hasVoted,
  canVote,
  isVoting,
  onVote,
  voteRestrictionReason,
  showActions = false,
  isSelf = false,
  isFollowing = false,
  isFollowLoading = false,
  onFollowToggle,
  onMessage
}: ContestantInfoSidebarProps) {
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
    <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-md rounded-3xl p-6 shadow-xl border border-gray-100 dark:border-gray-700/50 sticky top-6 space-y-6 transition-all duration-300 hover:shadow-2xl">
      {/* Candidate Info */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-wider">
            {t('contestant_detail.candidate_info')}
          </h3>
          
        </div>

        {candidateTitle && (
          <div className="rounded-2xl border border-emerald-100 dark:border-emerald-900/40 bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-950/30 dark:to-teal-900/30 p-4 shadow-inner">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('contestant_detail.title')}</p>
            <p className="text-base font-semibold text-gray-900 dark:text-white">{candidateTitle}</p>
          </div>
        )}

        {registrationDate && (
          <div className="rounded-2xl border border-amber-100 dark:border-amber-900/40 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-900/30 p-4 shadow-inner flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('contestant_detail.registered_on')}</p>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">
                {new Date(registrationDate).toLocaleDateString('fr-FR')}
              </p>
            </div>
            <div className="text-lg">📅</div>
          </div>
        )}

        {followersCount !== null && (
          <div className="rounded-2xl border border-blue-100 dark:border-blue-900/40 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-900/30 p-4 shadow-inner flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                {t('dashboard.following.followers') || 'Followers'}
              </p>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">
                {followersCount}
              </p>
            </div>
            <div className="text-lg">👥</div>
          </div>
        )}
      </div>

      <div className="border-t border-gray-200/40 dark:border-gray-700/40"></div>

      {/* Follow / Message Actions */}
      {showActions && !isSelf && (
        <div className="space-y-2">
          <Button
            onClick={onFollowToggle}
            disabled={isFollowLoading || !onFollowToggle}
            className="w-full rounded-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
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
            className="w-full rounded-full"
          >
            {t('dashboard.messages.message_button') || 'Message'}
          </Button>
        </div>
      )}

      <div className="border-t border-gray-200/40 dark:border-gray-700/40"></div>

      {/* Reactions Section - Only visible to author */}
      {isAuthor && (
        <>
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4 uppercase tracking-wider">
              {t('dashboard.contests.reactions') || 'Réactions'}
            </h3>
            <ReactionsButton
              contestantId={contestantId}
              selectedReaction={selectedReaction}
              onReactionSelect={onReactionSelect}
            />
            
            {/* Reaction Stats with Users - Improved Design */}
            {reactionDetails && (
              <div className="mt-4 space-y-3">
                {/* Users who liked */}
                {reactionDetails.reactions_by_type?.like && reactionDetails.reactions_by_type.like.length > 0 && (
                  <div className="bg-gradient-to-r from-blue-50 to-cyan-50 dark:from-blue-950/40 dark:to-cyan-950/40 rounded-xl p-4 border border-blue-200/50 dark:border-blue-800/50 shadow-sm">
                    <div className="flex items-center gap-2 mb-2">
                      <ThumbsUp className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                      <span className="text-sm font-semibold text-blue-900 dark:text-blue-100">
                        {reactionDetails.reactions_by_type.like.length}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {reactionDetails.reactions_by_type.like.slice(0, 5).map((user: any) => (
                        <div key={user.user_id} className="relative group">
                          {user.avatar_url ? (
                            <Image
                              src={user.avatar_url}
                              alt={user.full_name || user.username || ''}
                              width={32}
                              height={32}
                              className="rounded-lg border-2 border-blue-500 cursor-pointer hover:scale-110 transition-transform object-cover"
                              title={user.full_name || user.username || ''}
                            />
                          ) : (
                            <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-900 flex items-center justify-center text-xs font-semibold border-2 border-blue-500 cursor-pointer hover:scale-110 transition-transform text-blue-700 dark:text-blue-300">
                              {(user.full_name || user.username || 'U')[0].toUpperCase()}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Users who loved */}
                {reactionDetails.reactions_by_type?.love && reactionDetails.reactions_by_type.love.length > 0 && (
                  <div className="bg-gradient-to-r from-red-50 to-pink-50 dark:from-red-950/40 dark:to-pink-950/40 rounded-xl p-4 border border-red-200/50 dark:border-red-800/50 shadow-sm">
                    <div className="flex items-center gap-2 mb-2">
                      <Heart className="w-4 h-4 text-red-600 dark:text-red-400 fill-current" />
                      <span className="text-sm font-semibold text-red-900 dark:text-red-100">
                        {reactionDetails.reactions_by_type.love.length}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {reactionDetails.reactions_by_type.love.slice(0, 5).map((user: any) => (
                        <div key={user.user_id} className="relative group">
                          {user.avatar_url ? (
                            <Image
                              src={user.avatar_url}
                              alt={user.full_name || user.username || ''}
                              width={32}
                              height={32}
                              className="rounded-lg border-2 border-red-500 cursor-pointer hover:scale-110 transition-transform object-cover"
                              title={user.full_name || user.username || ''}
                            />
                          ) : (
                            <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-900 flex items-center justify-center text-xs font-semibold border-2 border-red-500 cursor-pointer hover:scale-110 transition-transform text-red-700 dark:text-red-300">
                              {(user.full_name || user.username || 'U')[0].toUpperCase()}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Vote History - Only visible to author */}
          {voters.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-200/50 dark:border-gray-700/50">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4 uppercase tracking-wider">
                {t('contestant_detail.vote_history') || 'Historique des votes'}
              </h4>
              <div className="flex items-center gap-2 flex-wrap">
                {voters.slice(0, 10).map((voter) => (
                  <div key={voter.user_id} className="relative group">
                    {voter.avatar_url ? (
                      <Image
                        src={voter.avatar_url}
                        alt={voter.full_name || voter.username || ''}
                        width={32}
                        height={32}
                        className="rounded-lg border-2 border-myhigh5-primary cursor-pointer hover:scale-110 transition-transform object-cover"
                        title={voter.full_name || voter.username || ''}
                      />
                    ) : (
                      <div className="w-8 h-8 rounded-lg bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center text-xs font-semibold border-2 border-myhigh5-primary cursor-pointer hover:scale-110 transition-transform text-myhigh5-primary dark:text-myhigh5-secondary">
                        {(voter.full_name || voter.username || 'V')[0].toUpperCase()}
                      </div>
                    )}
                  </div>
                ))}
                {voters.length > 10 && (
                  <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-xs font-semibold border-2 border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400">
                    +{voters.length - 10}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      <div className="border-t border-gray-200/50 dark:border-gray-700/50"></div>

      {/* Desktop Vote Button */}
      <Button
        onClick={onVote}
        disabled={!canVote || isVoting || hasVoted}
        className={`w-full hidden md:block font-semibold py-3 text-sm rounded-xl hover:shadow-xl transition-all duration-300 ${
          hasVoted
            ? 'bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed'
            : 'bg-gradient-to-r from-myhigh5-primary via-myhigh5-primary-dark to-indigo-600 text-white hover:scale-[1.02] active:scale-[0.98]'
        }`}
      >
        {isVoting ? t('contestant_detail.voting') : hasVoted ? (t('contestant_detail.voted') || 'Voted') : t('contestant_detail.vote')}
      </Button>
    </div>
  )
}

