import api, { apiService } from '@/lib/api'
import { cacheService } from '@/lib/cache-service'

export interface TopContestant {
  id: number
  user_id?: number  // ID de l'utilisateur qui a créé cette participation
  author_name?: string
  author_avatar_url?: string
  image_url?: string  // Image de soumission du contestant
  votes_count?: number
  rank?: number
}

export interface Contest {
  id: string
  title: string
  description?: string
  coverImage: string
  startDate: Date
  status: 'city' | 'country' | 'regional' | 'continental' | 'global'
  received: number
  contestants: number
  likes: number
  comments: number
  reactions?: number
  favorites?: number
  isOpen: boolean
  contestType?: string
  genderRestriction?: 'male' | 'female' | null
  participationStartDate?: Date
  participationEndDate?: Date
  votingStartDate?: Date
  topContestants?: TopContestant[]
  // Verification requirements
  requiresKyc?: boolean
  verificationType?: 'none' | 'visual' | 'voice' | 'brand' | 'content'
  participantType?: 'individual' | 'pet' | 'club' | 'content'
  requiresVisualVerification?: boolean
  requiresVoiceVerification?: boolean
  requiresBrandVerification?: boolean
  requiresContentVerification?: boolean
  minAge?: number | null
  maxAge?: number | null
  // Media requirements
  requiresVideo?: boolean
  maxVideos?: number
  videoMaxDuration?: number
  videoMaxSizeMb?: number
  minImages?: number
  maxImages?: number
  verificationVideoMaxDuration?: number
  verificationMaxSizeMb?: number
  // Voting type and level for categorization
  votingTypeId?: number | null
  level?: string
  votingType?: {
    id: number
    name: string
    voting_level: string
    commission_source: string
    commission_rules?: any
  } | null
  // Indique si l'utilisateur connecté a déjà participé à ce concours
  currentUserContesting?: boolean
}

export interface ContestResponse {
  id: string
  name: string
  description?: string
  contest_type: string
  cover_image_url?: string
  image_url?: string
  submission_start_date: string
  submission_end_date: string
  voting_start_date: string
  voting_end_date: string
  is_active: boolean
  is_submission_open: boolean
  is_voting_open: boolean
  level: string
  season_level?: string
  location_id?: number
  gender_restriction?: string
  voting_restriction?: string
  max_entries_per_user: number
  template_id?: number
  created_at: string
  updated_at: string
  entries_count?: number
  total_votes?: number
  // Verification requirements
  requires_kyc?: boolean
  verification_type?: string
  participant_type?: string
  requires_visual_verification?: boolean
  requires_voice_verification?: boolean
  requires_brand_verification?: boolean
  requires_content_verification?: boolean
  min_age?: number | null
  max_age?: number | null
  // Media requirements
  requires_video?: boolean
  max_videos?: number
  video_max_duration?: number
  video_max_size_mb?: number
  min_images?: number
  max_images?: number
  verification_video_max_duration?: number
  verification_max_size_mb?: number
  voting_type_id?: number | null
  voting_type?: {
    id: number
    name: string
    voting_level: string
    commission_source: string
    commission_rules?: any
  } | null
  category_id?: number | null
  category?: {
    id: number
    name: string
    slug: string
    description?: string
    is_active: boolean
  } | null
  // Top contestants preview
  top_contestants?: Array<{
    id: number
    author_name?: string
    author_avatar_url?: string
    image_url?: string
    votes_count?: number
    rank?: number
  }>
  // Indique si l'utilisateur connecté a déjà participé à ce concours
  current_user_contesting?: boolean
}

export interface ContestantWithAuthorAndStats {
  id: number
  user_id: number
  season_id: number
  title?: string
  description?: string
  image_media_ids?: string
  video_media_ids?: string
  contestant_image_url?: string
  registration_date: string
  is_qualified: boolean

  // Infos auteur
  author_name?: string
  author_country?: string
  author_city?: string
  author_continent?: string
  author_avatar_url?: string

  // Stats
  rank?: number
  votes_count: number
  images_count: number
  videos_count: number
  favorites_count?: number
  reactions_count?: number
  comments_count?: number

