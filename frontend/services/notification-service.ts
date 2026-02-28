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
  private _notificationsPromise: Promise<Notification[]> | null = null;
  private _notificationsCacheTime: number = 0;
  private _unreadCountPromise: Promise<number> | null = null;
  private _unreadCountCacheTime: number = 0;

  /**
   * Récupère les notifications de l'utilisateur connecté
   */
  async getNotifications(
    skip: number = 0,
    limit: number = 50,
    unreadOnly: boolean = false
  ): Promise<Notification[]> {
    const now = Date.now();
    const cacheKey = `${skip}-${limit}-${unreadOnly}`;
    // Simple deduplication for the exact same parameters within a 2-second window
    if (this._notificationsPromise && now - this._notificationsCacheTime < 2000 && skip === 0 && limit === 20 && !unreadOnly) {
      return this._notificationsPromise;
    }

    const fetchPromise = (async () => {
      try {
        const response = await api.get('/api/v1/notifications', {
          params: { skip, limit, unread_only: unreadOnly },
          timeout: 30000
        })
        return response.data
      } catch (error) {
        return []
      }
    })();

    if (skip === 0 && limit === 20 && !unreadOnly) {
      this._notificationsPromise = fetchPromise;
      this._notificationsCacheTime = now;
    }

    return fetchPromise;
  }

  /**
   * Récupère le nombre de notifications non lues
   */
  async getUnreadCount(): Promise<number> {
    const now = Date.now();
    if (this._unreadCountPromise && now - this._unreadCountCacheTime < 2000) {
      return this._unreadCountPromise;
    }

    this._unreadCountCacheTime = now;
    this._unreadCountPromise = (async () => {
      try {
        const response = await api.get('/api/v1/notifications/unread-count', { timeout: 10000 })
        return response.data?.count ?? 0
      } catch (error) {
        return 0
      }
    })();

    return this._unreadCountPromise;
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

