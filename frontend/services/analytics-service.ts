import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Types
export interface ContestPerformance {
  name: string
  votes: number
  comments: number
  views: number
  likes: number
}

export interface ReactionStats {
  name: string
  value: number
  color: string
  [key: string]: string | number
}

export interface WeeklyActivity {
  day: string
  votes: number
  views: number
}

export interface AffiliatesStats {
  direct_count: number
  total_network: number
  total_commissions: number
  conversion_rate: number
}

export interface AffiliatesGrowth {
  month: string
  directs: number
  total: number
  commissions: number
}

export interface DashboardAnalytics {
  total_votes: number
  total_comments: number
  total_views: number
  total_reactions: number
  votes_change: number
  comments_change: number
  views_change: number
  reactions_change: number
  contest_performance: ContestPerformance[]
  reactions_by_type: ReactionStats[]
  weekly_activity: WeeklyActivity[]
  affiliates_stats: AffiliatesStats
  affiliates_growth: AffiliatesGrowth[]
  active_contests: number
  best_ranking: number
  engagement_change: number
}

// API instance with auth
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth token to requests
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

// Analytics Service
export const analyticsService = {
  /**
   * Get dashboard analytics for the current user
   */
  async getDashboardAnalytics(): Promise<DashboardAnalytics> {
    const response = await api.get('/api/v1/analytics/dashboard')
    return response.data
  },

  /**
   * Get default/mock data when API fails or user has no data
   */
  getDefaultAnalytics(): DashboardAnalytics {
    return {
      total_votes: 0,
      total_comments: 0,
      total_views: 0,
      total_reactions: 0,
      votes_change: 0,
      comments_change: 0,
      views_change: 0,
      reactions_change: 0,
      contest_performance: [],
      reactions_by_type: [
        { name: '❤️ Love', value: 0, color: '#ef4444' },
        { name: '👏 Bravo', value: 0, color: '#f59e0b' },
        { name: '🔥 Fire', value: 0, color: '#f97316' },
        { name: '⭐ Star', value: 0, color: '#eab308' },
        { name: '😍 Wow', value: 0, color: '#ec4899' },
      ],
      weekly_activity: [
        { day: 'Lun', votes: 0, views: 0 },
        { day: 'Mar', votes: 0, views: 0 },
        { day: 'Mer', votes: 0, views: 0 },
        { day: 'Jeu', votes: 0, views: 0 },
        { day: 'Ven', votes: 0, views: 0 },
        { day: 'Sam', votes: 0, views: 0 },
        { day: 'Dim', votes: 0, views: 0 },
      ],
      affiliates_stats: {
        direct_count: 0,
        total_network: 0,
        total_commissions: 0,
        conversion_rate: 0,
      },
      affiliates_growth: [
        { month: 'Jan', directs: 0, total: 0, commissions: 0 },
        { month: 'Fév', directs: 0, total: 0, commissions: 0 },
        { month: 'Mar', directs: 0, total: 0, commissions: 0 },
        { month: 'Avr', directs: 0, total: 0, commissions: 0 },
        { month: 'Mai', directs: 0, total: 0, commissions: 0 },
        { month: 'Juin', directs: 0, total: 0, commissions: 0 },
      ],
      active_contests: 0,
      best_ranking: 0,
      engagement_change: 0,
    }
  },
}

export default analyticsService
