'use client'

import { Badge } from '@/components/ui/badge'
import { ContestantCard } from './contestant-card'
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
  avatar: string
  participationTitle?: string
  description: string
  votes: number
  rank?: number
  imagesCount: number
  videosCount: number
  canVote: boolean
  hasVoted: boolean
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

  const getRankBadgeColor = (rank?: number) => {
    if (!rank) return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
    if (rank === 1) return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700'
    if (rank === 2) return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600'
    if (rank === 3) return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700'
    return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700'
  }

  const getRankText = (rank?: number) => {
    if (!rank) return ''
    if (language === 'fr') {
      if (rank === 1) return '1er'
      if (rank === 2) return '2ème'
      if (rank === 3) return '3ème'
      return `${rank}ème`
    } else if (language === 'es') {
      if (rank === 1) return '1º'
      if (rank === 2) return '2º'
      if (rank === 3) return '3º'
      return `${rank}º`
    } else if (language === 'de') {
      if (rank === 1) return '1.'
      if (rank === 2) return '2.'
      if (rank === 3) return '3.'
      return `${rank}.`
    } else {
      if (rank === 1) return '1st'
      if (rank === 2) return '2nd'
      if (rank === 3) return '3rd'
      return `${rank}th`
    }
  }

  const getRankIcon = (rank?: number) => {
    if (!rank) return null
    if (rank === 1) return '🥇'
    if (rank === 2) return '🥈'
    if (rank === 3) return '🥉'
    return `#${rank}`
  }

  if (contestants.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="flex flex-col items-center gap-3">
          <p className="text-5xl mb-2">🏆</p>
          <p className="text-lg font-semibold text-gray-700 dark:text-gray-300">
            {searchQuery 
              ? t('dashboard.contests.no_contestants_found') || 'Aucun participant trouvé'
              : t('dashboard.contests.no_contestants') || 'Aucun participant pour le moment'}
          </p>
          {!searchQuery && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.contests.participate') || 'Soyez le premier à participer !'}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4 max-w-2xl mx-auto lg:mx-0">
      {contestants.map((contestant) => (
        <div key={contestant.id} className="relative">
          {/* Rank Badge */}
          {contestant.rank && (
            <div className="absolute -top-2 -left-2 z-10">
              <Badge 
                className={`${getRankBadgeColor(contestant.rank)} border-2 font-bold text-sm px-3 py-1.5 shadow-lg flex items-center gap-1`}
              >
                <span>{getRankIcon(contestant.rank)}</span>
                <span className="hidden sm:inline">
                  {getRankText(contestant.rank)}
                </span>
              </Badge>
            </div>
          )}
          
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
            onReport={() => onReport(contestant.id)}
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
            onHoverVotes={() => onHoverVotes(contestant.id, contestant.votesList || [])}
            onHoverReactions={() => onHoverReactions(contestant.id, contestant.reactionsList || {})}
            onHoverFavorites={() => onHoverFavorites(contestant.id, contestant.favoritesList || [])}
          />
        </div>
      ))}
    </div>
  )
}

