import { API_URL } from '@/lib/config'
import { logger } from '@/lib/logger'

export interface KYCSubmissionData {
  firstName: string
  lastName: string
  dateOfBirth: string
  nationality: string
  address: string
  documentType: string
  documentNumber: string
  issuingCountry: string
  documentFront: string
  documentBack: string
  selfie: string
}

export interface KYCStatusResponse {
  status: 'pending' | 'approved' | 'rejected' | 'under_review'
  submittedAt?: string
  reviewedAt?: string
  rejectionReason?: string
}

export interface KYCSubmissionResponse {
  success: boolean
  message: string
  data?: {
    id: string
    status: string
    submittedAt: string
  }
}

export interface KYCInitiateResponse {
  verification_url: string
  reference: string
  verification_id: number
}

export interface PaymentRequiredError {
  type: 'payment_required'
  message: string
  available_attempts: number
  price: number
  currency: string
}

export class KYCPaymentRequiredError extends Error {
  public data: PaymentRequiredError
  
  constructor(data: PaymentRequiredError) {
    super(data.message)
    this.name = 'KYCPaymentRequiredError'
    this.data = data
  }
}

class KYCService {
  private baseUrl = API_URL || 'http://localhost:8000'

  /**
   * Initier une vérification KYC avec Shufti Pro
   * Retourne l'URL de vérification où rediriger l'utilisateur
   */
  async initiateVerification(token: string, language: string = 'FR'): Promise<KYCInitiateResponse> {
    try {
      if (!token) {
        throw new Error('Authentication token is required')
      }

      const response = await fetch(`${this.baseUrl}/api/v1/kyc/initiate?language=${language}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        }
      })

      if (!response.ok) {
        const error = await response.json()
        logger.error('KYC initiation error:', error)
        
        // Gérer l'erreur 402 Payment Required
        if (response.status === 402) {
          const detail = typeof error.detail === 'object' ? error.detail : { message: error.detail }
          throw new KYCPaymentRequiredError({
            type: 'payment_required',
            message: detail.message || 'Paiement requis pour la vérification KYC',
            available_attempts: detail.available_attempts || 0,
            price: detail.price || 10,
            currency: detail.currency || 'USD'
          })
        }
        
        throw new Error(error.detail?.message || error.detail || error.message || 'Failed to initiate KYC verification')
      }

      const result = await response.json()
      return result
    } catch (error) {
      logger.error('KYC initiation error:', error)
      throw error instanceof Error ? error : new Error('An error occurred while initiating KYC')
    }
  }

  /**
   * Soumettre les données KYC
   */
  async submitKYC(data: KYCSubmissionData, token: string): Promise<KYCSubmissionResponse> {
    try {
      if (!token) {
        throw new Error('Authentication token is required')
      }

      const response = await fetch(`${this.baseUrl}/api/v1/kyc/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(data)
      })

      if (!response.ok) {
        const error = await response.json()
        logger.error('KYC submission error:', error)
        throw new Error(error.detail || error.message || 'Failed to submit KYC')
      }

      const result = await response.json()
      return result
    } catch (error) {
      logger.error('KYC submission error:', error)
      throw error instanceof Error ? error : new Error('An error occurred while submitting KYC')
    }
  }

  /**
   * Récupérer le statut KYC de l'utilisateur
   * Uses status-detailed endpoint which returns a better response even when no verification exists
   */
  async getKYCStatus(token: string): Promise<KYCStatusResponse> {
    try {
      if (!token) {
        throw new Error('Authentication token is required')
      }

      // Use status-detailed endpoint which handles "no verification" case gracefully
      const response = await fetch(`${this.baseUrl}/api/v1/kyc/status-detailed`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (!response.ok) {
        // If 404, return null status (no verification found)
        if (response.status === 404) {
          return {
            status: null,
            can_start: true,
            message: 'Aucune vérification KYC trouvée'
          } as any
        }
        const error = await response.json()
        throw new Error(error.detail || error.message || 'Failed to fetch KYC status')
      }

      const result = await response.json()
      // Map status-detailed response to KYCStatusResponse format
      return {
        status: result.status,
        identity_verified: result.identity_verified || false,
        address_verified: result.address_verified || false,
        document_verified: result.document_verified || false,
        face_verified: result.face_verified || false,
        submitted_at: result.submitted_at,
        processed_at: result.processed_at,
        rejection_reason: result.rejection_reason,
        expires_at: result.expires_at,
        can_start: result.can_restart || result.can_continue || false,
        needs_payment: result.needs_payment || false,
        has_valid_payment: result.has_valid_payment || false
      } as any
    } catch (error) {
      // Handle network errors gracefully
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error('Network error: Unable to connect to server')
      }
      throw error instanceof Error ? error : new Error('An error occurred while fetching KYC status')
    }
  }

  /**
   * Récupérer les détails de vérification KYC
   */
  async getKYCVerification(verificationId: string, token: string): Promise<any> {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/kyc/verification/${verificationId}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to fetch KYC verification')
      }

      return await response.json()
    } catch (error) {
      throw error instanceof Error ? error : new Error('An error occurred while fetching KYC verification')
    }
  }

  /**
   * Uploader un document KYC
   */
  async uploadKYCDocument(
    verificationId: string,
    documentType: string,
    file: File,
    token: string
  ): Promise<{ url: string }> {
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('document_type', documentType)

      const response = await fetch(
        `${this.baseUrl}/api/v1/kyc/verification/${verificationId}/upload-document`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
          body: formData
        }
      )

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to upload document')
      }

      return await response.json()
    } catch (error) {
      throw error instanceof Error ? error : new Error('An error occurred while uploading document')
    }
  }

  /**
   * Vérifier si l'utilisateur a déjà soumis un KYC
   */
  async hasSubmittedKYC(token: string): Promise<boolean> {
    try {
      const status = await this.getKYCStatus(token)
      return !!status
    } catch {
      return false
    }
  }

  /**
   * Récupérer les détails de la soumission KYC
   */
  async getKYCSubmission(token: string): Promise<KYCSubmissionData | null> {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/kyc/submission`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (!response.ok) {
        return null
      }

      return await response.json()
    } catch {
      return null
    }
  }

  /**
   * Mettre à jour la soumission KYC
   */
  async updateKYCSubmission(
    data: Partial<KYCSubmissionData>,
    token: string
  ): Promise<KYCSubmissionResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/kyc/submission`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(data)
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to update KYC submission')
      }

      return await response.json()
    } catch (error) {
      throw error instanceof Error ? error : new Error('An error occurred while updating KYC submission')
    }
  }

  /**
   * Annuler la soumission KYC
   */
  async cancelKYCSubmission(token: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/kyc/submission`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to cancel KYC submission')
      }

      return await response.json()
    } catch (error) {
      throw error instanceof Error ? error : new Error('An error occurred while canceling KYC submission')
    }
  }
}

export const kycService = new KYCService()
