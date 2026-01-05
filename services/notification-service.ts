import api from '@/lib/api'

export interface Notification {
  id: number
  user_id: number
  type: 'system' | 'contest' | 'compte'
  title: string
  message: string
  related_contestant_id?: number | null
  related_comment_id?: number | null
  related_contest_id?: number | null
  is_read: boolean
  created_at: string
}

export interface NotificationUnreadCount {
  count: number
}

class NotificationService {
  /**
   * Récupère les notifications de l'utilisateur connecté
   */
  async getNotifications(
    skip: number = 0,
    limit: number = 50,
    unreadOnly: boolean = false
  ): Promise<Notification[]> {
    try {
      const response = await api.get('/api/v1/notifications', {
        params: { skip, limit, unread_only: unreadOnly }
      })
      return response.data
    } catch (error) {
      console.error('Erreur lors de la récupération des notifications:', error)
      throw error
    }
  }

  /**
   * Récupère le nombre de notifications non lues
   */
  async getUnreadCount(): Promise<number> {
    try {
      const response = await api.get('/api/v1/notifications/unread-count')
      return response.data.count
    } catch (error) {
      console.error('Erreur lors de la récupération du nombre de notifications non lues:', error)
      return 0
    }
  }

  /**
   * Marque une notification comme lue
   */
  async markAsRead(notificationId: number): Promise<Notification> {
    try {
      const response = await api.patch(`/api/v1/notifications/${notificationId}/read`)
      return response.data
    } catch (error) {
      console.error('Erreur lors du marquage de la notification comme lue:', error)
      throw error
    }
  }

  /**
   * Marque toutes les notifications comme lues
   */
  async markAllAsRead(): Promise<{ message: string; count: number }> {
    try {
      const response = await api.patch('/api/v1/notifications/read-all')
      return response.data
    } catch (error) {
      console.error('Erreur lors du marquage de toutes les notifications comme lues:', error)
      throw error
    }
  }
}

export const notificationService = new NotificationService()

