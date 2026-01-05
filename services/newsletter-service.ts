const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface NewsletterSubscriptionData {
  email: string
  device_info?: {
    user_agent?: string
    platform?: string
    browser?: string
    screen_width?: number
    screen_height?: number
  }
  location_info?: {
    country?: string
    city?: string
    continent?: string
    ip?: string
    timezone?: string
  }
}

export interface NewsletterSubscriptionResponse {
  id: number
  email: string
  is_active: boolean
  is_verified: boolean
  created_at: string
  verified_at?: string | null
}

class NewsletterService {
  private baseUrl = `${API_BASE_URL}/api/v1/newsletter`

  async subscribe(data: NewsletterSubscriptionData): Promise<NewsletterSubscriptionResponse> {
    const response = await fetch(`${this.baseUrl}/subscribe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Une erreur est survenue' }))
      throw new Error(error.detail || 'Erreur lors de l\'abonnement à la newsletter')
    }

    return response.json()
  }

  async unsubscribe(email: string): Promise<{ message: string }> {
    const response = await fetch(`${this.baseUrl}/unsubscribe?email=${encodeURIComponent(email)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Une erreur est survenue' }))
      throw new Error(error.detail || 'Erreur lors de la désinscription')
    }

    return response.json()
  }
}

export const newsletterService = new NewsletterService()

