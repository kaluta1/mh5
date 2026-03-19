/**
 * Service pour la gestion des vérifications utilisateur
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export type VerificationType = 
  | 'selfie' 
  | 'selfie_with_pet' 
  | 'selfie_with_document' 
  | 'voice' 
  | 'video' 
  | 'brand' 
  | 'content'

export type MediaType = 'image' | 'audio' | 'video' | 'document'

export type VerificationStatus = 'pending' | 'approved' | 'rejected'

export interface VerificationCreate {
  verification_type: VerificationType
  media_url: string
  media_type: MediaType
  duration_seconds?: number
  file_size_bytes?: number
  contest_id?: number
  contestant_id?: number
  metadata?: Record<string, any>
}

export interface Verification {
  id: number
  user_id: number
  verification_type: string
  media_url: string
  media_type: string
  duration_seconds?: number
  file_size_bytes?: number
  status: VerificationStatus
  rejection_reason?: string
  contest_id?: number
  contestant_id?: number
  reviewed_by?: number
  reviewed_at?: string
  created_at: string
  updated_at: string
}

export interface UserVerificationsStatus {
  has_selfie: boolean
  has_voice: boolean
  has_video: boolean
  has_brand: boolean
  has_content: boolean
  selfie_status?: VerificationStatus
  voice_status?: VerificationStatus
  video_status?: VerificationStatus
  brand_status?: VerificationStatus
  content_status?: VerificationStatus
  selfie_url?: string
  voice_url?: string
  video_url?: string
  brand_url?: string
  content_url?: string
}

class VerificationService {
  private getAuthHeaders(): HeadersInit {
    const token = typeof window !== 'undefined' 
      ? localStorage.getItem('access_token') 
      : null
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }

  /**
   * Créer une nouvelle vérification
   */
  async createVerification(data: VerificationCreate): Promise<Verification> {
    const response = await fetch(`${API_URL}/api/v1/verifications/`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(data)
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Erreur lors de la création de la vérification')
    }

    return response.json()
  }

  /**
   * Récupérer le statut de mes vérifications
   */
  async getMyVerificationsStatus(): Promise<UserVerificationsStatus> {
    const response = await fetch(`${API_URL}/api/v1/verifications/me`, {
      headers: this.getAuthHeaders()
    })

    if (!response.ok) {
      throw new Error('Erreur lors de la récupération des vérifications')
    }

    return response.json()
  }

  /**
   * Récupérer toutes mes vérifications
   */
  async getMyVerifications(type?: VerificationType): Promise<Verification[]> {
    const url = type 
      ? `${API_URL}/api/v1/verifications/me/all?verification_type=${type}`
      : `${API_URL}/api/v1/verifications/me/all`
    
    const response = await fetch(url, {
      headers: this.getAuthHeaders()
    })

    if (!response.ok) {
      throw new Error('Erreur lors de la récupération des vérifications')
    }

    return response.json()
  }

  /**
   * Supprimer une vérification
   */
  async deleteVerification(id: number): Promise<void> {
    const response = await fetch(`${API_URL}/api/v1/verifications/${id}`, {
      method: 'DELETE',
      headers: this.getAuthHeaders()
    })

    if (!response.ok) {
      throw new Error('Erreur lors de la suppression')
    }
  }

  /**
   * Upload un fichier vers Uploadthing et créer la vérification
   */
  async uploadAndCreateVerification(
    file: Blob,
    fileName: string,
    verificationType: VerificationType,
    mediaType: MediaType,
    options?: {
      duration_seconds?: number
      contest_id?: number
      contestant_id?: number
    }
  ): Promise<Verification> {
    // 1. Upload vers /api/upload/moderated
    const formData = new FormData()
    formData.append('file', file, fileName)

    const token = typeof window !== 'undefined' 
      ? localStorage.getItem('access_token') 
      : null

    const uploadResponse = await fetch('/api/upload/moderated', {
      method: 'POST',
      headers: {
        'x-access-token': token || ''
      },
      body: formData
    })

    if (!uploadResponse.ok) {
      const error = await uploadResponse.json()
      throw new Error(error.error || error.details || "Erreur lors de l'upload")
    }

    const uploadResult = await uploadResponse.json()

    // 2. Créer la vérification dans le backend
    const verification = await this.createVerification({
      verification_type: verificationType,
      media_url: uploadResult.file.url,
      media_type: mediaType,
      file_size_bytes: uploadResult.file.size,
      duration_seconds: options?.duration_seconds,
      contest_id: options?.contest_id,
      contestant_id: options?.contestant_id
    })

    return verification
  }
}

export const verificationService = new VerificationService()