  // Infos du contest
  contest_title?: string
  contest_image_url?: string
  contest_id?: number
  total_participants?: number

  // Position dans les favoris
  position?: number

  // État du vote
  has_voted: boolean
  can_vote: boolean
}

export interface RoundWithStats {
  id: number
  contest_id: number
  name: string
  status: 'upcoming' | 'active' | 'completed' | 'cancelled'
  is_submission_open: boolean
  is_voting_open: boolean
  current_season_level: string | null  // city, country, regional, continental, global, submission, voting
  submission_start_date: string | null
  submission_end_date: string | null
  voting_start_date: string | null
  voting_end_date: string | null
  city_season_start_date: string | null
  city_season_end_date: string | null
  country_season_start_date: string | null
  country_season_end_date: string | null
  regional_start_date: string | null
  regional_end_date: string | null
  continental_start_date: string | null
  continental_end_date: string | null
  global_start_date: string | null
  global_end_date: string | null
  created_at: string
  updated_at: string
  // Stats
  participants_count: number
  current_user_participated: boolean
  is_completed: boolean
}

class ContestService {
  /**
   * Récupère tous les contests avec pagination et recherche (avec cache)
   * @param filterCountry - Filtrer par pays (pour compter les contestants de ce pays)
   * @param filterRegion - Filtrer par région (pour compter les contestants de cette région)
   * @param filterContinent - Filtrer par continent (pour compter les contestants de ce continent)
   */
  async getContests(
    skip: number = 0,
    limit: number = 10,
    search?: string,
    votingLevel?: string,
    votingTypeId?: number | null,
    hasVotingType?: boolean,
    filterCountry?: string,
    filterRegion?: string,
    filterContinent?: string
  ): Promise<ContestResponse[]> {
    try {
      const params: any = { skip, limit }
      if (search) {
        params.search = search
      }
      if (votingLevel) {
        params.voting_level = votingLevel
      }
      if (votingTypeId !== undefined && votingTypeId !== null) {
        params.voting_type_id = votingTypeId
      }
      if (hasVotingType !== undefined) {
        params.has_voting_type = hasVotingType
      }
      if (filterCountry) {
        params.filter_country = filterCountry
      }
      if (filterRegion) {
        params.filter_region = filterRegion
      }
      if (filterContinent) {
        params.filter_continent = filterContinent
      }

      // Vérifier le cache
      const cacheKey = '/api/v1/contests/'
      const cached = cacheService.get<ContestResponse[]>(cacheKey, params)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      console.log('[ContestService] Fetching contests with params:', params)
      const data = await apiService.get<ContestResponse[]>('/api/v1/contests/', params)
      console.log('[ContestService] Received data:', {
        type: Array.isArray(data) ? 'array' : typeof data,
        length: Array.isArray(data) ? data.length : 'N/A',
        sample: Array.isArray(data) && data.length > 0 ? data[0] : null
      })

      // Mettre en cache
      cacheService.set(cacheKey, data, params)

      return data
    } catch (error: any) {
      console.error('[ContestService] Error fetching contests:', error)
      console.error('[ContestService] Error details:', {
        message: error?.message,
        response: error?.response?.data,
        status: error?.response?.status,
        url: error?.config?.url
      })
      throw error
    }
  }

  /**
   * Récupère un contest par son ID avec ses participants
   */
  async getContestById(contestId: string): Promise<ContestResponse> {
    try {
      const response = await api.get(`/api/v1/contests/${contestId}`)
      return response.data
    } catch (error) {
      console.error(`Error fetching contest ${contestId}:`, error)
      throw error
    }
  }

