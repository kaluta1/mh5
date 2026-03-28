import api from '@/lib/api'

export interface MentionUser {
  id: number
  username?: string
  full_name?: string
  avatar_url?: string
}

export const userService = {
  async searchUsers(query: string, limit: number = 8): Promise<MentionUser[]> {
    const normalizedQuery = query.trim()
    if (!normalizedQuery) return []

    const response = await api.get('/api/v1/users/search', {
      params: {
        q: normalizedQuery,
        limit,
      },
    })

    return Array.isArray(response.data) ? response.data : []
  },
}
