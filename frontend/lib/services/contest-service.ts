import api from '@/lib/api'
import { cacheService } from '@/lib/cache-service'

export interface CreateContestData {
  name: string
  description?: string
  contest_type: string
  level?: string  // Optional - defaults to "city" on backend
  is_active: boolean
  is_submission_open: boolean
  is_voting_open: boolean
  submission_start_date?: string  // Optional - auto-generated on backend
  submission_end_date?: string  // Optional - auto-generated on backend
  voting_start_date?: string  // Optional - auto-generated on backend
  voting_end_date?: string  // Optional - auto-generated on backend
  image_url?: string
  voting_restriction: string
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
  video_max_duration?: number  // in seconds
  video_max_size_mb?: number
  min_images?: number
  max_images?: number
  // Verification media limits
  verification_video_max_duration?: number  // in seconds
  verification_max_size_mb?: number
}

export interface Contest extends CreateContestData {
  id: number
  created_at: string
  updated_at: string
  participant_count?: number
  contestants?: number
  active_round_id?: number | null
}

export interface ContestResponse {
  id: number
  name: string
  description?: string
  contest_type: string
  level: string
  is_active: boolean
  is_submission_open: boolean
  is_voting_open: boolean
  submission_start_date: string
  submission_end_date: string
  voting_start_date: string
  voting_end_date: string
  image_url?: string
  cover_image_url?: string
  voting_restriction: string
  participant_count: number
  approved_count: number
  pending_count: number
  created_at: string
  updated_at: string
  active_round_id?: number | null
  voting_type_id?: number | null
  voting_type?: {
    id: number
    name: string
    voting_level: string
    commission_source: string
    commission_rules?: any
  }
  category_id?: number | null
  category?: {
    id: number
    name: string
    slug: string
    description?: string
    is_active: boolean
  }
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
  // Verification media limits
  verification_video_max_duration?: number
  verification_max_size_mb?: number
}

class ContestService {
  /**
   * Récupère tous les concours
   */
  async getAllContests(): Promise<ContestResponse[]> {
    try {
      const cacheKey = '/api/v1/admin/contests'

      // Vérifier le cache
      const cached = cacheService.get<ContestResponse[]>(cacheKey)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête avec increased timeout
      const response = await api.get(cacheKey, { timeout: 30000 })

      // Mettre en cache
      cacheService.set(cacheKey, response.data)

      return response.data
    } catch (error: any) {
      // Silently handle timeout errors - don't log to console.error to avoid noise
      if (error?.code !== 'ECONNABORTED' && error?.message && !error?.message?.includes('timeout')) {
        console.warn('Error fetching contests:', error)
      }
      // Return empty array instead of throwing to prevent UI crashes
      return []
    }
  }

  /**
   * Récupère un concours par ID
   */
  async getContestById(id: number): Promise<ContestResponse> {
    try {
      const cacheKey = `/api/v1/admin/contests/${id}`

      // Vérifier le cache
      const cached = cacheService.get<ContestResponse>(cacheKey)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(cacheKey)

      // Mettre en cache
      cacheService.set(cacheKey, response.data)

      return response.data
    } catch (error) {
      console.error(`Erreur lors de la récupération du concours ${id}:`, error)
      throw error
    }
  }

  /**
   * Crée un nouveau concours
   */
  async createContest(data: CreateContestData): Promise<ContestResponse> {
    try {
      const response = await api.post('/api/v1/admin/contests', data)

      // Invalider les caches admin et publics
      cacheService.invalidate('/api/v1/admin/contests')
      cacheService.invalidate('/api/v1/contests/')

      return response.data
    } catch (error) {
      console.error('Erreur lors de la création du concours:', error)
      throw error
    }
  }

  /**
   * Met à jour un concours
   */
  async updateContest(id: number, data: Partial<CreateContestData>): Promise<ContestResponse> {
    try {
      const response = await api.put(`/api/v1/admin/contests/${id}`, data)

      // Invalider les caches admin et publics pour ce contest spécifique
      cacheService.invalidate(`/api/v1/admin/contests/${id}`)
      cacheService.invalidate(`/api/v1/contests/${id}`)

      // Invalider les listes de contests
      cacheService.invalidate('/api/v1/admin/contests')
      cacheService.invalidate('/api/v1/contests/')

      // Mettre à jour le cache avec les nouvelles données
      cacheService.set(`/api/v1/admin/contests/${id}`, response.data)
      cacheService.set(`/api/v1/contests/${id}`, response.data)

      return response.data
    } catch (error) {
      console.error(`Erreur lors de la mise à jour du concours ${id}:`, error)
      throw error
    }
  }

  /**
   * Supprime un concours
   */
  async deleteContest(id: number): Promise<void> {
    try {
      await api.delete(`/api/v1/admin/contests/${id}`)

      // Invalider les caches admin et publics
      cacheService.invalidate(`/api/v1/admin/contests/${id}`)
      cacheService.invalidate(`/api/v1/contests/${id}`)
      cacheService.invalidate('/api/v1/admin/contests')
      cacheService.invalidate('/api/v1/contests/')
    } catch (error) {
      console.error(`Erreur lors de la suppression du concours ${id}:`, error)
      throw error
    }
  }

  /**
   * Récupère les concours avec filtres
   */
  async getContestsByFilter(filters: {
    level?: string
    is_active?: boolean
    contest_type?: string
  }): Promise<ContestResponse[]> {
    try {
      const params = new URLSearchParams()
      if (filters.level) params.append('level', filters.level)
      if (filters.is_active !== undefined) params.append('is_active', String(filters.is_active))
      if (filters.contest_type) params.append('contest_type', filters.contest_type)

      const cacheKey = '/api/v1/admin/contests'
      const paramsObj = {
        level: filters.level,
        is_active: filters.is_active,
        contest_type: filters.contest_type
      }

      // Vérifier le cache
      const cached = cacheService.get<ContestResponse[]>(cacheKey, paramsObj)
      if (cached) {
        return cached
      }

      // Si pas en cache, faire la requête
      const response = await api.get(`/api/v1/admin/contests?${params.toString()}`)

      // Mettre en cache
      cacheService.set(cacheKey, response.data, paramsObj)

      return response.data
    } catch (error) {
      console.error('Erreur lors de la récupération des concours filtrés:', error)
      throw error
    }
  }
}

export const contestService = new ContestService()