  /**
   * Récupère les rounds d'un contest avec leurs statistiques
   * Inclut le nombre de participants et si l'utilisateur actuel a participé
   */
  async getRoundsForContest(contestId: string): Promise<RoundWithStats[]> {
    try {
      const cacheKey = `/api/v1/rounds/`
      const params = { contest_id: contestId }

      // Vérifier le cache
      const cached = cacheService.get<RoundWithStats[]>(cacheKey, params)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey, { params })

      // Mettre en cache
      cacheService.set(cacheKey, response.data, params)

      return response.data
    } catch (error) {
      console.error(`Error fetching rounds for contest ${contestId}:`, error)
      throw error
    }
  }

  /**
   * Crée un nouveau contest (admin uniquement)
   */
  async createContest(contestData: Partial<ContestResponse>): Promise<ContestResponse> {
    try {
      const result = await apiService.post<ContestResponse>('/api/v1/contests/', contestData, '/api/v1/contests/')

      // Invalider le cache des contests
      cacheService.invalidate('/api/v1/contests/')

      return result
    } catch (error) {
      console.error('Error creating contest:', error)
      throw error
    }
  }

  /**
   * Met à jour un contest (admin uniquement)
   */
  async updateContest(contestId: string, contestData: Partial<ContestResponse>): Promise<ContestResponse> {
    try {
      const result = await apiService.put<ContestResponse>(`/api/v1/contests/${contestId}`, contestData, '/api/v1/contests/')

      // Invalider le cache du contest spécifique et de la liste
      cacheService.invalidate(`/api/v1/contests/${contestId}`)
      cacheService.invalidate('/api/v1/contests/')

      return result
    } catch (error) {
      console.error(`Error updating contest ${contestId}:`, error)
      throw error
    }
  }

  /**
   * Supprime un contest (admin uniquement)
   */
  async deleteContest(contestId: string): Promise<void> {
    try {
      await apiService.delete<void>(`/api/v1/contests/${contestId}`, '/api/v1/contests/')

      // Invalider le cache du contest spécifique et de la liste
      cacheService.invalidate(`/api/v1/contests/${contestId}`)
      cacheService.invalidate('/api/v1/contests/')
    } catch (error) {
      console.error(`Error deleting contest ${contestId}:`, error)
      throw error
    }
  }

  /**
   * Soumet une candidature à un contest
   */
  async submitContestant(
    contestId: string,
    title: string,
    description: string,
    imageMediaIds?: string,
    videoMediaIds?: string,
    nominatorCity?: string,
    nominatorCountry?: string
  ): Promise<any> {
    try {
      // Prepare request body - only include fields that have values
      const requestBody: any = {
        title: title,
        description: description
      }

      // Only include optional fields if they have values
      if (imageMediaIds) {
        requestBody.image_media_ids = imageMediaIds
      }
      if (videoMediaIds) {
        requestBody.video_media_ids = videoMediaIds
      }
      if (nominatorCity && nominatorCity.trim()) {
        requestBody.nominator_city = nominatorCity.trim()
      }
      if (nominatorCountry && nominatorCountry.trim()) {
        requestBody.nominator_country = nominatorCountry.trim()
      }

      console.log('Submitting contestant with data:', {
        contestId,
        title,
        description,
        hasImages: !!imageMediaIds,
        hasVideos: !!videoMediaIds,
        nominatorCity: nominatorCity || 'not provided',
        nominatorCountry: nominatorCountry || 'not provided'
      })

      const response = await api.post(`/api/v1/contestants/${contestId}`, requestBody)

      // Invalider le cache des contestants et du contest
      cacheService.invalidate(`/api/v1/contestants/contest/${contestId}`)
      cacheService.invalidate(`/api/v1/contests/${contestId}`)
      cacheService.invalidate('/api/v1/contests/')

      return response.data
    } catch (error: any) {
      console.error(`Error submitting contestant for contest ${contestId}:`, error)
      console.error('Error response data:', error?.response?.data)
      console.error('Error response status:', error?.response?.status)
      throw error
    }
  }

  /**
   * Met à jour une candidature existante
   */
  async updateContestant(
    contestantId: number,
    title: string,
    description: string,
    imageMediaIds?: string,
    videoMediaIds?: string,
    nominatorCity?: string,
    nominatorCountry?: string
  ): Promise<any> {
    try {
      const response = await api.put(`/api/v1/contestants/${contestantId}`, {
        title: title,
        description: description,
        image_media_ids: imageMediaIds,
        video_media_ids: videoMediaIds,
        nominator_city: nominatorCity,
        nominator_country: nominatorCountry
      })

      // Invalider le cache du contestant, de la liste des contestants et du contest
      cacheService.invalidate(`/api/v1/contestants/${contestantId}`)
      cacheService.invalidate('/api/v1/contestants/contest/')
      cacheService.invalidate('/api/v1/contests/')

      return response.data
    } catch (error) {
      console.error(`Error updating contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Ajoute une soumission (média) à une candidature
   */
  async addSubmission(
    contestantId: number,
    mediaType: string,
    fileUrl: string,
    title?: string,
    description?: string
  ): Promise<any> {
    try {
      const response = await api.post(`/api/v1/contestants/${contestantId}/submission`, null, {
        params: {
          media_type: mediaType,
          file_url: fileUrl,
          title,
          description
        }
      })

      // Invalider le cache du contestant et de la liste des contestants
      cacheService.invalidate(`/api/v1/contestants/${contestantId}`)
      cacheService.invalidate('/api/v1/contestants/contest/')

      return response.data
    } catch (error) {
      console.error(`Error adding submission for contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Récupère un contestant par son ID avec infos auteur et stats
   */
  async getContestantById(contestantId: number): Promise<ContestantWithAuthorAndStats | null> {
    try {
      const response = await api.get(`/api/v1/contestants/${contestantId}`)
      console.log(`Contestant ${contestantId} fetched:`, response.data)
      return response.data
    } catch (error) {
      console.error(`Error fetching contestant ${contestantId}:`, error)
      return null
    }
  }

  /**
   * Récupère les candidatures d'un contest avec infos auteur et stats enrichies
   * @param filterCountry - Filtrer par pays
   * @param filterRegion - Filtrer par région
   * @param filterContinent - Filtrer par continent
   */
  async getContestantsByContest(
    contestId: string,
    skip: number = 0,
    limit: number = 10,
    filterCountry?: string,
    filterRegion?: string,
    filterContinent?: string,
    filterCity?: string,
    userId?: number | string
  ): Promise<ContestantWithAuthorAndStats[]> {
    try {
      const cacheKey = `/api/v1/contestants/contest/${contestId}`
      const params: any = { skip, limit }

      if (filterCountry) {
        params.filter_country = filterCountry
      }
      if (filterRegion) {
        params.filter_region = filterRegion
      }
      if (filterContinent) {
        params.filter_continent = filterContinent
      }
      if (filterCity) {
        params.filter_city = filterCity
      }
      if (userId) {
        params.user_id = userId
      }

      // Vérifier le cache
      const cached = cacheService.get<ContestantWithAuthorAndStats[]>(cacheKey, params)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey, { params })

      // Mettre en cache
      cacheService.set(cacheKey, response.data, params)

      return response.data
    } catch (error: any) {
      console.error(`Error fetching contestants for contest ${contestId}:`, error)
      if (error.response) {
        console.error('Response error detail:', error.response.data)
      }
      throw error
    }
  }

  /**
   * Ajoute un contestant aux favoris
   */
  async addToFavorites(contestantId: number): Promise<void> {
    try {
      await api.post(`/api/v1/contestants/${contestantId}/favorite`)

      // Invalider le cache des favoris et du contestant
      cacheService.invalidate('/api/v1/contestants/favorites')
      cacheService.invalidate(`/api/v1/contestants/${contestantId}`)
    } catch (error) {
      console.error(`Error adding contestant ${contestantId} to favorites:`, error)
      throw error
    }
  }

  /**
   * Retire un contestant des favoris
   */
  async removeFromFavorites(contestantId: number): Promise<void> {
    try {
      await api.delete(`/api/v1/contestants/${contestantId}/favorite`)

      // Invalider le cache des favoris et du contestant
      cacheService.invalidate('/api/v1/contestants/favorites')
      cacheService.invalidate(`/api/v1/contestants/${contestantId}`)
    } catch (error) {
      console.error(`Error removing contestant ${contestantId} from favorites:`, error)
      throw error
    }
  }

  /**
   * Supprime une candidature (l'utilisateur peut supprimer sa propre candidature)
   */
  async deleteContestant(contestantId: number): Promise<void> {
    try {
      await api.delete(`/api/v1/contestants/${contestantId}`)

      // Invalider le cache du contestant et de la liste des contestants
      cacheService.invalidate(`/api/v1/contestants/${contestantId}`)
      cacheService.invalidate('/api/v1/contestants/contest/')
      cacheService.invalidate('/api/v1/contests/')
    } catch (error) {
      console.error(`Error deleting contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Récupère les favoris de l'utilisateur courant
   */
  async getUserFavorites(): Promise<number[]> {
    try {
      const cacheKey = '/api/v1/contestants/favorites'

      // Vérifier le cache
      const cached = cacheService.get<number[]>(cacheKey)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey)

      // Mettre en cache
      cacheService.set(cacheKey, response.data)

      return response.data
    } catch (error) {
      console.error('Error fetching user favorites:', error)
      throw error
    }
  }

  /**
   * Récupérer les détails des votes avec les noms des utilisateurs
   */
  async getVoteDetails(contestantId: number): Promise<any> {
    try {
      const response = await api.get(`/api/v1/contestants/${contestantId}/votes/details`)
      return response.data
    } catch (error) {
      console.error(`Error fetching vote details for contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Récupère les votes MyHigh5 de l'utilisateur courant (saisons actives uniquement)
   * Retourne les 5 contestants pour lesquels l'utilisateur a voté, groupés par season
   */
  async getMyHigh5Votes(): Promise<any> {
    try {
      const cacheKey = '/api/v1/contestants/user/my-votes'

      // Vérifier le cache
      const cached = cacheService.get<any>(cacheKey)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey)

      // Mettre en cache
      cacheService.set(cacheKey, response.data)

      return response.data
    } catch (error) {
      console.error('Error fetching MyHigh5 votes:', error)
      throw error
    }
  }

  /**
   * Récupère l'historique complet des votes MyHigh5 de l'utilisateur
   * Inclut toutes les saisons (actives et inactives), groupées par contestant
   */
  async getMyHigh5VotesHistory(contestId?: number): Promise<any> {
    try {
      const cacheKey = '/api/v1/contestants/user/my-votes/history'
      const params = contestId ? { contest_id: contestId } : {}

      // Vérifier le cache
      const cached = cacheService.get<any>(cacheKey, params)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey, { params })

      // Mettre en cache
      cacheService.set(cacheKey, response.data, params)

      return response.data
    } catch (error) {
      console.error('Error fetching MyHigh5 votes history:', error)
      throw error
    }
  }

  /**
   * Réordonne les votes MyHigh5 de l'utilisateur pour une season donnée
   * Le 1er reçoit 5 points, le 2ème 4 points, etc.
   */
  async reorderMyHigh5Votes(
    votes: Array<{ contestant_id: number; position: number }>,
    seasonId: number
  ): Promise<void> {
    try {
      await api.put('/api/v1/contestants/user/my-votes/reorder', {
        votes,
        season_id: seasonId
      })

      // Invalider le cache des votes MyHigh5
      cacheService.invalidate('/api/v1/contestants/user/my-votes')
      cacheService.invalidate('/api/v1/contestants/user/my-votes/history')
    } catch (error) {
      console.error('Error reordering MyHigh5 votes:', error)
      throw error
    }
  }

  /**
   * Récupérer les détails des favoris avec les noms des utilisateurs
   */
  async getFavoriteDetails(contestantId: number): Promise<any> {
    try {
      const response = await api.get(`/api/v1/contestants/${contestantId}/favorites/details`)
      return response.data
    } catch (error) {
      console.error(`Error fetching favorite details for contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Sauvegarde l'ordre des favoris
   */
  async reorderFavorites(favorites: Array<{ contestant_id: number; position: number }>): Promise<void> {
    try {
      console.log('[REORDER] Sending favorites to backend:', favorites)
      const response = await api.put('/api/v1/favorites/contestants/reorder', {
        favorites
      })
      console.log('[REORDER] Response:', response.data)
      console.log('Favorites reordered successfully')

      // Invalider le cache des favoris
      cacheService.invalidate('/api/v1/contestants/favorites')
    } catch (error) {
      console.error('[REORDER] Error reordering favorites:', error)
      throw error
    }
  }

  /**
   * Récupère le classement d'un contest
   */
  async getContestLeaderboard(
    contestId: string,
    skip: number = 0,
    limit: number = 10
  ): Promise<any[]> {
    try {
      const cacheKey = `/api/v1/contestants/leaderboard/contest/${contestId}`
      const params = { skip, limit }

      // Vérifier le cache
      const cached = cacheService.get<any[]>(cacheKey, params)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey, { params })

      // Mettre en cache
      cacheService.set(cacheKey, response.data, params)

      return response.data
    } catch (error) {
      console.error(`Error fetching leaderboard for contest ${contestId}:`, error)
      throw error
    }
  }

  /**
   * Vote pour une candidature
   */
  async voteForContestant(contestantId: number, score: number = 5): Promise<any> {
    try {
      const response = await api.post(`/api/v1/contestants/${contestantId}/vote`)

      // Invalider le cache du contestant, du leaderboard et du contest
      cacheService.invalidate(`/api/v1/contestants/${contestantId}`)
      cacheService.invalidate('/api/v1/contestants/leaderboard/')
      cacheService.invalidate('/api/v1/contestants/contest/')
      cacheService.invalidate('/api/v1/contests/')

      return response.data
    } catch (error: any) {
      console.error(`Error voting for contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Participe à un contest (ancienne méthode - gardée pour compatibilité)
   */
  async participateInContest(contestId: string, mediaId: number): Promise<any> {
    try {
      const response = await api.post(`/api/v1/contests/${contestId}/entry`, {
        media_id: mediaId
      })
      return response.data
    } catch (error) {
      console.error(`Error participating in contest ${contestId}:`, error)
      throw error
    }
  }

  /**
   * Récupère les contests filtrés
   */
  async getContestsWithFilters(
    filters: {
      location_id?: number
      contest_type?: string
      active?: boolean
    },
    skip: number = 0,
    limit: number = 10
  ): Promise<ContestResponse[]> {
    try {
      const cacheKey = '/api/v1/contests'
      const params = { ...filters, skip, limit }

      // Vérifier le cache
      const cached = cacheService.get<ContestResponse[]>(cacheKey, params)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey, { params })

      // Mettre en cache
      cacheService.set(cacheKey, response.data, params)

      return response.data
    } catch (error) {
      console.error('Error fetching filtered contests:', error)
      throw error
    }
  }

  /**
   * Ajoute un contest aux favoris
   */
  async addContestFavorite(contestId: string): Promise<void> {
    try {
      await api.post(`/api/v1/favorites/contests/${contestId}`)

      // Invalider le cache des favoris de contests
      cacheService.invalidate('/api/v1/favorites/contests')
      cacheService.invalidate(`/api/v1/favorites/contests/${contestId}/is-favorite`)
    } catch (error) {
      console.error('Erreur lors de l\'ajout du contest aux favoris:', error)
      throw error
    }
  }

  /**
   * Retire un contest des favoris
   */
  async removeContestFavorite(contestId: string): Promise<void> {
    try {
      await api.delete(`/api/v1/favorites/contests/${contestId}`)

      // Invalider le cache des favoris de contests
      cacheService.invalidate('/api/v1/favorites/contests')
      cacheService.invalidate(`/api/v1/favorites/contests/${contestId}/is-favorite`)
    } catch (error) {
      console.error('Erreur lors de la suppression du contest des favoris:', error)
      throw error
    }
  }

  /**
   * Récupère les contests favoris de l'utilisateur
   */
  async getFavoritesContests(skip: number = 0, limit: number = 100): Promise<ContestResponse[]> {
    try {
      const cacheKey = '/api/v1/favorites/contests'
      const params = { skip, limit }

      // Vérifier le cache
      const cached = cacheService.get<ContestResponse[]>(cacheKey, params)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey, { params })

      // Mettre en cache
      cacheService.set(cacheKey, response.data, params)

      return response.data
    } catch (error) {
      console.error('Erreur lors du chargement des contests favoris:', error)
      return []
    }
  }

  /**
   * Vérifie si un contest est dans les favoris
   */
  async isContestFavorite(contestId: string): Promise<boolean> {
    try {
      const cacheKey = `/api/v1/favorites/contests/${contestId}/is-favorite`

      // Vérifier le cache
      const cached = cacheService.get<{ is_favorite: boolean }>(cacheKey)
      if (cached) {
        return cached.is_favorite
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey)

      // Mettre en cache
      cacheService.set(cacheKey, response.data)

      return response.data.is_favorite
    } catch (error) {
      console.error('Erreur lors de la vérification du favori:', error)
      return false
    }
  }

  /**
   * Convertit une réponse API en objet Contest pour l'affichage
   */
  mapResponseToContest(response: ContestResponse): Contest {
    // Utiliser season_level si disponible, sinon utiliser level
    const level = response.season_level || response.level || 'country'

    // Le contest est ouvert pour candidater si le backend dit is_submission_open: true
    // On fait confiance au backend pour gérer les dates
    // FIXED: Handle missing date fields gracefully (they may not exist in database)
    const now = new Date()
    const submissionStart = (response.submission_start_date && response.submission_start_date !== 'null') 
      ? new Date(response.submission_start_date) 
      : null
    const submissionEnd = (response.submission_end_date && response.submission_end_date !== 'null')
      ? new Date(response.submission_end_date) 
      : null
    const votingStart = (response.voting_start_date && response.voting_start_date !== 'null')
      ? new Date(response.voting_start_date) 
      : null

    // Faire confiance au backend pour la valeur de is_submission_open
    const isOpen = response.is_submission_open || false

    // Gérer la couverture : utiliser image_url en priorité, puis cover_image_url, sinon emoji
    let coverImage = response.image_url || response.cover_image_url || ''

    // Si l'image existe, s'assurer qu'elle est une URL valide
    if (coverImage && coverImage.trim() !== '') {
      // Vérifier si c'est un emoji (caractère unicode haut)
      const firstCodePoint = coverImage.codePointAt(0) || 0
      const isEmoji = coverImage.length <= 4 && firstCodePoint > 0x1F000

      // Si ce n'est pas un emoji et que ce n'est pas déjà une URL complète
      if (!isEmoji && !coverImage.startsWith('http') && !coverImage.startsWith('data:')) {
        // Si c'est un chemin relatif, construire l'URL complète
        if (coverImage.startsWith('/')) {
          const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          coverImage = `${API_BASE_URL}${coverImage}`
        } else {
          // Sinon, essayer de construire l'URL
          const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
          coverImage = `${API_BASE_URL}/${coverImage}`
        }
      }
    }

    // Si toujours pas d'image valide, utiliser l'emoji
    if (!coverImage || coverImage.trim() === '' || (!coverImage.startsWith('http') && !coverImage.startsWith('/') && !coverImage.startsWith('data:'))) {
      coverImage = this.getEmojiForType(response.contest_type)
    }

    return {
      id: String(response.id),
      title: response.name,
      coverImage: coverImage,
      startDate: submissionStart || new Date(),
      status: (level as 'city' | 'country' | 'regional' | 'continental' | 'global') || 'country',
      received: response.total_votes || 0, // Nombre total de votes
      contestants: response.entries_count || 0, // Nombre de participants
      likes: 0, // À implémenter plus tard
      comments: 0, // À implémenter plus tard
      isOpen: isOpen,
      contestType: response.contest_type,
      genderRestriction: (() => {
        // Priorité: gender_restriction, puis voting_restriction
        let restriction = response.gender_restriction

        // Si pas de gender_restriction, essayer de l'extraire de voting_restriction
        if (!restriction && response.voting_restriction) {
          const votingRestriction = String(response.voting_restriction).toLowerCase().trim()
          if (votingRestriction === 'male_only') {
            restriction = 'male'
          } else if (votingRestriction === 'female_only') {
            restriction = 'female'
          }
        }

        // Vérifier aussi si gender_restriction est directement 'male' ou 'female'
        if (restriction && typeof restriction === 'string' && restriction.trim() !== '') {
          const normalized = restriction.toLowerCase().trim()
          if (normalized === 'male' || normalized === 'female') {
            return normalized as 'male' | 'female'
          }
        }
        return null
      })(),
      participationStartDate: submissionStart || undefined,
      participationEndDate: submissionEnd || undefined,
      votingStartDate: votingStart || undefined,
      // Verification requirements - KYC n'est PAS requis par défaut
      requiresKyc: response.requires_kyc ?? false,
      verificationType: (response.verification_type as 'none' | 'visual' | 'voice' | 'brand' | 'content') || 'none',
      participantType: (response.participant_type as 'individual' | 'pet' | 'club' | 'content') || 'individual',
      requiresVisualVerification: response.requires_visual_verification ?? false,
      requiresVoiceVerification: response.requires_voice_verification ?? false,
      requiresBrandVerification: response.requires_brand_verification ?? false,
      requiresContentVerification: response.requires_content_verification ?? false,
      minAge: response.min_age ?? null,
      maxAge: response.max_age ?? null,
      // Media requirements
      requiresVideo: response.requires_video ?? false,
      maxVideos: response.max_videos ?? 1,
      videoMaxDuration: response.video_max_duration ?? 3000,
      videoMaxSizeMb: response.video_max_size_mb ?? 500,
      minImages: response.min_images ?? 0,
      maxImages: response.max_images ?? 10,
      verificationVideoMaxDuration: response.verification_video_max_duration ?? 30,
      verificationMaxSizeMb: response.verification_max_size_mb ?? 50,
      // Voting type and level for categorization
      votingTypeId: response.voting_type_id ?? null,
      level: response.season_level || response.level || 'country',
      votingType: response.voting_type ?? null,
      // Top contestants preview
      topContestants: response.top_contestants?.map((c, index) => ({
        id: c.id,
        author_name: c.author_name,
        author_avatar_url: c.author_avatar_url,
        image_url: c.image_url,
        votes_count: c.votes_count,
        rank: c.rank ?? (index + 1)
      })) || [],
      // Indique si l'utilisateur connecté a déjà participé
      currentUserContesting: response.current_user_contesting ?? false
    }
  }

  /**
   * Retourne un emoji basé sur le type de contest
   */
  private getEmojiForType(type: string): string {
    const emojiMap: Record<string, string> = {
      'beauty': '👑',
      'handsome': '🤴',
      'latest_hits': '🌟',
      'talent': '✨',
      'photography': '📸',
      'default': '💎'
    }
    return emojiMap[type] || emojiMap['default']
  }

  /**
   * Crée une suggestion de concours
   */
  async createSuggestedContest(data: {
    name: string
    description?: string
    category: string
  }): Promise<any> {
    try {
      const response = await api.post('/api/v1/suggested-contests', {
        name: data.name.trim(),
        description: data.description?.trim() || null,
        category: data.category.trim(),
        status: 'pending'
      })

      // Invalider le cache des suggestions si nécessaire
      cacheService.invalidate('/api/v1/suggested-contests')

      return response.data
    } catch (error: any) {
      console.error('Error creating suggested contest:', error)
      // Propager l'erreur avec plus de détails
      const errorMessage = error.response?.data?.detail || error.message || 'Erreur lors de la création de la suggestion'
      throw new Error(errorMessage)
    }
  }

  /**
   * Signale un contestant
   */
  async reportContestant(contestantId: number, contestId: number, data: {
    reason: string
    description: string
  }): Promise<any> {
    try {
      const response = await api.post(`/api/v1/contestants/${contestantId}/report`, {
        contestant_id: contestantId,
        contest_id: contestId,
        reason: data.reason.trim(),
        description: data.description.trim()
      })

      // Invalider le cache du contestant signalé
      cacheService.invalidate(`/api/v1/contestants/${contestantId}`)

      return response.data
    } catch (error: any) {
      console.error('Error reporting contestant:', error)
      const errorMessage = error.response?.data?.detail || error.message || 'Erreur lors du signalement'
      throw new Error(errorMessage)
    }
  }
}

export const contestService = new ContestService()
