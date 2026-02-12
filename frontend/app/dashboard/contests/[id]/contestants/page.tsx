'use client'

import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { contestService, ContestResponse } from '@/services/contest-service'
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

export default function ContestantsListPage() {
  const { t, language } = useLanguage()
  const { user } = useAuth()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const contestId = params.id as string

  const [contest, setContest] = useState<ContestResponse | null>(null)
  const [allContestants, setAllContestants] = useState<Contestant[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [favorites, setFavorites] = useState<string[]>([])

  // Read location filters from URL (same pattern as contest detail page)
  const filterCountry = searchParams.get('country') || ''
  const filterContinent = searchParams.get('continent') || ''

  // State for client-side override (the "Globe" vs "Country" toggle)
  const [showMyCountryOnly, setShowMyCountryOnly] = useState(true)
  const [userCountry, setUserCountry] = useState<string>(() => filterCountry)

  // Mettre à jour l'URL quand les filtres changent
  const updateUrlWithFilters = useCallback((country: string, continent: string) => {
    const params = new URLSearchParams()
    if (country) params.set('country', country)
    if (continent && continent !== 'all') params.set('continent', continent)

    const queryString = params.toString()
    const newUrl = `/dashboard/contests/${contestId}/contestants${queryString ? `?${queryString}` : ''}`
    router.replace(newUrl, { scroll: false })
  }, [router, contestId])

  // Auto-redirect to user's country if no filters in URL (Mirrors contest detail page)
  useEffect(() => {
    if (!user || (!user.country && !user.continent)) return;
    const urlCountry = searchParams.get('country');
    const urlContinent = searchParams.get('continent');

    if (!urlCountry && !urlContinent) {
      const defaultCountry = user.country || '';
      const defaultContinent = user.continent || 'all';

      if (defaultCountry || (defaultContinent && defaultContinent !== 'all')) {
        const p = new URLSearchParams();
        if (defaultCountry) p.set('country', defaultCountry);
        if (defaultContinent && defaultContinent !== 'all') p.set('continent', defaultContinent);
        const q = p.toString();
        if (q) {
          console.log('[ContestantsPage] Redirecting to default filters:', q);
          router.replace(`/dashboard/contests/${contestId}/contestants?${q}`, { scroll: false });
        }
      }
    }
  }, [user, contestId, searchParams, router]);

  // Sync state with URL params
  useEffect(() => {
    const urlCountry = searchParams.get('country');
    if (urlCountry === 'all') {
      setShowMyCountryOnly(false);
    } else if (urlCountry) {
      setUserCountry(urlCountry);
      setShowMyCountryOnly(true);
    } else if (user?.country) {
      // Fallback if URL is empty but user has country
      setUserCountry(user.country);
      setShowMyCountryOnly(true);
    }
  }, [user?.country, searchParams]);

  const loadContest = useCallback(async () => {
    try {
      setLoading(true)

      // Mirroring contest detail page: If URL has filters, use them. 
      // EXCEPT: If we want client-side "Show All" to work instantly, we might want 'all'.
      // BUT: The user specifically complained it's not filtered by default.
      // So let's use the URL filters (or user default) which matches the detail page.

      const params: any = {};
      if (filterCountry) params.filter_country = filterCountry;
      if (filterContinent) params.filter_continent = filterContinent;

      // If NO filters in URL and NOT logged in, we get everyone.
      // If NO filters in URL and LOGGED in, backend will fallback to user country.

      console.log('[ContestantsPage] Loading with params:', params);
      const response = await contestService.getContestById(contestId, params)
      setContest(response)

      const parseMediaIds = (mediaIds: string | null | undefined, type: 'image' | 'video'): Media[] => {
        if (!mediaIds) return []

        try {
          // Si c'est déjà une URL complète
          if (mediaIds.startsWith('http://') || mediaIds.startsWith('https://')) {
            return [{
              id: mediaIds,
              type,
              url: mediaIds,
              thumbnail: type === 'video' ? mediaIds : undefined
            }]
          }

          // Si c'est un JSON array
          if (mediaIds.startsWith('[')) {
            const ids = JSON.parse(mediaIds)
            return ids.map((id: string | number) => ({
              id: String(id),
              type,
              url: `${API_URL}/api/v1/media/${id}`,
              thumbnail: type === 'video' ? `${API_URL}/api/v1/media/${id}/thumbnail` : undefined
            }))
          }

          // Si c'est un ID simple
          return [{
            id: String(mediaIds),
            type,
            url: `${API_URL}/api/v1/media/${mediaIds}`,
            thumbnail: type === 'video' ? `${API_URL}/api/v1/media/${mediaIds}/thumbnail` : undefined
          }]
        } catch (error) {
          console.error('Error parsing media IDs:', error)
          return []
        }
      }

      // Les contestants sont dans la réponse enrichie
      const contestantsResponse = (response as any).contestants || []
      const mappedContestants: Contestant[] = contestantsResponse.map((c: any) => {
        const images = parseMediaIds(c.image_media_ids, 'image')
        const videos = parseMediaIds(c.video_media_ids, 'video')
        const allMedia = [...images, ...videos]

        return {
          id: String(c.id),
          userId: c.user_id,
          name: c.author_name || 'Utilisateur inconnu',
          country: c.author_country,
          city: c.author_city,
          avatar: c.author_avatar_url || '',
          participationTitle: c.title || '',
          votes: c.votes_count || 0,
          rank: c.rank,
          imagesCount: c.images_count ?? images.length,
          videosCount: c.videos_count ?? videos.length,
          canVote: c.can_vote || false,
          hasVoted: c.has_voted || false,
          isFavorite: c.is_in_favorites ?? false,
          media: allMedia,
          description: c.description || '',
          comments: c.comments_count || 0,
          reactions: c.reactions_count || 0,
          favorites: c.favorites_count || 0,
          shares: c.shares_count || 0,
          votesList: c.votes || [],
          commentsList: c.comments || [],
          reactionsList: c.reactions || {},
          favoritesList: c.favorites || [],
          sharesList: c.shares || [],
          season: c.season,
        }
      })

      // Trier les contestants par rank (croissant) si disponible, sinon par votes décroissants
      mappedContestants.sort((a, b) => {
        if (a.rank && b.rank) {
          return a.rank - b.rank
        }
        if (a.rank && !b.rank) return -1
        if (!a.rank && b.rank) return 1
        if (b.votes !== a.votes) {
          return b.votes - a.votes
        }
        return Number(a.id) - Number(b.id)
      })

      setAllContestants(mappedContestants)
      setFavorites(mappedContestants.filter(c => c.isFavorite).map(c => c.id))
    } catch (error) {
      console.error('Error loading contest:', error)
    } finally {
      setLoading(false)
    }
  }, [contestId, filterCountry, filterContinent]);

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

  const countriesMatch = (userCountryVal: string, contestantCountryVal: string): boolean => {
    if (!contestantCountryVal) return false;
    const userCode = getCanonicalCountryCode(userCountryVal);
    const contestantCode = getCanonicalCountryCode(contestantCountryVal);
    const normUser = userCountryVal.toString().toLowerCase().trim();
    const normContestant = contestantCountryVal.toString().toLowerCase().trim();
    // Match by canonical code (e.g. both "TZ" and "Tanzania" -> "tz")
    if (userCode && contestantCode && userCode === contestantCode) return true;
    // Substring match (e.g. "United Republic of Tanzania" contains "Tanzania")
    if (normContestant.includes(normUser) || normUser.includes(normContestant)) return true;
    // No-space substring match
    const noSpaceC = normContestant.replace(/\s+/g, '');
    const noSpaceU = normUser.replace(/\s+/g, '');
    return noSpaceC.includes(noSpaceU) || noSpaceU.includes(noSpaceC);
  };


  // Get contestants based on filter
  const contestants = React.useMemo(() => {
    console.log('Filtering contestants...', {
      showMyCountryOnly,
      userCountry,
      allContestantsCount: allContestants.length
    });

    if (!showMyCountryOnly || !userCountry) {
      console.log('Returning all contestants - filter not active');
      return allContestants;
    }

    const filtered = allContestants.filter(contestant => {
      if (!contestant.country) return false;
      return countriesMatch(userCountry, contestant.country);
    });

    console.log('Filtered contestants:', filtered.length, 'out of', allContestants.length);
    return filtered;
  }, [allContestants, showMyCountryOnly, userCountry]);

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
              {contest?.name || t('dashboard.contests.contestants') || 'Participants'}
            </h1>
            {contest && (
              <p className="text-lg text-gray-600 dark:text-gray-400">
                {contest.contest_type}
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
          </div>

          {/* Contestants Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredContestants.length > 0 ? (
              filteredContestants.map((contestant) => (
                <div key={contestant.id} className="relative">
                  {/* Rank Badge */}
                  {contestant.rank && (
                    <div className="absolute -top-2 -left-2 z-10">
                      <div className={`${getRankBadgeColor(contestant.rank)} border-2 font-bold text-sm px-3 py-1.5 shadow-lg flex items-center gap-1 rounded-full`}>
                        <span>{getRankIcon(contestant.rank)}</span>
                        <span className="hidden sm:inline">
                          {getRankText(contestant.rank)}
                        </span>
                      </div>
                    </div>
                  )}

                  <ContestantCard
                    id={contestant.id}
                    userId={contestant.userId}
                    currentUserId={user?.id}
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
                    onToggleFavorite={() => handleToggleFavorite(contestant.id)}
                    onViewDetails={() => router.push(`/dashboard/contests/${contestId}/contestant/${contestant.id}`)}
                    onVote={() => {
                      // Le vote est géré dans ContestantCard, pas de redirection nécessaire
                    }}
                    onComment={() => { }}
                    onShare={() => { }}
                    onHoverAuthor={() => { }}
                    onHoverEnd={() => { }}
                    onHoverDescription={() => { }}
                    onHoverVotes={() => {
                      // Seul l'auteur peut voir la liste des votes
                      if (user?.id === contestant.userId) {
                        // TODO: Implémenter l'affichage de la liste des votes
                      }
                    }}
                    onHoverReactions={() => { }}
                    onHoverFavorites={() => {
                      // Seul l'auteur peut voir la liste des favoris
                      if (user?.id === contestant.userId) {
                        // TODO: Implémenter l'affichage de la liste des favoris
                      }
                    }}
                  />
                </div>
              ))
            ) : (
              <div className="col-span-full text-center py-12">
                <div className="flex flex-col items-center gap-3">
                  <p className="text-5xl mb-2">🏆</p>
                  <p className="text-lg font-semibold text-gray-700 dark:text-gray-300">
                    {searchQuery
                      ? t('dashboard.contests.no_contestants_found') || 'Aucun participant trouvé'
                      : t('dashboard.contests.no_contestants') || 'Aucun participant pour le moment'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

