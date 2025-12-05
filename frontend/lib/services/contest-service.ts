import api from '@/lib/api'

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
}

export interface Contest extends CreateContestData {
  id: number
  created_at: string
  updated_at: string
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
  participant_count?: number
  approved_count?: number
  pending_count?: number
  created_at: string
  updated_at: string
}

class ContestService {
  /**
   * Récupère tous les concours
   */
  async getAllContests(): Promise<ContestResponse[]> {
    try {
      const response = await api.get('/api/v1/admin/contests')
      return response.data
    } catch (error) {
      console.error('Erreur lors de la récupération des concours:', error)
      throw error
    }
  }

  /**
   * Récupère un concours par ID
   */
  async getContestById(id: number): Promise<ContestResponse> {
    try {
      const response = await api.get(`/api/v1/admin/contests/${id}`)
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

      const response = await api.get(`/api/v1/admin/contests?${params.toString()}`)
      return response.data
    } catch (error) {
      console.error('Erreur lors de la récupération des concours filtrés:', error)
      throw error
    }
  }
}

export const contestService = new ContestService()
