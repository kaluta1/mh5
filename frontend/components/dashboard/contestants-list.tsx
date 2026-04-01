'use client'

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ContestantCard } from './contestant-card'
import { ReportContestantDialog } from './report-contestant-dialog'
import { useLanguage } from '@/contexts/language-context'

interface Media {
  id: string
  type: 'image' | 'video'
  url: string
  thumbnail?: string
}

interface Contestant {
  id: string
  userId?: number
  name: string
  country?: string
  city?: string
  continent?: string
  region?: string
  avatar: string
  participationTitle?: string
  description: string
  votes: number
  rank?: number
  imagesCount: number
  videosCount: number
  canVote: boolean
  hasVoted: boolean
  hasReported?: boolean
  isVotingOpenForRound?: boolean
  voteRestrictionReason?: string | null
  media: Media[]
  comments: number
  reactions?: number
  favorites?: number
  shares?: number
  isFavorite: boolean
  votesList?: Array<{
    id?: number
    user_id: number
    username?: string
    full_name?: string
    avatar_url?: string
    points: number
    vote_date: string
    contest_id?: number
    season_id?: number
  }>
  commentsList?: Array<{
    id: number
    user_id: number
    username?: string
    full_name?: string
    avatar_url?: string
    content: string
    created_at: string
    parent_id?: number | null
  }>
  reactionsList?: {
    [key: string]: Array<{
      id?: number
      user_id: number
      username?: string
      full_name?: string
      avatar_url?: string
      reaction_type: string
    }>
  }
  favoritesList?: Array<{
    id?: number
    user_id: number
    username?: string
    full_name?: string
    avatar_url?: string
    position?: number
    added_date: string
  }>
  sharesList?: Array<{
    id: number
    user_id?: number
    username?: string
    full_name?: string
    avatar_url?: string
    platform?: string
    share_link: string
    created_at: string
  }>
  season?: {
    id: number
    title: string
    level: string
  }
}

interface ContestantsListProps {
  contestants: Contestant[]
  contestId: string
  currentUserId?: number
  favorites: string[]
  searchQuery?: string
  onToggleFavorite: (contestantId: string) => void
  onViewDetails: (contestantId: string) => void
  onVote: (contestantId: string) => void
  onComment: (contestantId: string) => void
  onShare: (contestantId: string) => void
  onReport: (contestantId: string) => void
  onEdit: (contestantId: string) => void
  onDelete: (contestantId: string) => void
  onHoverAuthor: (contestantId: string, data: any) => void
  onHoverEnd: () => void
  onHoverDescription: (contestantId: string, description: string) => void
  onHoverVotes: (contestantId: string, votes: any[]) => void
  onHoverReactions: (contestantId: string, reactions: any) => void
  onHoverFavorites: (contestantId: string, favorites: any[]) => void
}

export function ContestantsList({
  contestants,
  contestId,
  currentUserId,
  favorites,
  searchQuery = '',
  onToggleFavorite,
  onViewDetails,
  onVote,
  onComment,
  onShare,
  onReport,
  onEdit,
  onDelete,
  onHoverAuthor,
  onHoverEnd,
  onHoverDescription,
  onHoverVotes,
  onHoverReactions,
  onHoverFavorites
}: ContestantsListProps) {
  const { t, language } = useLanguage()
  const [reportDialogOpen, setReportDialogOpen] = useState(false)
  const [selectedContestantId, setSelectedContestantId] = useState<number | null>(null)
  const [selectedContestantTitle, setSelectedContestantTitle] = useState<string>('')

  const handleReportClick = (contestantId: string) => {
    const contestant = contestants.find(c => c.id === contestantId)
    if (contestant) {
      setSelectedContestantId(parseInt(contestantId))
      setSelectedContestantTitle(contestant.participationTitle || contestant.name)
      setReportDialogOpen(true)
    }
    // Appeler aussi le callback original si nécessaire
    onReport(contestantId)
  }







  if (contestants.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="flex flex-col items-center gap-4 bg-white dark:bg-gray-800/50 rounded-xl border border-gray-200/50 dark:border-gray-700/50 p-8 backdrop-blur-sm">
          <div className="w-20 h-20 rounded-full bg-gradient-to-br from-myhigh5-primary/20 to-myhigh5-secondary/20 flex items-center justify-center mb-2">
            <p className="text-4xl">🏆</p>
          </div>
          <p className="text-lg font-semibold text-gray-700 dark:text-gray-300">
            {searchQuery 
              ? t('dashboard.contests.no_contestants_found') || 'Aucun participant trouvé'
              : t('dashboard.contests.no_contestants') || 'Aucun participant pour le moment'}
          </p>
          {!searchQuery && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.contests.participate') || 'Soyez le premier à concourir !'}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {contestants.map((contestant) => (
        <div key={contestant.id}>
          
          <ContestantCard
            id={contestant.id}
            userId={contestant.userId}
            currentUserId={currentUserId}
            contestId={contestId}
            name={contestant.name}
            country={contestant.country}
            city={contestant.city}
            avatar={contestant.avatar}
            participationTitle={contestant.participationTitle}
            votes={contestant.votes}
            rank={contestant.rank}
            imagesCount={contestant.imagesCount}
            videosCount={contestant.videosCount}
            canVote={contestant.canVote}
            hasVoted={contestant.hasVoted}
            hasReported={contestant.hasReported}
            isVotingOpenForRound={contestant.isVotingOpenForRound}
            voteRestrictionReason={contestant.voteRestrictionReason}
            isFavorite={favorites.includes(contestant.id)}
            media={contestant.media}
            description={contestant.description}
            comments={contestant.comments}
            reactions={contestant.reactions}
            favorites={contestant.favorites}
            votesList={contestant.votesList}
            reactionsList={contestant.reactionsList}
            favoritesList={contestant.favoritesList}
            onToggleFavorite={() => onToggleFavorite(contestant.id)}
            onViewDetails={() => onViewDetails(contestant.id)}
            onVote={() => onVote(contestant.id)}
            onComment={() => onComment(contestant.id)}
            onShare={() => onShare(contestant.id)}
            onReport={() => handleReportClick(contestant.id)}
            onEdit={() => onEdit(contestant.id)}
            onDelete={() => onDelete(contestant.id)}
            onHoverAuthor={() => onHoverAuthor(contestant.id, {
              name: contestant.name,
              avatar: contestant.avatar,
              country: contestant.country,
              city: contestant.city,
              rank: contestant.rank
            })}
            onHoverEnd={onHoverEnd}
            onHoverDescription={() => onHoverDescription(contestant.id, contestant.description)}
            onHoverVotes={() => {
              // Seul l'auteur peut voir la liste des votes
              if (currentUserId === contestant.userId) {
                onHoverVotes(contestant.id, contestant.votesList || [])
              }
            }}
            onHoverReactions={() => onHoverReactions(contestant.id, contestant.reactionsList || {})}
            onHoverFavorites={() => {
              // Seul l'auteur peut voir la liste des favoris
              if (currentUserId === contestant.userId) {
                onHoverFavorites(contestant.id, contestant.favoritesList || [])
              }
            }}
          />
        </div>
      ))}
      
      {/* Dialog de signalement */}
      {selectedContestantId !== null && (
        <ReportContestantDialog
          open={reportDialogOpen}
          onOpenChange={setReportDialogOpen}
          contestantId={selectedContestantId}
          contestId={parseInt(contestId)}
          contestantTitle={selectedContestantTitle}
        />
      )}
    </div>
  )
}

