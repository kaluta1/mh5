'use client'

import { useEffect, useState, useMemo } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  ArrowLeft,
  MapPin,
  Calendar,
  UserPlus,
  UserMinus,
  Users,
  Trophy,
  Image as ImageIcon,
  Video,
  ThumbsUp,
  Heart,
  Loader2,
  Globe,
  ChevronDown,
  ChevronUp
} from 'lucide-react'
import api from '@/lib/api'
import { followService } from '@/services/follow-service'
import Image from 'next/image'

interface UserProfile {
  id: number
  username: string
  full_name?: string
  first_name?: string
  last_name?: string
  avatar_url?: string
  bio?: string
  gender?: string
  date_of_birth?: string
  country?: string
  city?: string
  continent?: string
  region?: string
  identity_verified?: boolean
  preferred_language?: string
  followers_count?: number
  following_count?: number
  is_following?: boolean
}

interface ContestantEntry {
  id: number
  title?: string
  description?: string
  image_media_ids?: string
  video_media_ids?: string
  entry_type?: string
  round_id?: number
  season_id?: number
  registration_date?: string
  votes_count?: number
  images_count?: number
  videos_count?: number
  favorites_count?: number
  reactions_count?: number
  comments_count?: number
  author_name?: string
  author_country?: string
  author_city?: string
  author_avatar_url?: string
}

