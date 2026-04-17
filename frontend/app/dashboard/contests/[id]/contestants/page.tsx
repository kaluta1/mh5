'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import ApiService from '@/lib/api-service'
import { isRoundVotingLive } from '@/lib/is-round-voting-live'
import { contestService } from '@/services/contest-service'
import { followService } from '@/services/follow-service'
import { Button } from '@/components/ui/button'
import {
  ArrowLeft, Search, Heart, MessageCircle, UserPlus, UserCheck,
  Trophy, ThumbsUp, MapPin, ChevronDown, X, Globe, Play
} from 'lucide-react'

interface Round {
  id: number
  name: string
  status: string
  is_voting_open?: boolean
  voting_start_date?: string | null
  voting_end_date?: string | null
}

interface ContestantData {
  id: number; user_id: number; season_id: number; round_id: number | null
  title: string; description: string
  author_name: string; author_country: string; author_city: string; author_avatar_url: string | null
  rank: number; votes_count: number; total_points: number; images_count: number; videos_count: number
  favorites_count: number; reactions_count: number; comments_count: number
  is_in_favorites: boolean; can_vote: boolean; has_voted: boolean
  image_media_ids: string; video_media_ids: string
}

export default function ContestantsListPage() {
  const { t, language } = useLanguage()
  const { user } = useAuth()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const contestId = params.id as string

  const [contestName, setContestName] = useState('')
  const [contestMode, setContestMode] = useState<string>('')
  const [allContestants, setAllContestants] = useState<ContestantData[]>([])
  const [rounds, setRounds] = useState<Round[]>([])
  const [activeRoundId, setActiveRoundId] = useState<number | null>(null)
  const [selectedRound, setSelectedRound] = useState<string>('all')
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [followedUsers, setFollowedUsers] = useState<Set<number>>(new Set())
  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(new Set())
  const [votingMap, setVotingMap] = useState<Map<number, boolean>>(new Map())

  // Country dropdown
  const [selectedCountry, setSelectedCountry] = useState(searchParams.get('country') || '')
  const [showCountryDropdown, setShowCountryDropdown] = useState(false)
  const [countrySearch, setCountrySearch] = useState('')
  const [availableCountries, setAvailableCountries] = useState<string[]>([])
  const countryRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (countryRef.current && !countryRef.current.contains(e.target as Node)) setShowCountryDropdown(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const roundIdParam = searchParams.get('roundId')

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const data = await ApiService.getContest(parseInt(contestId), {
        filterCountry: 'all',
        filterContinent: 'all',
        roundId: roundIdParam ? parseInt(roundIdParam, 10) : undefined,
      }) as any
      setContestName(data.name || '')
      setContestMode(String(data.contest_mode || ''))
      setActiveRoundId(data.display_round_id ?? data.active_round_id ?? null)
      const cts = data.contestants || []
      setAllContestants(cts)
      const countries = new Set<string>()
      cts.forEach((c: ContestantData) => { if (c.author_country) countries.add(c.author_country) })
      setAvailableCountries(Array.from(countries).sort())
      const favs = new Set<number>()
      cts.forEach((c: ContestantData) => { if (c.is_in_favorites) favs.add(c.id) })
      setFavoriteIds(favs)
    } catch (error) { console.error('Error:', error) }
    finally { setLoading(false) }
  }, [contestId, roundIdParam])

  useEffect(() => {
    const loadRounds = async () => {
      try {
        const rd = await ApiService.getRounds() as any
        if (Array.isArray(rd)) {
          setRounds(
            rd.map((r: any, i: number) => ({
              id: r.id || i + 1,
              name: r.name || `Round ${i + 1}`,
              status: r.status || 'active',
              is_voting_open: Boolean(r.is_voting_open),
              voting_start_date: r.voting_start_date ?? null,
              voting_end_date: r.voting_end_date ?? null,
            }))
          )
        }
      } catch {}
    }
    loadRounds()
  }, [contestId])

  useEffect(() => { loadData() }, [loadData])

  const filteredContestants = allContestants.filter(c => {
    if (selectedCountry && selectedCountry !== 'all' && (c.author_country || '').toLowerCase() !== selectedCountry.toLowerCase()) return false
    if (selectedRound !== 'all' && c.round_id !== Number(selectedRound)) return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      return (c.author_name||'').toLowerCase().includes(q) || (c.title||'').toLowerCase().includes(q) || (c.author_country||'').toLowerCase().includes(q)
    }
    return true
  })

  const handleToggleFavorite = async (cid: number) => {
    try {
      if (favoriteIds.has(cid)) { await contestService.removeFromFavorites(cid); setFavoriteIds(p => { const n = new Set(p); n.delete(cid); return n }) }
      else { await contestService.addToFavorites(cid); setFavoriteIds(p => new Set(p).add(cid)) }
    } catch (e) { console.error(e) }
  }

  const handleFollow = async (uid: number) => {
    try {
      if (followedUsers.has(uid)) { await followService.unfollowUser(uid); setFollowedUsers(p => { const n = new Set(p); n.delete(uid); return n }) }
      else { await followService.followUser(uid); setFollowedUsers(p => new Set(p).add(uid)) }
    } catch (e) { console.error(e) }
  }

  const handleVote = async (cid: number) => {
    try {
      setVotingMap(p => new Map(p).set(cid, true))
      const cIdNum = parseInt(contestId, 10)
      const result = await contestService.voteForContestant(cid, {
        contestId: Number.isNaN(cIdNum) ? undefined : cIdNum,
      })
      if (result.success) {
        await loadData()
        window.dispatchEvent(new Event('vote-changed'))
      } else if (result.code === 'max_votes_reached') {
        await contestService.replaceVote(cid, Number.isNaN(cIdNum) ? undefined : cIdNum)
        await loadData()
        window.dispatchEvent(new Event('vote-changed'))
      }
    } catch (e) {
      console.error(e)
    } finally {
      setVotingMap(p => new Map(p).set(cid, false))
    }
  }

  const selectCountry = (country: string) => {
    setSelectedCountry(country); setShowCountryDropdown(false); setCountrySearch('')
    const p = new URLSearchParams(searchParams.toString())
    if (country && country !== 'all') p.set('country', country); else p.delete('country')
    router.replace(`/dashboard/contests/${contestId}/contestants?${p.toString()}`, { scroll: false })
  }

  const getInitials = (name: string) => name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || '?'

  const getMediaUrl = (c: ContestantData): string | null => {
    try {
      const ids = c.image_media_ids || c.video_media_ids
      if (ids) {
        const parsed = typeof ids === 'string' ? JSON.parse(ids) : ids
        if (Array.isArray(parsed) && parsed.length > 0) {
          const url = parsed[0]
          if (url.startsWith('http')) return url
          const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          return url.startsWith('/') ? `${base}${url}` : `${base}/${url}`
        }
      }
    } catch {}
    return null
  }

  const filteredCountryList = availableCountries.filter(c => c.toLowerCase().includes(countrySearch.toLowerCase()))

  if (loading) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-myhigh5-primary border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900">
      <div className="px-4 py-3 sm:px-6 sm:py-4 lg:px-8">
        <div className="max-w-7xl mx-auto">

          {/* Back */}
          <Button onClick={() => router.back()} variant="ghost" size="sm" className="gap-2 mb-4 -ml-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
            <ArrowLeft className="h-4 w-4" />
            {t('common.back') || 'Retour'}
          </Button>

          {/* Title */}
          <div className="mb-5">
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">{contestName}</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              {filteredContestants.length}{' '}
              {contestMode === 'nomination'
                ? (language === 'fr' ? 'nominateurs' : 'nominators')
                : (language === 'fr' ? 'participants' : 'contestants')}
            </p>
          </div>

          {/* Filters bar */}
          <div className="flex flex-wrap items-center gap-3 mb-6">
            {/* Country dropdown */}
            <div className="relative" ref={countryRef}>
              <button
                onClick={() => setShowCountryDropdown(!showCountryDropdown)}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border transition-all ${
                  selectedCountry && selectedCountry !== 'all'
                    ? 'bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 text-myhigh5-primary dark:text-white border-myhigh5-primary/30'
                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                }`}
              >
                <MapPin className="w-4 h-4" />
                {selectedCountry && selectedCountry !== 'all' ? selectedCountry : (language === 'fr' ? 'Tous les pays' : 'All countries')}
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showCountryDropdown ? 'rotate-180' : ''}`} />
              </button>
              {showCountryDropdown && (
                <div className="absolute top-full left-0 mt-1.5 w-64 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-xl z-50 overflow-hidden">
                  <div className="p-2 border-b border-gray-100 dark:border-gray-700">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                      <input type="text" value={countrySearch} onChange={(e) => setCountrySearch(e.target.value)}
                        placeholder={language === 'fr' ? 'Rechercher un pays...' : 'Search country...'}
                        className="w-full pl-8 pr-3 py-2 text-sm bg-gray-50 dark:bg-gray-700/50 border-0 rounded-lg focus:outline-none focus:ring-2 focus:ring-myhigh5-primary/30 text-gray-900 dark:text-white placeholder-gray-400"
                        autoFocus />
                    </div>
                  </div>
                  <div className="max-h-48 overflow-y-auto py-1">
                    <button onClick={() => selectCountry('all')}
                      className={`w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors flex items-center gap-2 ${!selectedCountry || selectedCountry === 'all' ? 'text-myhigh5-primary dark:text-white font-medium' : 'text-gray-700 dark:text-gray-300'}`}>
                      <Globe className="w-4 h-4" /> {language === 'fr' ? 'Tous les pays' : 'All countries'}
                    </button>
                    {filteredCountryList.map(country => (
                      <button key={country} onClick={() => selectCountry(country)}
                        className={`w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${selectedCountry === country ? 'text-myhigh5-primary dark:text-white font-medium bg-myhigh5-primary/5' : 'text-gray-700 dark:text-gray-300'}`}>
                        {country}
                      </button>
                    ))}
                    {filteredCountryList.length === 0 && <p className="px-4 py-3 text-xs text-gray-400 text-center">{language === 'fr' ? 'Aucun pays trouvé' : 'No country found'}</p>}
                  </div>
                </div>
              )}
            </div>

            {/* Round pills */}
            {rounds.length > 0 && (
              <>
                <div className="w-px h-6 bg-gray-200 dark:bg-gray-700 hidden sm:block" />
                <div className="flex gap-1.5 overflow-x-auto">
                  <button onClick={() => setSelectedRound('all')}
                    className={`px-3.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${selectedRound === 'all' ? 'bg-gray-900 dark:bg-white text-white dark:text-gray-900' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'}`}>
                    {language === 'fr' ? 'Tous' : 'All'}
                  </button>
                  {rounds.map(round => (
                    <button key={round.id} onClick={() => setSelectedRound(String(round.id))}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all flex flex-col items-center justify-center gap-0.5 min-h-[2.5rem] ${selectedRound === String(round.id) ? 'bg-gray-900 dark:bg-white text-white dark:text-gray-900' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'}`}>
                      {isRoundVotingLive(round, rounds) && (
                        <span
                          className={`text-[10px] font-semibold leading-none ${
                            selectedRound === String(round.id)
                              ? 'text-blue-200'
                              : 'text-blue-600 dark:text-blue-400'
                          }`}
                        >
                          VOTE NOW
                        </span>
                      )}
                      <span className="flex items-center gap-1.5">
                        {round.name}
                        {round.id === activeRoundId && <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />}
                      </span>
                    </button>
                  ))}
                </div>
              </>
            )}

            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input type="text" placeholder={t('dashboard.contests.search_contestant') || 'Rechercher...'}
                value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-myhigh5-primary/30 text-gray-900 dark:text-white placeholder-gray-400" />
            </div>
          </div>

          {/* Active filter chip */}
          {selectedCountry && selectedCountry !== 'all' && (
            <div className="flex items-center gap-2 mb-4">
              <button onClick={() => selectCountry('all')} className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-myhigh5-primary/10 text-myhigh5-primary dark:text-white border border-myhigh5-primary/20 hover:bg-myhigh5-primary/20 transition-colors">
                <MapPin className="w-3 h-3" /> {selectedCountry} <X className="w-3 h-3" />
              </button>
            </div>
          )}

          {/* Contestants grid — Facebook friend cards style */}
          {filteredContestants.length === 0 ? (
            <div className="text-center py-20">
              <Trophy className="w-14 h-14 text-gray-200 dark:text-gray-700 mx-auto mb-4" />
              <p className="text-gray-500 dark:text-gray-400 font-medium">{
                contestMode === 'nomination'
                  ? (language === 'fr' ? 'Aucun nominateur trouvé' : 'No nominators found')
                  : (language === 'fr' ? 'Aucun participant trouvé' : 'No contestants found')
              }</p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">{language === 'fr' ? 'Essayez de modifier vos filtres' : 'Try adjusting your filters'}</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4">
              {filteredContestants.map((contestant) => {
                const isOwner = user?.id === contestant.user_id
                const isFollowed = followedUsers.has(contestant.user_id)
                const isFav = favoriteIds.has(contestant.id)
                const isVoting = votingMap.get(contestant.id) || false
                const mediaUrl = getMediaUrl(contestant)

                return (
                  <div key={contestant.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700/50 overflow-hidden shadow-sm hover:shadow-lg transition-all duration-200 group">

                    {/* Photo / Avatar area */}
                    <div
                      className="relative aspect-square bg-gray-100 dark:bg-gray-700 cursor-pointer overflow-hidden"
                      onClick={() => router.push(`/dashboard/contests/${contestId}/contestant/${contestant.id}`)}
                    >
                      {mediaUrl ? (
                        <img src={mediaUrl} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
                      ) : contestant.author_avatar_url ? (
                        <img src={contestant.author_avatar_url} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
                      ) : (
                        <div className="w-full h-full bg-gradient-to-br from-myhigh5-primary/80 to-blue-600 flex items-center justify-center">
                          <span className="text-4xl sm:text-5xl font-bold text-white/80">{getInitials(contestant.author_name)}</span>
                        </div>
                      )}

                      {/* Rank badge */}
                      {contestant.rank <= 3 && (
                        <div className={`absolute top-2 left-2 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shadow-lg ${
                          contestant.rank === 1 ? 'bg-yellow-400 text-yellow-900' :
                          contestant.rank === 2 ? 'bg-gray-300 text-gray-700' :
                          'bg-amber-500 text-white'
                        }`}>
                          {contestant.rank}
                        </div>
                      )}

                      {/* Favorite heart */}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleToggleFavorite(contestant.id) }}
                        className={`absolute top-2 right-2 w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                          isFav ? 'bg-red-500 text-white' : 'bg-black/30 text-white/80 opacity-0 group-hover:opacity-100 hover:bg-red-500'
                        }`}
                      >
                        <Heart className={`w-4 h-4 ${isFav ? 'fill-current' : ''}`} />
                      </button>

                      {/* Vote count */}
                      <div className="absolute bottom-2 right-2 bg-black/50 backdrop-blur-sm text-white text-[11px] font-medium px-2 py-0.5 rounded-full flex items-center gap-1">
                        <ThumbsUp className="w-3 h-3" /> {contestant.total_points ?? 0} pts
                      </div>

                      {/* Video indicator */}
                      {contestant.videos_count > 0 && (
                        <div className="absolute bottom-2 left-2 bg-black/50 backdrop-blur-sm text-white text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1">
                          <Play className="w-3 h-3" /> {contestant.videos_count}
                        </div>
                      )}
                    </div>

                    {/* Info */}
                    <div className="p-3">
                      <h3
                        className="text-sm font-semibold text-gray-900 dark:text-white truncate cursor-pointer hover:underline"
                        onClick={() => router.push(`/dashboard/contests/${contestId}/contestant/${contestant.id}`)}
                      >
                        {contestant.author_name || 'Anonyme'}
                      </h3>
                      <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                        {contestant.title || [contestant.author_country, contestant.author_city].filter(Boolean).join(' · ') || (
                          contestMode === 'nomination'
                            ? (language === 'fr' ? 'Nominateur' : 'Nominator')
                            : (language === 'fr' ? 'Participant' : 'Contestant')
                        )}
                      </p>

                      {/* Action buttons */}
                      <div className="mt-3 space-y-1.5">
                        {/* Primary: Vote or Follow */}
                        {!isOwner ? (
                          <>
                            {!contestant.has_voted && contestant.can_vote ? (
                              <button
                                onClick={() => handleVote(contestant.id)}
                                disabled={isVoting}
                                className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-semibold bg-myhigh5-primary text-white hover:bg-myhigh5-primary/90 transition-all"
                              >
                                <ThumbsUp className="w-4 h-4" />
                                Vote
                              </button>
                            ) : (
                              <button
                                onClick={() => handleFollow(contestant.user_id)}
                                className={`w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-semibold transition-all ${
                                  isFollowed
                                    ? 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                                    : 'bg-myhigh5-primary text-white hover:bg-myhigh5-primary/90'
                                }`}
                              >
                                {isFollowed ? <UserCheck className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
                                {isFollowed ? (language === 'fr' ? 'Suivi' : 'Following') : (language === 'fr' ? 'Suivre' : 'Follow')}
                              </button>
                            )}

                            {/* Secondary: Message */}
                            <button
                              onClick={() => router.push(`/dashboard/messages?user=${contestant.user_id}`)}
                              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-semibold bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-all"
                            >
                              <MessageCircle className="w-4 h-4" />
                              Message
                            </button>
                          </>
                        ) : (
                          <div className="text-center py-1.5 text-xs text-gray-400 dark:text-gray-500 font-medium">
                            {language === 'fr' ? 'Votre participation' : 'Your entry'}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
