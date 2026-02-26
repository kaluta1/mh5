import api, { apiService } from '@/lib/api'
import { cacheService } from '@/lib/cache-service'

export interface Contestant {
  id: number
  user_id: number
  contest_id: number
  title: string
  description?: string
  image_media_ids?: string
  video_media_ids?: string
  status: 'pending' | 'approved' | 'rejected'
  is_qualified: boolean
  votes_count: number
  rank?: number
  created_at: string
  updated_at: string
  author_name?: string
  author_avatar_url?: string
  author_country?: string
  author_city?: string
  author_continent?: string
  contestant_image_url?: string
}

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
  id: string | number
  title: string
  name?: string
  description?: string
  coverImage: string
  startDate: Date
  status: 'city' | 'country' | 'regional' | 'continental' | 'global'
  received: number
  contestants: number
  participant_count?: number
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
  votingEndDate?: Date
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
  // Basic contest information
  id: string | number
  name: string
  description?: string
  contest_type: string
  cover_image_url?: string
  image_url?: string
  status?: string

  // Dates
  start_date?: string
  end_date?: string
  submission_start_date?: string
  submission_end_date?: string
  voting_start_date?: string
  voting_end_date?: string
  created_at?: string
  updated_at?: string
  active_round_id?: number | null

  // Contest settings
  is_active?: boolean
  is_public?: boolean
  is_submission_open?: boolean
  is_voting_open?: boolean
  max_participants?: number
  max_entries_per_user?: number

  // Age and gender restrictions
  min_age?: number | null
  max_age?: number | null
  gender_restriction?: 'male' | 'female' | null

  // Verification requirements
  requires_kyc?: boolean
  verification_type?: 'none' | 'visual' | 'voice' | 'brand' | 'content'
  participant_type?: 'individual' | 'pet' | 'club' | 'content'
  requires_visual_verification?: boolean
  requires_voice_verification?: boolean
  requires_brand_verification?: boolean
  requires_content_verification?: boolean

  // Media requirements
  requires_video?: boolean
  max_videos?: number
  video_max_duration?: number
  video_max_size_mb?: number
  min_images?: number
  max_images?: number
  verification_video_max_duration?: number
  verification_max_size_mb?: number

  // Voting and commission
  voting_type_id?: number | null
  voting_restriction?: string

  // Location and category
  location_id?: number | null
  season_level?: string
  category_id?: number | null
  template_id?: number | null

  // Category details
  category?: {
    id: number
    name: string
    slug: string
    description?: string
    is_active: boolean
  } | null

  // Voting type details
  voting_type?: {
    id: number
    name: string
    voting_level: string
    commission_source: string
    commission_rules?: any
  } | null
  top_contestants?: Array<{
    id: number
    user_id?: number
    author_name?: string
    author_avatar_url?: string
    image_url?: string
    votes_count?: number
    rank?: number
  }>
  contestants?: Contestant[]
  current_user_contesting?: boolean
  entries_count?: number
  total_votes?: number
  level?: string
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
  author_name?: string
  author_country?: string
  author_city?: string
  author_continent?: string
  author_avatar_url?: string
  rank?: number
  votes_count: number
  images_count: number
  videos_count: number
  favorites_count?: number
  reactions_count?: number
  comments_count?: number
  shares_count?: number
  contest_title?: string
  contest_level?: string
  contest_image_url?: string
  contest_id?: number
  total_participants?: number
  position?: number
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
  current_season_level: string | null
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
  participants_count: number
  current_user_participated: boolean
  is_completed: boolean
}

class ContestService {
  async addToFavorites(id: string | number, type: 'contest' | 'contestant' = 'contest'): Promise<void> {
    try {
      if (type === 'contest') {
        const cacheKey = `/api/v1/favorites/contests/${id}`;
        await api.post(cacheKey);
        cacheService.invalidate(`/api/v1/favorites/contests/${id}/is-favorite`);
        cacheService.invalidate('/api/v1/favorites/contests');
      } else {
        await api.post(`/api/v1/contestants/${id}/favorite`);
        cacheService.invalidate(`/api/v1/contestants/${id}`);
        cacheService.invalidate('/api/v1/contestants/favorites');
      }
    } catch (error) {
      console.error(`Error adding ${type} ${id} to favorites:`, error);
      throw error;
    }
  }

