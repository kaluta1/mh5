import api, { apiService } from '@/lib/api'

export interface SearchResult {
  id: string
  title: string
  category: 'contest' | 'contestant' | 'club' | 'product'
  description?: string

  // Champs optionnels enrichis par l'API pour mieux afficher les listes
  full_name?: string
  city?: string
  country?: string
  continent?: string
  level?: string
  location_name?: string
}

export interface SearchResponse {
  contest: SearchResult[]
  contestant: SearchResult[]
  club: SearchResult[]
}

class SearchService {
  /**
   * Search across all categories (fast, limited results)
   */
  async search(query: string): Promise<SearchResponse> {
    try {
      const response = await api.get(`/api/v1/search?q=${encodeURIComponent(query)}`)
      return response.data
    } catch (error) {
      console.error('Search failed:', error)
      throw error
    }
  }

  /**
   * Search multiple categories in parallel for better performance
   */
  async searchAll(query: string, limit: number = 10): Promise<SearchResponse> {
    try {
      const [contests, contestants, clubs] = await Promise.all([
        this.searchContests(query, 0, limit),
        this.searchContestants(query, 0, limit),
        this.searchClubs(query, 0, limit)
      ])

      return {
        contest: contests,
        contestant: contestants,
        club: clubs
      }
    } catch (error) {
      console.error('Multi-search failed:', error)
      // Fallback to global search
      return this.search(query)
    }
  }

  /**
   * Search only contests
   */
  async searchContests(query: string, skip: number = 0, limit: number = 10): Promise<SearchResult[]> {
    try {
      const response = await api.get(
        `/api/v1/search/contests?q=${encodeURIComponent(query)}&skip=${skip}&limit=${limit}`
      )
      return response.data
    } catch (error) {
      console.error('Contest search failed:', error)
      throw error
    }
  }

  /**
   * Search only contestants (contest submissions)
   */
  async searchContestants(query: string, skip: number = 0, limit: number = 10): Promise<SearchResult[]> {
    try {
      const response = await api.get(
        `/api/v1/search/contestants?q=${encodeURIComponent(query)}&skip=${skip}&limit=${limit}`
      )
      return response.data
    } catch (error) {
      console.error('Contestant search failed:', error)
      throw error
    }
  }

  /**
   * Search only clubs
   */
  async searchClubs(query: string, skip: number = 0, limit: number = 10): Promise<SearchResult[]> {
    try {
      const response = await api.get(
        `/api/v1/search/clubs?q=${encodeURIComponent(query)}&skip=${skip}&limit=${limit}`
      )
      return response.data
    } catch (error) {
      console.error('Club search failed:', error)
      throw error
    }
  }
}

export const searchService = new SearchService()
