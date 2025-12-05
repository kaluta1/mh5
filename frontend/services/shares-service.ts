import api from '@/lib/api'

export interface Share {
  id: number
  user_id?: number
  contestant_id: number
  shared_by_user_id?: number
  share_link: string
  platform?: string
  created_at: string
}

export interface ShareStats {
  contestant_id: number
  total_shares: number
  shares_by_platform: Record<string, number>
}

class SharesService {
  /**
   * Enregistrer un partage de contestant
   */
  async shareContestant(
    contestantId: number,
    shareLink: string,
    platform?: string,
    sharedByUserId?: number
  ): Promise<Share> {
    try {
      const response = await api.post(`/api/v1/contestants/${contestantId}/share`, {
        contestant_id: contestantId,
        share_link: shareLink,
        platform: platform,
        shared_by_user_id: sharedByUserId
      })
      return response.data
    } catch (error: any) {
      console.error(`Error sharing contestant ${contestantId}:`, error)
      throw error
    }
  }

  /**
   * Récupérer les statistiques de partage pour un contestant
   */
  async getShareStats(contestantId: number): Promise<ShareStats> {
    try {
      const response = await api.get(`/api/v1/contestants/${contestantId}/shares`)
      return response.data
    } catch (error: any) {
      console.error(`Error fetching share stats for contestant ${contestantId}:`, error)
      throw error
    }
  }
}

export const sharesService = new SharesService()