  async removeFromFavorites(id: string | number, type: 'contest' | 'contestant' = 'contest'): Promise<void> {
    try {
      if (type === 'contest') {
        const cacheKey = `/api/v1/favorites/contests/${id}`;
        await api.delete(cacheKey);
        cacheService.invalidate(`/api/v1/favorites/contests/${id}/is-favorite`);
        cacheService.invalidate('/api/v1/favorites/contests');
      } else {
        await api.delete(`/api/v1/contestants/${id}/favorite`);
        cacheService.invalidate(`/api/v1/contestants/${id}`);
        cacheService.invalidate('/api/v1/contestants/favorites');
      }
    } catch (error) {
      console.error(`Error removing ${type} ${id} from favorites:`, error);
      throw error;
    }
  }

  async getContestById(contestId: string | number): Promise<Contest> {
    try {
      const cacheKey = `/api/v1/contests/${contestId}`;
      const cached = cacheService.get<ContestResponse>(cacheKey);
      if (cached) {
        return this.mapResponseToContest(cached);
      }

      const response = await api.get<ContestResponse>(cacheKey);
      cacheService.set(cacheKey, response.data);
      return this.mapResponseToContest(response.data);
    } catch (error) {
      console.error(`Error fetching contest ${contestId}:`, error);
      throw error;
    }
  }

  async addContestFavorite(contestId: string): Promise<void> {
    return this.addToFavorites(contestId, 'contest');
  }

  async removeContestFavorite(contestId: string): Promise<void> {
    return this.removeFromFavorites(contestId, 'contest');
  }

  private getEmojiForType(type: string): string {
    const emojiMap: Record<string, string> = {
      'beauty': '👑',
      'handsome': '🤴',
      'latest_hits': '🌟',
      'talent': '✨',
      'photography': '📸',
      'default': '💎'
    };
    return emojiMap[type] || emojiMap['default'];
  }

