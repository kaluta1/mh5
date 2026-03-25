'use client'

import { Globe, MapPin, Compass, Heart, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'

export interface ContestantHeaderProps {
  author_name?: string
  author_country?: string
  author_city?: string
  author_continent?: string
  author_avatar_url?: string
  titlePrefix?: string
  votes_count?: number
  followersCount?: number | null
  rank?: number
  total_participants?: number
  isFavorite: boolean
  coverImage?: string
  onBack: () => void
  onFavoriteToggle: () => void
  showActions?: boolean
  isSelf?: boolean
  isFollowing?: boolean
  isFollowLoading?: boolean
  onFollowToggle?: () => void
  onMessage?: () => void
}

export function ContestantHeader({
  author_name,
  author_country,
  author_city,
  author_continent,
  author_avatar_url,
  titlePrefix = 'Contestant',
  votes_count = 0,
  followersCount = null,
  rank,
  total_participants,
  isFavorite,
  coverImage,
  onBack,
  onFavoriteToggle,
  showActions = false,
  isSelf = false,
  isFollowing = false,
  isFollowLoading = false,
  onFollowToggle,
  onMessage
}: ContestantHeaderProps) {
  const { t } = useLanguage()

  return (
    <div className="relative h-64 md:h-80 lg:h-96 bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary-dark to-indigo-600 overflow-hidden">
      {/* Cover Image */}
      {coverImage ? (
        <img
          src={coverImage}
          alt="Cover"
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : null}
      <div className="absolute inset-0 bg-black/40"></div>

      {/* Navigation */}
      <div className="absolute top-0 left-0 right-0 p-4 md:p-6 flex items-center justify-between z-10">
        <Button
          onClick={onBack}
          variant="ghost"
          className="bg-white/10 hover:bg-white/20 backdrop-blur-md text-white border border-white/20 rounded-xl transition-all duration-200"
        >
          <ArrowLeft className="w-5 h-5 mr-2" />
          {t('common.back')}
        </Button>

        <Button
          onClick={onFavoriteToggle}
          variant="ghost"
          className="bg-white/10 hover:bg-white/20 backdrop-blur-md text-white border border-white/20 rounded-xl transition-all duration-200"
        >
          <Heart className={`w-5 h-5 transition-all duration-200 ${isFavorite ? 'fill-current text-red-400 scale-110' : ''}`} />
        </Button>
      </div>

      {/* Content */}
      <div className="absolute bottom-0 left-0 right-0 p-4 md:p-6 z-10">
        <div className="flex gap-4 items-end">
          {/* Avatar */}
          {author_avatar_url ? (
            <img
              src={author_avatar_url}
              alt={author_name}
              className="w-20 h-20 md:w-24 md:h-24 rounded-full border-4 border-white object-cover"
            />
          ) : (
            <div className="w-20 h-20 md:w-24 md:h-24 rounded-full border-4 border-white bg-gradient-to-br from-myhigh5-primary to-myhigh5-primary-dark flex items-center justify-center text-white font-bold text-2xl">
              {author_name?.charAt(0).toUpperCase() || '?'}
            </div>
          )}

          {/* Info */}
          <div className="flex-1 pb-2">
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
              {titlePrefix}: {author_name || titlePrefix}
            </h1>

            {/* Stats */}
            <div className="flex flex-wrap gap-4 text-white/90 text-sm md:text-base">
              <div>⭐ {votes_count} {t('contestant_detail.votes')}</div>
              {followersCount !== null && (
                <div>👥 {followersCount} {t('dashboard.following.followers') || 'Followers'}</div>
              )}
              {rank && total_participants && (
                <div>#{rank}/{total_participants}</div>
              )}
            </div>

            {/* Actions */}
            {showActions && !isSelf && (
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  onClick={onFollowToggle}
                  disabled={isFollowLoading || !onFollowToggle}
                  className="bg-white text-gray-900 hover:bg-gray-100 rounded-full px-4 py-2 text-sm font-semibold"
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
                  variant="ghost"
                  className="bg-white/10 hover:bg-white/20 text-white border border-white/30 rounded-full px-4 py-2 text-sm font-semibold"
                >
                  {t('dashboard.messages.message_button') || 'Message'}
                </Button>
              </div>
            )}

            {/* Location Info */}
            <div className="mt-3 space-y-1">
              {author_country && (
                <p className="text-lg md:text-xl text-white/90 flex items-center justify-center md:justify-start gap-2">
                  <Globe className="w-5 h-5" /> {author_country}
                </p>
              )}
              {author_city && (
                <p className="text-sm md:text-base text-white/80 flex items-center justify-center md:justify-start gap-2">
                  <MapPin className="w-4 h-4" /> {author_city}
                </p>
              )}
              {author_continent && (
                <p className="text-sm md:text-base text-white/70 flex items-center justify-center md:justify-start gap-2">
                  <Compass className="w-4 h-4" /> {author_continent}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
