'use client'

import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import ApiService from '@/lib/api-service'
import { contestService, Contest, Contestant as ServiceContestant } from '@/services/contest-service'
import { Button } from '@/components/ui/button'
import { ContestantCard } from '@/components/dashboard/contestant-card'
import { ArrowLeft, Globe, MapPin } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { API_URL } from '@/lib/config'

interface Media {
  id: string
  type: 'image' | 'video'
  url: string
  thumbnail?: string
}

interface Contestant extends Omit<ServiceContestant, 'id' | 'user_id' | 'title' | 'description' | 'image_media_ids' | 'video_media_ids' | 'votes_count' | 'author_name' | 'author_country' | 'author_city' | 'author_avatar_url'> {
  id: string
  userId: number
  name: string
  country?: string
  city?: string
  continent?: string
  avatar: string
  participationTitle: string
  description: string
  votes: number
  rank?: number
  imagesCount: number
  videosCount: number
  canVote: boolean
  hasVoteRight?: boolean
  hasVoted: boolean
  media: Media[]
  comments: number
  isFavorite: boolean
  contestant_image_url?: string
  reactions?: number
  favorites?: number
  shares?: number
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

export default function ContestantsListPage() {
  const { t, language } = useLanguage()
  const { user } = useAuth()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const contestId = params.id as string

  const [contest, setContest] = useState<Contest | null>(null)
  const [allContestants, setAllContestants] = useState<Contestant[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [favorites, setFavorites] = useState<string[]>([])
  const [rankings, setRankings] = useState<{[key: string]: number}>({})

  // Read location filters from URL (same pattern as contest detail page)
  const filterCountry = searchParams.get('country') || ''
  const filterContinent = searchParams.get('continent') || ''

  // State for client-side override (the "Globe" vs "Country" toggle)
  const [showMyCountryOnly, setShowMyCountryOnly] = useState(true)
  const [userCountry, setUserCountry] = useState<string>(() => filterCountry)
  const [userContinent, setUserContinent] = useState<string>(() => filterContinent || 'all')

  // Mettre à jour l'URL quand les filtres changent
  const updateUrlWithFilters = useCallback((country: string, continent: string) => {
    const params = new URLSearchParams()
    if (country) params.set('country', country)
    if (continent && continent !== 'all') params.set('continent', continent)

    const queryString = params.toString()
    const newUrl = `/dashboard/contests/${contestId}/contestants${queryString ? `?${queryString}` : ''}`
    router.replace(newUrl, { scroll: false })
  }, [router, contestId])

  // Auto-redirect to user's country + continent=all if no filters in URL (Mirrors contest detail page)
  useEffect(() => {
    if (!user?.country) return;
    const urlCountry = searchParams.get('country');
    const urlContinent = searchParams.get('continent');

    if (!urlCountry && !urlContinent) {
      const defaultCountry = user.country || '';
      if (defaultCountry) {
        const p = new URLSearchParams();
        p.set('country', defaultCountry);
        p.set('continent', 'all');
        router.replace(`/dashboard/contests/${contestId}/contestants?${p.toString()}`, { scroll: false });
      }
    }
  }, [user?.country, contestId, searchParams, router]);

  // Sync state with URL params (same filters as contest detail page)
  useEffect(() => {
    const urlCountry = searchParams.get('country');
    const urlContinent = searchParams.get('continent') || 'all';
    if (urlCountry === 'all') {
      setShowMyCountryOnly(false);
    } else if (urlCountry) {
      setUserCountry(urlCountry);
      setShowMyCountryOnly(true);
    } else if (user?.country) {
      setUserCountry(user.country);
      setShowMyCountryOnly(true);
    }
    setUserContinent(urlContinent);
  }, [user?.country, searchParams]);

  const loadContest = useCallback(async () => {
    try {
      setLoading(true)

      // Fetch ALL contestants (same as contest detail page) - backend filter can return 0 due to format mismatch
      const c = await ApiService.getContest(parseInt(contestId), {
        filterCountry: 'all',
        filterContinent: 'all'
      }) as any

      const parseMediaIds = (mediaIds: string | undefined, type: 'image' | 'video'): Media[] => {
        if (!mediaIds) return []
        try {
          const parsed = typeof mediaIds === 'string' ? JSON.parse(mediaIds) : mediaIds
          if (!Array.isArray(parsed)) return []
          const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          return parsed.filter((url: string) => url && url.trim() !== '').map((url: string, idx: number) => {
            let fullUrl = url
            if (url && !url.startsWith('http') && !url.startsWith('data:')) {
              fullUrl = url.startsWith('/') ? `${API_BASE}${url}` : `${API_BASE}/${url}`
            }
            return { id: `${type}-${idx}`, type, url: fullUrl, thumbnail: type === 'video' ? fullUrl : undefined }
          })
        } catch { return [] }
      }

      const mappedContestants: Contestant[] = (c.contestants || []).map((ct: any, index: number) => {
        const images = parseMediaIds(ct.image_media_ids, 'image')
        const videos = parseMediaIds(ct.video_media_ids, 'video')
        return {
          id: String(ct.id ?? index),
          userId: ct.user_id,
          name: ct.author_name || `Contestant #${index + 1}`,
          country: ct.author_country,
          city: ct.author_city,
          continent: ct.author?.continent,
          avatar: ct.author_avatar_url || '/default-avatar.png',
          participationTitle: ct.title,
          description: ct.description ?? '',
          votes: ct.votes_count ?? 0,
          rank: ct.rank,
          imagesCount: ct.images_count ?? images.length,
          videosCount: ct.videos_count ?? videos.length,
          canVote: ct.can_vote ?? false,
          hasVoted: ct.has_voted ?? false,
          media: [...images, ...videos],
          comments: ct.comments_count ?? 0,
          reactions: ct.reactions_count ?? 0,
          favorites: ct.favorites_count ?? 0,
          shares: ct.shares_count ?? 0,
          isFavorite: ct.is_in_favorites ?? false,
          votesList: ct.votes || [],
          commentsList: ct.comments || [],
          reactionsList: ct.reactions || {},
          favoritesList: ct.favorites || [],
          sharesList: ct.shares || [],
        }
      })

      mappedContestants.sort((a, b) => {
        if (a.rank && b.rank) return a.rank - b.rank
        if (a.rank && !b.rank) return -1
        if (!a.rank && b.rank) return 1
        if (b.votes !== a.votes) return b.votes - a.votes
        return Number(a.id) - Number(b.id)
      })

      const updatedContest: Contest = {
        id: c.id,
        title: c.name || c.contest_type || 'Unknown Contest',
        description: c.description,
        coverImage: c.cover_image_url || '',
        startDate: c.submission_start_date ? new Date(c.submission_start_date) : new Date(),
        status: 'global',
        received: c.entries_count ?? mappedContestants.length,
        contestants: mappedContestants.length,
        likes: c.total_votes ?? 0,
        comments: 0,
        isOpen: true,
        contestType: c.contest_type || 'general',
        contest_type: c.contest_type || 'general',
        name: c.name || 'Unknown Contest',
      } as Contest

      setContest(updatedContest)
      setAllContestants(mappedContestants)
      setFavorites(mappedContestants.filter(c => c.isFavorite).map(c => c.id))
    } catch (error) {
      console.error('Error loading contest:', error)
    } finally {
      setLoading(false)
    }
  }, [contestId])

  useEffect(() => {
    if (contestId) {
      loadContest();
    }
  }, [loadContest, contestId]);

  // Country code mapping with common variations
  const countryCodeMap: Record<string, string> = {
    // North America
    'united states': 'us',
    'usa': 'us',
    'united states of america': 'us',
    'canada': 'ca',
    'mexico': 'mx',

    // Europe
    'united kingdom': 'gb',
    'uk': 'gb',
    'great britain': 'gb',
    'france': 'fr',
    'spain': 'es',
    'germany': 'de',
    'italy': 'it',
    'netherlands': 'nl',
    'sweden': 'se',
    'switzerland': 'ch',
    'norway': 'no',
    'denmark': 'dk',
    'finland': 'fi',
    'belgium': 'be',
    'portugal': 'pt',
    'ireland': 'ie',
    'austria': 'at',
    'greece': 'gr',
    'turkey': 'tr',
    'poland': 'pl',
    'ukraine': 'ua',
    'romania': 'ro',
    'hungary': 'hu',
    'czech republic': 'cz',
    'slovakia': 'sk',
    'croatia': 'hr',
    'serbia': 'rs',
    'bulgaria': 'bg',
    'slovenia': 'si',
    'lithuania': 'lt',
    'latvia': 'lv',
    'estonia': 'ee',
    'albania': 'al',
    'macedonia': 'mk',
    'montenegro': 'me',
    'bosnia and herzegovina': 'ba',
    'bosnia': 'ba',
    'herzegovina': 'ba',
    'kosovo': 'xk',
    'moldova': 'md',
    'belarus': 'by',

    // Asia
    'japan': 'jp',
    'south korea': 'kr',
    'north korea': 'kp',
    'china': 'cn',
    'india': 'in',
    'russia': 'ru',
    'kazakhstan': 'kz',
    'uzbekistan': 'uz',
    'turkmenistan': 'tm',
    'tajikistan': 'tj',
    'kyrgyzstan': 'kg',
    'afghanistan': 'af',
    'pakistan': 'pk',
    'iran': 'ir',
    'iraq': 'iq',
    'syria': 'sy',
    'lebanon': 'lb',
    'jordan': 'jo',
    'israel': 'il',
    'palestine': 'ps',
    'saudi arabia': 'sa',
    'yemen': 'ye',
    'oman': 'om',
    'united arab emirates': 'ae',
    'uae': 'ae',
    'qatar': 'qa',
    'kuwait': 'kw',
    'bahrain': 'bh',

    // Africa
    'egypt': 'eg',
    'libya': 'ly',
    'tunisia': 'tn',
    'algeria': 'dz',
    'morocco': 'ma',
    'mauritania': 'mr',
    'mali': 'ml',
    'niger': 'ne',
    'chad': 'td',
    'sudan': 'sd',
    'south sudan': 'ss',
    'ethiopia': 'et',
    'somalia': 'so',
    'djibouti': 'dj',
    'eritrea': 'er',
    'kenya': 'ke',
    'tanzania': 'tz',
    'tz': 'tz',
    'united republic of tanzania': 'tz',
    'uganda': 'ug',
    'rwanda': 'rw',
    'burundi': 'bi',
    'zambia': 'zm',
    'zimbabwe': 'zw',
    'mozambique': 'mz',
    'madagascar': 'mg',
    'angola': 'ao',
    'namibia': 'na',
    'botswana': 'bw',
    'south africa': 'za',
    'lesotho': 'ls',
    'eswatini': 'sz',
    'swaziland': 'sz',
    'senegal': 'sn',
    'gambia': 'gm',
    'the gambia': 'gm',
    'guinea-bissau': 'gw',
    'guinea': 'gn',
    'sierra leone': 'sl',
    'liberia': 'lr',
    'ivory coast': 'ci',
    'cote d\'ivoire': 'ci',
    'ghana': 'gh',
    'togo': 'tg',
    'benin': 'bj',
    'nigeria': 'ng',
    'cameroon': 'cm',
    'gabon': 'ga',
    'congo': 'cg',
    'republic of the congo': 'cg',
    'democratic republic of the congo': 'cd',
    'dr congo': 'cd',
    'central african republic': 'cf',
    'burkina faso': 'bf',
    'equatorial guinea': 'gq',
    'sao tome and principe': 'st',
    'malawi': 'mw',
    'mauritius': 'mu',
    'comoros': 'km',
    'seychelles': 'sc',
    'cape verde': 'cv'
  };

  // Normalize country for comparison - handles "TZ" vs "Tanzania" etc.
  const getCanonicalCountryCode = (str: string | undefined): string => {
    if (!str) return '';
    const normalized = str.toString().toLowerCase().trim();
    return countryCodeMap[normalized] || normalized;
  };

  // Strict single-country match: contestant must be from the SAME country only (e.g. Uganda only Uganda, Kenya only Kenya)
  const countriesMatch = (userCountryVal: string, contestantCountryVal: string): boolean => {
    if (!contestantCountryVal || !userCountryVal) return false;
    const userCode = getCanonicalCountryCode(userCountryVal);
    const contestantCode = getCanonicalCountryCode(contestantCountryVal);
    const normUser = userCountryVal.toString().toLowerCase().trim();
    const normContestant = contestantCountryVal.toString().toLowerCase().trim();
    // Prefer canonical code match (e.g. "TZ" and "Tanzania" -> "tz" so only Tanzania matches)
    if (userCode && contestantCode && userCode === contestantCode) return true;
    // Exact match
    if (normUser === normContestant) return true;
    // Same-country name substring only (e.g. "United Republic of Tanzania" contains "Tanzania") - do not match across countries
    if (normContestant.includes(normUser) || normUser.includes(normContestant)) {
      // Avoid cross-match: "uganda" must not match "tanzania" etc.
      if (userCode && contestantCode && userCode !== contestantCode) return false;
      return true;
    }
    return false;
  };


  // Continent match - same logic as contest detail page
  const continentsMatch = (userContinentVal: string, contestantContinent: string | undefined): boolean => {
    if (!userContinentVal || userContinentVal === 'all') return true;
    if (!contestantContinent) return false;
    const uc = (userContinentVal || '').toLowerCase().trim();
    const cc = (contestantContinent || '').toLowerCase().trim();
    return cc.includes(uc) || uc.includes(cc) || uc === cc;
  };

  // Effective country: URL param or user's country - never show "all" when user has a country
  const effectiveCountry = (userCountry || filterCountry || user?.country || '').trim();
  const effectiveContinent = (userContinent && userContinent !== 'all' ? userContinent : '').trim();

  // Strict single-country: show ONLY contestants from the selected country (Uganda only Uganda, Kenya only Kenya)
  const contestants = React.useMemo(() => {
    if (!showMyCountryOnly && !effectiveContinent) {
      return allContestants;
    }
    if (!showMyCountryOnly && effectiveContinent) {
      return allContestants.filter(c => continentsMatch(effectiveContinent, c.continent));
    }
    if (showMyCountryOnly && effectiveCountry) {
      return allContestants.filter(contestant => {
        const matchCountry = countriesMatch(effectiveCountry, contestant.country || '');
        const matchContinent = continentsMatch(effectiveContinent || 'all', contestant.continent);
        return matchCountry && matchContinent;
      });
    }
    if (showMyCountryOnly && user?.country) {
      return allContestants.filter(contestant => countriesMatch(user.country, contestant.country || '') && continentsMatch('all', contestant.continent));
    }
    return allContestants;
  }, [allContestants, showMyCountryOnly, effectiveCountry, effectiveContinent, user?.country]);

  // Count of contestants from user's country
  const countryContestantCount = React.useMemo(() => {
    const targetCountry = user?.country || userCountry;
    if (!targetCountry) return allContestants.length;

    return allContestants.filter(contestant => {
      if (!contestant.country) return false;
      return countriesMatch(targetCountry, contestant.country);
    }).length;
  }, [allContestants, userCountry, user?.country]);

  const filteredContestants = contestants.filter(contestant => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    return (
      contestant.name.toLowerCase().includes(query) ||
      contestant.participationTitle?.toLowerCase().includes(query) ||
      contestant.description.toLowerCase().includes(query) ||
      contestant.country?.toLowerCase().includes(query) ||
      contestant.city?.toLowerCase().includes(query)
    )
  })

  const handleToggleFavorite = async (contestantId: string) => {
    try {
      const contestant = contestants.find(c => c.id === contestantId)
      if (!contestant) return

      if (favorites.includes(contestantId)) {
        await contestService.removeFromFavorites(Number(contestantId))
        setFavorites(prev => prev.filter(id => id !== contestantId))
      } else {
        await contestService.addToFavorites(Number(contestantId))
        setFavorites(prev => [...prev, contestantId])
      }
    } catch (error) {
      console.error('Error toggling favorite:', error)
    }
  }

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

  if (loading) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-myfav-primary mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">{t('common.loading') || 'Chargement...'}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900">
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-6 flex items-center justify-between">
            <Button
              onClick={() => router.back()}
              variant="outline"
              size="sm"
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              {t('common.back') || 'Retour'}
            </Button>
          </div>

          {/* Title */}
          <div className="mb-6">
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-gray-900 dark:text-white mb-2">
              {contest?.title || t('dashboard.contests.contestants') || 'Participants'}
            </h1>
            {contest && (
              <p className="text-lg text-gray-600 dark:text-gray-400">
                {contest.contestType}
              </p>
            )}
          </div>

          {/* Search and Country Filter */}
          <div className="mb-6 space-y-4">
            {/* Country toggle */}
            {(user?.country || filterCountry) && (
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-2 px-3 py-1.5 bg-myfav-primary/10 text-myfav-primary rounded-full border border-myfav-primary/20">
                  <MapPin className="h-4 w-4" />
                  <span className="text-sm font-medium">{user?.country || userCountry}</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                  {t('dashboard.contests.filtered_by_country') || 'Filtré par votre pays'}
                </p>
              </div>
            )}
            {/* Search */}
            <Input
              type="text"
              placeholder={t('dashboard.contests.search_contestant') || 'Rechercher un participant...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="max-w-md"
            />

            {loading ? (
              <div className="flex justify-center items-center h-64">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-myfav-primary"></div>
                <span className="ml-3">Loading contestants...</span>
              </div>
            ) : allContestants.length === 0 ? (
              <div className="text-center py-12">
                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                  {t('dashboard.contests.no_contestants') || 'No contestants available'}
                </h3>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                  {t('dashboard.contests.check_back_later') || 'Check back later for new contestants.'}
                </p>
              </div>
            ) : filteredContestants.length === 0 ? (
              <div className="text-center py-12">
                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                  {t('dashboard.contests.no_matching_contestants') || 'No matching contestants found'}
                </h3>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                  {t('dashboard.contests.try_different_filters') || 'Try adjusting your filters or search term.'}
                </p>
                <button
                  onClick={() => {
                    setSearchQuery('');
                    setShowMyCountryOnly(false);
                  }}
                  className="mt-4 px-4 py-2 bg-myfav-primary text-white rounded-md hover:bg-myfav-primary/90"
                >
                  {t('common.clear_filters') || 'Clear filters'}
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {filteredContestants.map((contestant) => (
                  <ContestantCard
                    key={contestant.id}
                    id={contestant.id}
                    userId={contestant.userId}
                    currentUserId={user?.id}
                    contestId={contestId}
                    name={contestant.name || 'Anonymous'}
                    country={contestant.country || 'Unknown'}
                    city={contestant.city || ''}
                    avatar={contestant.avatar || '/default-avatar.png'}
                    participationTitle={contestant.participationTitle || 'Contestant'}
                    votes={contestant.votes || 0}
                    rank={contestant.rank}
                    imagesCount={contestant.imagesCount || 0}
                    videosCount={contestant.videosCount || 0}
                    canVote={contestant.canVote || false}
                    hasVoted={contestant.hasVoted || false}
                    isFavorite={favorites.includes(contestant.id)}
                    media={contestant.media || []}
                    description={contestant.description || ''}
                    comments={contestant.comments || 0}
                    reactions={contestant.reactions || 0}
                    favorites={contestant.favorites || 0}
                    votesList={contestant.votesList || []}
                    reactionsList={contestant.reactionsList || {}}
                    favoritesList={contestant.favoritesList || []}
                    onToggleFavorite={() => handleToggleFavorite(contestant.id)}
                    onViewDetails={() => router.push(`/dashboard/contests/${contestId}/contestant/${contestant.id}`)}
                    onVote={() => {
                      // Voting is handled in ContestantCard
                    }}
                    onComment={() => {}}
                    onShare={() => {}}
                    onHoverAuthor={() => {}}
                    onHoverEnd={() => {}}
                    onHoverDescription={() => {}}
                    onHoverVotes={() => {
                      // Only the author can see the votes list
                      if (user?.id === contestant.userId) {
                        // TODO: Implement votes list display
                      }
                    }}
                    onHoverReactions={() => {}}
                    onHoverFavorites={() => {
                      // Only the author can see the favorites list
                      if (user?.id === contestant.userId) {
                        // TODO: Implement favorites list display
                      }
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