  /**
   * Map a contest response to a contest object
   */
  public mapResponseToContest(response: ContestResponse): Contest {
    // Convert dates
    const submissionStart = response.submission_start_date ? new Date(response.submission_start_date) : undefined;
    const submissionEnd = response.submission_end_date && response.submission_end_date !== 'null'
      ? new Date(response.submission_end_date)
      : undefined;
    const votingStart = response.voting_start_date && response.voting_start_date !== 'null'
      ? new Date(response.voting_start_date)
      : undefined;
    const votingEnd = response.voting_end_date && response.voting_end_date !== 'null'
      ? new Date(response.voting_end_date)
      : undefined;
    const startDate = response.start_date ? new Date(response.start_date) : new Date();
    const endDate = response.end_date ? new Date(response.end_date) : undefined;

    // Process cover image
    let coverImage = response.cover_image_url || response.image_url || '';

    // If image exists, ensure it's a valid URL or emoji
    if (coverImage.trim() !== '') {
      const firstCodePoint = coverImage.codePointAt(0) || 0;
      const isEmoji = coverImage.length <= 4 && firstCodePoint > 0x1F000;

      if (!isEmoji && !coverImage.startsWith('http')) {
        // If it's not an emoji and not a complete URL, prepend base URL
        const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        if (coverImage.startsWith('/')) {
          coverImage = `${API_BASE_URL}${coverImage}`;
        } else if (coverImage.trim() !== '') {
          coverImage = `${API_BASE_URL}/${coverImage}`;
        }
      }

      // If still no valid image, use an emoji
      if (!coverImage || coverImage.trim() === '' || (!coverImage.startsWith('http') && !coverImage.startsWith('/') && !coverImage.startsWith('data:'))) {
        coverImage = this.getEmojiForType(response.contest_type);
      }
    } else {
      // If no image, use an emoji
      coverImage = this.getEmojiForType(response.contest_type);
    }

    // Determine contest status
    const now = new Date();
    const isSubmissionOpen = submissionStart && (!submissionEnd || now <= submissionEnd);
    const isVotingOpen = votingStart && votingEnd ? (votingStart <= now && now <= votingEnd) : false;
    const isOpen = isSubmissionOpen || isVotingOpen;

    // Determine contest status level
    const status = (response.status as 'city' | 'country' | 'regional' | 'continental' | 'global') || 'city';

    // Map verification type
    const verificationType = response.verification_type || 'none';

    // Map voting type if available
    const votingType = response.voting_type ? {
      id: response.voting_type.id,
      name: response.voting_type.name,
      voting_level: response.voting_type.voting_level,
      commission_source: response.voting_type.commission_source,
      commission_rules: response.voting_type.commission_rules
    } : null;

    // Map top contestants if available
    const topContestants = (response.top_contestants || []).map(contestant => ({
      id: contestant.id,
      user_id: contestant.user_id || 0,
      author_name: contestant.author_name || '',
      author_avatar_url: contestant.author_avatar_url || '',
      image_url: contestant.image_url || '',
      votes_count: contestant.votes_count || 0,
      rank: contestant.rank || 0
    }));

    // Create the Contest object
    return {
      id: String(response.id),
      title: response.name || '',
      name: response.name || '',
      description: response.description || '',
      coverImage,
      startDate,
      status,
      received: response.entries_count || 0,
      contestants: response.contestants?.length || 0,
      likes: 0,
      comments: 0,
      reactions: 0,
      favorites: 0,
      isOpen,
      contestType: response.contest_type || '',
      genderRestriction: response.gender_restriction || null,
      participationStartDate: submissionStart,
      participationEndDate: submissionEnd,
      votingStartDate: votingStart,
      votingEndDate: votingEnd,
      requiresKyc: response.requires_kyc || false,
      verificationType,
      // Participant and verification requirements
      participantType: response.participant_type || 'individual',
      requiresVisualVerification: verificationType === 'visual',
      requiresVoiceVerification: verificationType === 'voice',
      requiresBrandVerification: verificationType === 'brand',
      requiresContentVerification: verificationType === 'content',
      minAge: response.min_age || null,
      maxAge: response.max_age || null,

      // Media requirements
      requiresVideo: response.requires_video || false,
      maxVideos: response.max_videos || 1,
      videoMaxDuration: response.video_max_duration || 300,
      videoMaxSizeMb: response.video_max_size_mb || 50,
      minImages: response.min_images || 1,
      maxImages: response.max_images || 10,
      verificationVideoMaxDuration: response.verification_video_max_duration || 60,
      verificationMaxSizeMb: response.verification_max_size_mb || 20,

      // Voting and contest details
      votingTypeId: response.voting_type_id || null,
      level: response.voting_type?.voting_level || response.season_level || 'country',
      currentUserContesting: response.current_user_contesting || false,
      votingType,
      topContestants: response.top_contestants?.map(t => ({
        id: t.id,
        user_id: t.user_id,
        author_name: t.author_name,
        author_avatar_url: t.author_avatar_url,
        image_url: t.image_url,
        votes_count: t.votes_count,
        rank: t.rank
      })) || []
    };
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

  /**
   * Récupère un participant par son ID
   */
  async getContestant(contestantId: number): Promise<ContestantWithAuthorAndStats> {
    try {
      const response = await api.get<ContestantWithAuthorAndStats>(`/api/v1/contestants/${contestantId}`);
      return response.data;
    } catch (error) {
      console.error('Error fetching contestant:', error);
      throw error;
    }
  }

  /**
   * Récupère la liste des concours avec pagination et recherche
   */
  async getContests(
    skip: number = 0,
    limit: number = 10,
    searchTerm?: string,
    votingLevel?: string,
    votingTypeId?: number,
    hasVotingType?: boolean
  ): Promise<{ contests: Contest[]; total: number }> {
    try {
      const params: any = {
        skip,
        limit,
        ...(searchTerm && { search: searchTerm }),
        ...(votingLevel && { voting_level: votingLevel }),
        ...(votingTypeId && { voting_type_id: votingTypeId }),
        ...(hasVotingType !== undefined && { has_voting_type: hasVotingType })
      };

      console.log('[ContestService] Fetching contests with params:', params);

      // Backend returns List[dict] directly, not wrapped in { items, total }
      const response = await api.get<ContestResponse[]>('/api/v1/contests', { params });

      // Handle both response formats (direct array or wrapped)
      const contestsArray = Array.isArray(response.data)
        ? response.data
        : (response.data as any)?.items || [];
      const total = (response.data as any)?.total || contestsArray.length;

      return {
        contests: contestsArray.map(contest => this.mapResponseToContest(contest)),
        total: total
      };
    } catch (error) {
      console.error('Error fetching contests:', error);
      throw error;
    }
  }

  /**
   * Get all rounds for a specific contest
   * @param contestId - The ID of the contest
   * @returns Promise with an array of rounds
   */
  async getRoundsForContest(contestId: string | number): Promise<RoundWithStats[]> {
    try {
      type ApiResponse = {
        data: RoundWithStats[];
      };

      const response = await api.get<ApiResponse>(`/api/v1/contests/${contestId}/rounds`);
      return Array.isArray(response?.data) ? response.data : [];
    } catch (error) {
      console.error('Error fetching contest rounds:', error);
      return [];
    }
  }

  /**
   * Submit a new contestant entry
   */
  async submitContestant(
    contestId: string | number,
    title: string,
    description: string,
    imageMediaIds: string | string[] = [],
    videoMediaIds: string | string[] = [],
    nominatorCity?: string,
    nominatorCountry?: string,
    roundId?: number
  ): Promise<any> {
    try {
      // Convert string media IDs to array if needed
      const imageIds = Array.isArray(imageMediaIds)
        ? imageMediaIds
        : imageMediaIds ? [imageMediaIds] : [];

      const videoIds = Array.isArray(videoMediaIds)
        ? videoMediaIds
        : videoMediaIds ? [videoMediaIds] : [];

      const payload: any = {
        title,
        description,
        image_media_ids: imageIds,
        video_media_ids: videoIds,
        nominator_city: nominatorCity,
        nominator_country: nominatorCountry
      };

      if (roundId !== undefined) {
        payload.round_id = roundId;
      }

      const response = await api.post(`/api/v1/contests/${contestId}/participate`, payload);
      return response.data;
    } catch (error) {
      console.error('Error submitting contestant:', error);
      throw error;
    }
  }

  /**
   * Update an existing contestant entry
   */
  async updateContestant(
    contestantId: number,
    title: string,
    description: string,
    imageMediaIds: string | string[] = [],
    videoMediaIds: string | string[] = [],
    nominatorCity?: string,
    nominatorCountry?: string
  ): Promise<any> {
    try {
      // Convert string media IDs to array if needed
      const imageIds = Array.isArray(imageMediaIds)
        ? imageMediaIds
        : imageMediaIds ? [imageMediaIds] : [];

      const videoIds = Array.isArray(videoMediaIds)
        ? videoMediaIds
        : videoMediaIds ? [videoMediaIds] : [];

      const response = await api.put(`/contestants/${contestantId}`, {
        title,
        description,
        image_media_ids: imageIds,
        video_media_ids: videoIds,
        nominator_city: nominatorCity,
        nominator_country: nominatorCountry
      });
      return response.data;
    } catch (error) {
      console.error('Error updating contestant:', error);
      throw error;
    }
  }

  /**
   * Delete a contestant entry
   */
  async deleteContestant(contestantId: number): Promise<void> {
    try {
      await api.delete(`/contestants/${contestantId}`);
    } catch (error) {
      console.error('Error deleting contestant:', error);
      throw error;
    }
  }

  /**
   * Get user's contest applications
   */
  async getMyApplications(skip: number = 0, limit: number = 10): Promise<ContestantWithAuthorAndStats[]> {
    try {
      const response = await api.get<ContestantWithAuthorAndStats[]>(
        '/api/v1/contestants/user/my-entries',
        { params: { skip, limit } }
      )
      // Backend returns a list directly, not an object with items
      return Array.isArray(response.data) ? response.data : []
    } catch (error: any) {
      // Silently handle network errors
      if (error?.code !== 'ERR_NETWORK' && error?.message && !error?.message?.includes('Network Error') && !error?.message?.includes('CORS')) {
        console.warn('Error fetching my applications:', error)
      }
      return []
    }
  }

  /**
   * Get user's high 5 votes
   */
  async getMyHigh5Votes(): Promise<{
    seasons: Array<{
      season_id: number;
      season_level: string | null;
      contest_id: number;
      contest_name: string | null;
      votes: Array<{
        position: number;
        points: number | null;
        contestant_id: number;
        contestant_title: string;
        contestant_description: string;
        author_id: number;
        author_name: string;
        author_avatar_url: string | null;
        author_country: string | null;
        author_city: string | null;
        votes_count: number;
        vote_date: string;
        season_id: number;
        contest_id: number;
        season_level: string | null;
      }>;
      votes_count: number;
      remaining_slots: number;
    }>
  }> {
    try {
      const response = await api.get<{
        seasons: Array<{
          season_id: number;
          season_level: string | null;
          contest_id: number;
          contest_name: string | null;
          votes: Array<{
            position: number;
            points: number | null;
            contestant_id: number;
            contestant_title: string;
            contestant_description: string;
            author_id: number;
            author_name: string;
            author_avatar_url: string | null;
            author_country: string | null;
            author_city: string | null;
            votes_count: number;
            vote_date: string;
            season_id: number;
            contest_id: number;
            season_level: string | null;
          }>;
          votes_count: number;
          remaining_slots: number;
        }>
      }>('/api/v1/contestants/user/my-votes');
      return response.data;
    } catch (error) {
      console.error('Error fetching high 5 votes:', error);
      return { seasons: [] };
    }
  }

  /**
   * Get user's high 5 votes history (all votes including inactive seasons)
   */
  async getMyHigh5VotesHistory(contestId?: number): Promise<{
    history: Array<{
      contest_id: number;
      contest_name: string | null;
      seasons: Array<{
        season_id: number;
        season_level: string | null;
        is_active: boolean;
        votes: Array<{
          position: number;
          points: number | null;
          contestant_id: number;
          contestant_title: string;
          contestant_description: string;
          author_id: number;
          author_name: string;
          author_avatar_url: string | null;
          author_country: string | null;
          author_city: string | null;
          votes_count: number;
          vote_date: string;
          season_id: number;
          contest_id: number;
          season_level: string | null;
        }>;
        votes_count: number;
      }>;
    }>
  }> {
    try {
      const response = await api.get<{
        history: Array<{
          contest_id: number;
          contest_name: string | null;
          seasons: Array<{
            season_id: number;
            season_level: string | null;
            is_active: boolean;
            votes: Array<{
              position: number;
              points: number | null;
              contestant_id: number;
              contestant_title: string;
              contestant_description: string;
              author_id: number;
              author_name: string;
              author_avatar_url: string | null;
              author_country: string | null;
              author_city: string | null;
              votes_count: number;
              vote_date: string;
              season_id: number;
              contest_id: number;
              season_level: string | null;
            }>;
            votes_count: number;
          }>;
        }>
      }>('/api/v1/contestants/user/my-votes/history', {
        params: contestId != null ? { contest_id: contestId } : undefined
      });
      return response.data;
    } catch (error) {
      console.error('Error fetching high 5 votes history:', error);
      return { history: [] };
    }
  }

  /**
   * Get vote details for a contestant (voters list)
   */
  async getVoteDetails(contestantId: number): Promise<{
    contestant_id: number;
    voters: Array<{
      id?: number;
      user_id: number;
      username?: string;
      full_name?: string;
      avatar_url?: string;
      points: number;
      vote_date: string;
      contest_id?: number;
      season_id?: number;
    }>;
  }> {
    const response = await api.get(`/api/v1/contestants/${contestantId}/votes/details`);
    return response.data;
  }

  /**
   * Get favorite details for a contestant (users who favorited)
   */
  async getFavoriteDetails(contestantId: number): Promise<{
    contestant_id: number;
    users: Array<{
      user_id: number;
      username?: string;
      full_name?: string;
      avatar_url?: string;
      position?: number;
      added_date: string;
    }>;
  }> {
    const response = await api.get(`/api/v1/contestants/${contestantId}/favorites/details`);
    return response.data;
  }

  /**
   * Vote for a contestant
   */
  async voteForContestant(contestantId: number, _points?: number): Promise<void> {
    await api.post(`/api/v1/contestants/${contestantId}/vote`);
  }

  /**
   * Reorder user's MyHigh5 votes for a season
   */
  async reorderMyHigh5Votes(
    votes: Array<{ contestant_id: number; position: number }>,
    seasonId: number
  ): Promise<{ message: string; count: number; season_id: number }> {
    const response = await api.put('/api/v1/contestants/user/my-votes/reorder', {
      votes,
      season_id: seasonId
    });
    return response.data;
  }

  /**
   * Récupère les participants d'un concours avec pagination et filtres optionnels
   */
  /**
   * Get user's favorite contests with pagination
   */
  async getFavoritesContests(skip: number = 0, limit: number = 10): Promise<ContestResponse[]> {
    try {
      const response = await api.get<{ items: ContestResponse[]; total: number }>(
        '/favorites/contests',
        { params: { skip, limit } }
      )
      return response.data.items || []
    } catch (error) {
      console.error('Error fetching favorite contests:', error)
      return []
    }
  }

  /**
   * Get user's favorite contestant IDs
   */
  async getUserFavorites(): Promise<number[]> {
    try {
      const response = await api.get<{ contestant_ids: number[] }>('/favorites')
      return response.data.contestant_ids || []
    } catch (error) {
      console.error('Error fetching user favorites:', error)
      return []
    }
  }

  /**
   * Get contestant by ID
   */
  async getContestantById(id: number): Promise<ContestantWithAuthorAndStats> {
    try {
      const response = await api.get<ContestantWithAuthorAndStats>(`/contestants/${id}`)
      return response.data
    } catch (error) {
      console.error(`Error fetching contestant ${id}:`, error)
      throw error
    }
  }

  /**
   * Reorder favorite contestants
   */
  async reorderFavorites(contestantIds: number[]): Promise<void> {
    try {
      await api.put('/favorites/reorder', { contestant_ids: contestantIds })
    } catch (error) {
      console.error('Error reordering favorites:', error)
      throw error
    }
  }

  /**
   * Get contestants by contest with pagination and optional filters
   */
  async getContestantsByContest(
    contestId: string | number,
    options?: { skip?: number; limit?: number; filterCountry?: string; filterRegion?: string; user_id?: number }
  ): Promise<ContestantWithAuthorAndStats[]> {
    try {
      const skip = options?.skip || 0
      const limit = options?.limit || 10
      const filterCountry = options?.filterCountry
      const filterRegion = options?.filterRegion
      const user_id = options?.user_id

      const cacheKey = `/api/v1/contestants/contest/${contestId}?skip=${skip}&limit=${limit}${filterCountry ? `&filter_country=${filterCountry}` : ''}${filterRegion ? `&filter_region=${filterRegion}` : ''}${user_id ? `&user_id=${user_id}` : ''}`

      // Vérifier le cache
      const cached = cacheService.get<ContestantWithAuthorAndStats[]>(cacheKey)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const params: any = { skip, limit }
      if (filterCountry) params.filter_country = filterCountry
      if (filterRegion) params.filter_region = filterRegion
      if (user_id) params.user_id = user_id

      const response = await api.get<ContestantWithAuthorAndStats[]>(`/api/v1/contestants/contest/${contestId}`, { params })

      // Mettre en cache
      cacheService.set(cacheKey, response.data)

      return response.data || []
    } catch (error: any) {
      // Silently handle network errors - don't log to console.error to avoid noise
      // Only log if it's not a network/CORS error
      if (error?.code !== 'ERR_NETWORK' && error?.message && !error?.message?.includes('Network Error') && !error?.message?.includes('CORS')) {
        console.warn(`Error fetching contestants for contest ${contestId}:`, error)
      }
      return []
    }
  }
}

export const contestService = new ContestService()
