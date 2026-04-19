'use client'

import { ThumbsUp, Image as ImageIcon, Video, Trophy, MessageCircle, Heart, Share2 } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { formatOrdinalRank } from '@/lib/date-utils'

interface ContestantStatsBarProps {
  votes: number
  images: number
  videos: number
  rank?: number
  comments?: number
  reactions?: number
  favorites?: number
  shares?: number
  onVotesClick?: () => void
  onCommentsClick?: () => void
  onReactionsClick?: () => void
  onFavoritesClick?: () => void
  onSharesClick?: () => void
}

export function ContestantStatsBar({
  votes,
  images,
  videos,
  rank,
  comments = 0,
  reactions = 0,
  favorites = 0,
  shares = 0,
  onVotesClick,
  onCommentsClick,
  onReactionsClick,
  onFavoritesClick,
  onSharesClick
}: ContestantStatsBarProps) {
  const { t, language } = useLanguage()

  const baseItems = [
    {
      key: 'votes',
      value: votes,
      label: t('dashboard.contests.votes') || 'Votes',
      icon: <ThumbsUp className="w-4 h-4 text-white" />,
      bg: 'bg-blue-500'
    },
    {
      key: 'images',
      value: images,
      label: t('contestant_detail.images') || t('dashboard.contests.images') || 'Images',
      icon: <ImageIcon className="w-4 h-4 text-white" />,
      bg: 'bg-purple-600'
    },
    {
      key: 'videos',
      value: videos,
      label: t('contestant_detail.videos') || t('dashboard.contests.videos') || 'Vidéos',
      icon: <Video className="w-4 h-4 text-white" />,
      bg: 'bg-red-500'
    },
    {
      key: 'comments',
      value: comments,
      label: t('contestant_detail.comments') || t('dashboard.contests.comments') || 'Commentaires',
      icon: <MessageCircle className="w-4 h-4 text-white" />,
      bg: 'bg-emerald-600'
    },
    {
      key: 'reactions',
      value: reactions,
      label: t('dashboard.contests.reactions') || 'Réactions',
      icon: <Heart className="w-4 h-4 text-white" />,
      bg: 'bg-pink-600'
    },
    {
      key: 'favorites',
      value: favorites,
      label: t('dashboard.contests.favorites') || 'Favoris',
      icon: <Heart className="w-4 h-4 text-white" />,
      bg: 'bg-rose-500'
    },
    {
      key: 'shares',
      value: shares,
      label: t('dashboard.contests.shares') || 'Partages',
      icon: <Share2 className="w-4 h-4 text-white" />,
      bg: 'bg-indigo-600'
    }
  ]

  const items =
    rank != null && rank > 0
      ? [
          {
            key: 'rank',
            value: formatOrdinalRank(rank, language),
            label: t('dashboard.contests.rank') || 'Rank',
            icon: <Trophy className="w-4 h-4 text-white" />,
            bg: 'bg-amber-500',
          },
          ...baseItems,
        ]
      : baseItems

  const clickHandlers: Record<string, (() => void) | undefined> = {
    votes: onVotesClick,
    comments: onCommentsClick,
    reactions: onReactionsClick,
    favorites: onFavoritesClick,
    shares: onSharesClick
  }

  return (
    <div className="bg-[#0f192a] dark:bg-[#0b1220] border-b border-white/5 shadow-lg">
      <div className="w-full overflow-x-auto">
        <div className="container mx-auto px-4 md:px-6 lg:px-8 py-4">
          <div className="flex items-center gap-3 md:gap-4 min-w-max">
          {items.map((item) => {
            const displayValue = item.value
            const onClick = clickHandlers[item.key] || (() => {})
            const clickable = !!clickHandlers[item.key]
            return (
              <div
                key={item.key}
                className={`flex items-center gap-2 px-3 py-2 rounded-2xl bg-white/5 border border-white/10 shadow-sm min-w-[110px] justify-start ${
                  clickable ? 'cursor-pointer hover:border-white/20 transition-all duration-150' : ''
                }`}
                onClick={clickable ? onClick : undefined}
              >
                <div className={`w-9 h-9 rounded-full flex items-center justify-center ${item.bg} shadow-inner`}>
                  {item.icon}
                </div>
                <div className="leading-tight">
                  <p className="text-white font-bold text-lg">{displayValue}</p>
                  <p className="text-xs text-white/70">{item.label}</p>
                </div>
              </div>
            )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

