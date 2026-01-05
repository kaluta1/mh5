import api from '@/lib/api'

export interface Reaction {
  id: number
  user_id: number
  contestant_id: number
  reaction_type: 'like' | 'love' | 'wow' | 'dislike'
  created_at: string
}

export interface ReactionStats {
  contestant_id: number
  total_reactions: number
  like_count: number
  love_count: number
  wow_count: number
  dislike_count: number
  user_reaction?: 'like' | 'love' | 'wow' | 'dislike' | null
}

export interface ReactionUserDetail {
  user_id: number
  username?: string | null
  full_name?: string | null
  avatar_url?: string | null
  reaction_type: string
}

export interface ReactionDetails {
  contestant_id: number
  reactions_by_type: Record<string, ReactionUserDetail[]>
}

class ReactionsService {
  /**
   * Ajouter ou mettre à jour une réaction pour un contestant
   */
  async addReaction(contestantId: number, reactionType: 'like' | 'love' | 'wow' | 'dislike'): Promise<Reaction> {
    try {
      const response = await api.post(`/api/v1/contestants/${contestantId}/reaction`, {
        contestant_id: contestantId,
        reaction_type: reactionType
      })
      return response.data
    } catch (error: any) {
      console.error(`Error adding reaction for contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Supprimer une réaction pour un contestant
   */
  async removeReaction(contestantId: number): Promise<void> {
    try {
      await api.delete(`/api/v1/contestants/${contestantId}/reaction`)
    } catch (error: any) {
      console.error(`Error removing reaction for contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Récupérer les statistiques de réactions pour un contestant
   */
  async getReactionStats(contestantId: number): Promise<ReactionStats> {
    try {
      const response = await api.get(`/api/v1/contestants/${contestantId}/reactions`)
      return response.data
    } catch (error: any) {
      console.error(`Error fetching reaction stats for contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Récupérer les détails des réactions avec les noms des utilisateurs
   */
  async getReactionDetails(contestantId: number): Promise<ReactionDetails> {
    try {
      const response = await api.get(`/api/v1/contestants/${contestantId}/reactions/details`)
      return response.data
    } catch (error: any) {
      console.error(`Error fetching reaction details for contestant ${contestantId}:`, error)
      throw error
    }
  }
}

export const reactionsService = new ReactionsService()

