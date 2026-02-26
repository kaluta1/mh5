'use client'

import React from 'react'
import { ContestCard } from './contest-card'
import { Contest } from '@/services/contest-service'
import { useLanguage } from '@/contexts/language-context'

interface ContestsGridProps {
  contests: Contest[]
  favorites: string[]
  onToggleFavorite: (contestId: string) => void
  onViewContestants: (contestId: string) => void
  onParticipate: (contestId: string) => void
  isLoading?: boolean
  userGender?: 'male' | 'female' | 'other' | 'prefer_not_to_say' | null
  canParticipate?: boolean
  isKycVerified?: boolean
}

export function ContestsGrid({
  contests,
  favorites,
  onToggleFavorite,
  onViewContestants,
  onParticipate,
  isLoading = false,
  userGender,
  canParticipate = true,
  isKycVerified = false
}: ContestsGridProps) {
  const { t } = useLanguage()

  // Removed debug logs for performance

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="aspect-[4/5] bg-gray-200 dark:bg-gray-700 rounded-3xl animate-pulse"
          />
        ))}
      </div>
    )
  }

  if (contests.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-lg text-gray-500 dark:text-gray-400">
          {t('dashboard.contests.no_contests')}
        </p>
      </div>
    )
  }

  // Identifier le contest le plus suivi (premier de la liste après tri)
  const featuredContestId = contests.length > 0 ? contests[0].id : null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8 auto-rows-fr">
      {contests.map((contest, index) => (
        <ContestCard
          key={String(contest.id)}
          id={String(contest.id)}
          title={contest.title}
          coverImage={contest.coverImage}
          startDate={contest.startDate}
          status={contest.status}
          received={contest.received}
          contestants={contest.contestants}
          likes={contest.likes}
          comments={contest.comments}
          isOpen={contest.isOpen}
          isFeatured={index === 0 && String(contest.id) === String(featuredContestId)}
          genderRestriction={contest.genderRestriction}
          participationStartDate={contest.participationStartDate}
          participationEndDate={contest.participationEndDate}
          votingStartDate={contest.votingStartDate}
          isFavorite={favorites.includes(String(contest.id))}
          userGender={userGender}
          canParticipate={canParticipate}
          isKycVerified={isKycVerified}
          topContestants={contest.topContestants}
          // Verification requirements
          requiresKyc={contest.requiresKyc}
          verificationType={contest.verificationType}
          participantType={contest.participantType}
          requiresVisualVerification={contest.requiresVisualVerification}
          requiresVoiceVerification={contest.requiresVoiceVerification}
          requiresBrandVerification={contest.requiresBrandVerification}
          requiresContentVerification={contest.requiresContentVerification}
          minAge={contest.minAge}
          maxAge={contest.maxAge}
          onToggleFavorite={() => onToggleFavorite(String(contest.id))}
          onViewContestants={() => onViewContestants(String(contest.id))}
          onParticipate={() => onParticipate(String(contest.id))}
          onOpenDetails={() => onViewContestants(String(contest.id))}
        />
      ))}
    </div>
  )
}