export default function UserProfilePage() {
  const { t } = useLanguage()
  const { user: currentUser, isAuthenticated, isLoading: authLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const userId = params.userId as string
  const { addToast } = useToast()

  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [entries, setEntries] = useState<ContestantEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingEntries, setLoadingEntries] = useState(true)
  const [isFollowing, setIsFollowing] = useState(false)
  const [followLoading, setFollowLoading] = useState(false)
  const [followersCount, setFollowersCount] = useState(0)
  const [selectedRound, setSelectedRound] = useState<number | 'all'>('all')
  const [expandedEntries, setExpandedEntries] = useState<Set<number>>(new Set())

  const isOwnProfile = currentUser?.id === Number(userId)

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, authLoading, router])

  useEffect(() => {
    if (!authLoading && isAuthenticated && userId) {
      loadProfile()
      loadEntries()
    }
  }, [authLoading, isAuthenticated, userId])

  const loadProfile = async () => {
    try {
      setLoading(true)
      const response = await api.get(`/api/v1/users/${userId}`)
      setProfile(response.data)
      setIsFollowing(response.data.is_following || false)
      setFollowersCount(response.data.followers_count || 0)
    } catch (err) {
      console.error('Error loading profile:', err)
      addToast(t('errors.generic') || 'Erreur lors du chargement du profil', 'error')
    } finally {
      setLoading(false)
    }
  }

  const loadEntries = async () => {
    try {
      setLoadingEntries(true)
      const response = await api.get(`/api/v1/contestants/user/${userId}/entries?limit=100`)
      setEntries(response.data)
    } catch (err) {
      console.error('Error loading entries:', err)
    } finally {
      setLoadingEntries(false)
    }
  }

  const handleFollow = async () => {
    if (followLoading || isOwnProfile) return
    setFollowLoading(true)
    try {
      if (isFollowing) {
        await followService.unfollowUser(Number(userId))
        setIsFollowing(false)
        setFollowersCount(prev => Math.max(0, prev - 1))
        addToast(t('dashboard.profile.unfollowed') || 'Vous ne suivez plus cet utilisateur', 'success')
      } else {
        await followService.followUser(Number(userId))
        setIsFollowing(true)
        setFollowersCount(prev => prev + 1)
        addToast(t('dashboard.profile.followed') || 'Vous suivez cet utilisateur', 'success')
      }
    } catch (err: any) {
      addToast(err?.response?.data?.detail || 'Erreur', 'error')
    } finally {
      setFollowLoading(false)
    }
  }

  // Group entries by round
  const rounds = useMemo(() => {
    const roundMap = new Map<number, ContestantEntry[]>()
    entries.forEach(entry => {
      const rid = entry.round_id || 0
      if (!roundMap.has(rid)) roundMap.set(rid, [])
      roundMap.get(rid)!.push(entry)
    })
    // Sort rounds descending
    return Array.from(roundMap.entries()).sort((a, b) => b[0] - a[0])
  }, [entries])

  const filteredEntries = useMemo(() => {
    if (selectedRound === 'all') return entries
    return entries.filter(e => (e.round_id || 0) === selectedRound)
  }, [entries, selectedRound])

  const toggleEntry = (id: number) => {
    setExpandedEntries(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const getAge = (dob?: string) => {
    if (!dob) return null
    const birth = new Date(dob)
    const today = new Date()
    let age = today.getFullYear() - birth.getFullYear()
    const m = today.getMonth() - birth.getMonth()
    if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--
    return age
  }

  const totalVotes = useMemo(() => entries.reduce((s, e) => s + (e.votes_count || 0), 0), [entries])
  const totalFavorites = useMemo(() => entries.reduce((s, e) => s + (e.favorites_count || 0), 0), [entries])

  if (authLoading || loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-myhigh5-primary" />
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500 dark:text-gray-400">{t('errors.user_not_found') || 'Utilisateur non trouvé'}</p>
      </div>
    )
  }

  const displayName = profile.full_name || [profile.first_name, profile.last_name].filter(Boolean).join(' ') || profile.username || 'Utilisateur'
  const age = getAge(profile.date_of_birth)

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back button */}
      <Button
        onClick={() => router.back()}
        variant="ghost"
        size="sm"
        className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        {t('common.back') || 'Retour'}
      </Button>

      {/* Profile Header Card */}
      <div className="bg-gradient-to-br from-myhigh5-primary/10 via-myhigh5-secondary/5 to-transparent dark:from-myhigh5-primary/20 dark:via-myhigh5-secondary/10 rounded-2xl border border-gray-200/50 dark:border-gray-700/50 overflow-hidden">
        {/* Cover gradient */}
        <div className="h-24 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary opacity-80" />

        <div className="px-6 pb-6 -mt-12">
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4">
            {/* Avatar */}
            <div className="flex-shrink-0">
              {profile.avatar_url ? (
                <div className="w-24 h-24 rounded-full overflow-hidden border-4 border-white dark:border-gray-800 shadow-lg">
                  <Image
                    src={profile.avatar_url}
                    alt={displayName}
                    width={96}
                    height={96}
                    className="w-full h-full object-cover"
                  />
                </div>
              ) : (
                <div className="w-24 h-24 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center border-4 border-white dark:border-gray-800 shadow-lg">
                  <span className="text-3xl font-bold text-white">
                    {displayName.charAt(0).toUpperCase()}
                  </span>
                </div>
              )}
            </div>

            {/* Name & Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  {displayName}
                </h1>
                {profile.identity_verified && (
                  <Badge className="bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20 text-xs">
                    {t('dashboard.profile.verified') || 'Vérifié'}
                  </Badge>
                )}
              </div>
              {profile.username && (
                <p className="text-sm text-gray-500 dark:text-gray-400">@{profile.username}</p>
              )}
              <div className="flex items-center gap-4 mt-1 text-sm text-gray-600 dark:text-gray-400 flex-wrap">
                {(profile.country || profile.city) && (
                  <span className="flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5" />
                    {[profile.city, profile.country].filter(Boolean).join(', ')}
                  </span>
                )}
                {profile.continent && (
                  <span className="flex items-center gap-1">
                    <Globe className="w-3.5 h-3.5" />
                    {profile.continent}
                  </span>
                )}
                {age && (
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3.5 h-3.5" />
                    {age} {t('dashboard.profile.years') || 'ans'}
                  </span>
                )}
              </div>
            </div>

            {/* Follow button */}
            {!isOwnProfile && (
              <Button
                onClick={handleFollow}
                disabled={followLoading}
                variant={isFollowing ? 'outline' : 'default'}
                className={isFollowing
                  ? 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:border-red-400 hover:text-red-500'
                  : 'bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white'
                }
              >
                {followLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : isFollowing ? (
                  <><UserMinus className="w-4 h-4 mr-2" />{t('dashboard.profile.unfollow') || 'Ne plus suivre'}</>
                ) : (
                  <><UserPlus className="w-4 h-4 mr-2" />{t('dashboard.profile.follow') || 'Suivre'}</>
                )}
              </Button>
            )}
          </div>

          {/* Bio */}
          {profile.bio && (
            <p className="mt-4 text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
              {profile.bio}
            </p>
          )}

          {/* Stats bar */}
          <div className="flex items-center gap-6 mt-4 pt-4 border-t border-gray-200/50 dark:border-gray-700/50">
            <div className="text-center">
              <p className="text-lg font-bold text-gray-900 dark:text-white">{entries.length}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.profile.participations') || 'Participations'}</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-gray-900 dark:text-white">{totalVotes}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.profile.total_votes') || 'Votes'}</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-gray-900 dark:text-white">{totalFavorites}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.profile.total_favorites') || 'Favoris'}</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-gray-900 dark:text-white">{followersCount}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.profile.followers') || 'Abonnés'}</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-gray-900 dark:text-white">{profile.following_count || 0}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.profile.following') || 'Abonnements'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Entries Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Trophy className="w-5 h-5 text-myhigh5-primary" />
            {t('dashboard.profile.contestants') || 'Participations'}
          </h2>

          {/* Round filter */}
          {rounds.length > 1 && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelectedRound('all')}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  selectedRound === 'all'
                    ? 'bg-myhigh5-primary text-white'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                }`}
              >
                {t('dashboard.profile.all_rounds') || 'Tous'}
              </button>
              {rounds.map(([roundId]) => (
                <button
                  key={roundId}
                  onClick={() => setSelectedRound(roundId)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                    selectedRound === roundId
                      ? 'bg-myhigh5-primary text-white'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                  }`}
                >
                  Round {roundId || '?'}
                </button>
              ))}
            </div>
          )}
        </div>

        {loadingEntries ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-myhigh5-primary" />
          </div>
        ) : filteredEntries.length === 0 ? (
          <div className="text-center py-12 bg-white dark:bg-gray-800/50 rounded-xl border border-gray-200/50 dark:border-gray-700/50">
            <Trophy className="w-12 h-12 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
            <p className="text-gray-500 dark:text-gray-400">
              {t('dashboard.profile.no_entries') || 'Aucune participation pour le moment'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredEntries.map((entry) => {
              const isExpanded = expandedEntries.has(entry.id)
              let images: string[] = []
              try { images = entry.image_media_ids ? JSON.parse(entry.image_media_ids) : [] } catch { images = [] }
              let videos: string[] = []
              try { videos = entry.video_media_ids ? JSON.parse(entry.video_media_ids) : [] } catch { videos = [] }
              const thumbnail = images[0] || null

              return (
                <div
                  key={entry.id}
                  className="bg-white dark:bg-gray-800/50 rounded-xl border border-gray-200/50 dark:border-gray-700/50 overflow-hidden hover:border-myhigh5-primary/30 transition-all"
                >
                  {/* Entry header */}
                  <button
                    onClick={() => toggleEntry(entry.id)}
                    className="w-full flex items-center gap-4 p-4 text-left"
                  >
                    {/* Thumbnail */}
                    {thumbnail ? (
                      <div className="w-14 h-14 rounded-lg overflow-hidden flex-shrink-0 bg-gray-100 dark:bg-gray-700">
                        <img src={thumbnail} alt="" className="w-full h-full object-cover" />
                      </div>
                    ) : (
                      <div className="w-14 h-14 rounded-lg flex-shrink-0 bg-gradient-to-br from-myhigh5-primary/20 to-myhigh5-secondary/20 flex items-center justify-center">
                        <Trophy className="w-6 h-6 text-myhigh5-primary/60" />
                      </div>
                    )}

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                          {entry.title || 'Sans titre'}
                        </h3>
                        <Badge className={`text-[10px] px-1.5 py-0 ${
                          entry.entry_type === 'nomination'
                            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                            : 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20'
                        }`}>
                          {entry.entry_type === 'nomination' ? 'Nomination' : 'Participation'}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {entry.round_id && <span>Round {entry.round_id}</span>}
                        {entry.registration_date && (
                          <span>{new Date(entry.registration_date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                        )}
                      </div>
                    </div>

                    {/* Stats mini */}
                    <div className="hidden sm:flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                      <span className="flex items-center gap-1"><ThumbsUp className="w-3.5 h-3.5" />{entry.votes_count || 0}</span>
                      <span className="flex items-center gap-1"><Heart className="w-3.5 h-3.5" />{entry.favorites_count || 0}</span>
                      <span className="flex items-center gap-1"><ImageIcon className="w-3.5 h-3.5" />{images.length}</span>
                      {videos.length > 0 && <span className="flex items-center gap-1"><Video className="w-3.5 h-3.5" />{videos.length}</span>}
                    </div>

                    {/* Expand icon */}
                    {isExpanded ? (
                      <ChevronUp className="w-5 h-5 text-gray-400 flex-shrink-0" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-gray-400 flex-shrink-0" />
                    )}
                  </button>

                  {/* Expanded content */}
                  {isExpanded && (
                    <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-700/50 pt-3 space-y-3">
                      {entry.description && (
                        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                          {entry.description}
                        </p>
                      )}

                      {/* Images grid */}
                      {images.length > 0 && (
                        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                          {images.map((url, idx) => (
                            <div key={idx} className="aspect-square rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-700">
                              <img src={url} alt="" className="w-full h-full object-cover" />
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Videos */}
                      {videos.length > 0 && (
                        <div className="space-y-2">
                          {videos.map((url, idx) => (
                            <a
                              key={idx}
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-2 text-sm text-myhigh5-primary hover:underline"
                            >
                              <Video className="w-4 h-4" />
                              {url.length > 60 ? url.substring(0, 60) + '...' : url}
                            </a>
                          ))}
                        </div>
                      )}

                      {/* Stats détaillés (mobile) */}
                      <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 sm:hidden">
                        <span className="flex items-center gap-1"><ThumbsUp className="w-3.5 h-3.5" />{entry.votes_count || 0} votes</span>
                        <span className="flex items-center gap-1"><Heart className="w-3.5 h-3.5" />{entry.favorites_count || 0} favoris</span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
