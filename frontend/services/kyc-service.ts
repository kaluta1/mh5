import { API_URL } from '@/lib/config'

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

class KYCService {
  private baseUrl = API_URL || 'http://localhost:8000'

  /**
   * Soumettre les données KYC
   */
  async submitKYC(data: KYCSubmissionData, token: string): Promise<KYCSubmissionResponse> {
    try {
      if (!token) {
        throw new Error('Authentication token is required')
      }

      console.log('Submitting KYC data to:', `${this.baseUrl}/api/v1/kyc/submit`)
      console.log('Token:', token.substring(0, 20) + '...')

      const response = await fetch(`${this.baseUrl}/api/v1/kyc/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(data)
      })

      console.log('Response status:', response.status)

      if (!response.ok) {
        const error = await response.json()
        console.error('KYC submission error:', error)
        throw new Error(error.detail || error.message || 'Failed to submit KYC')
      }

      const result = await response.json()
      console.log('KYC submission successful:', result)
      return result
    } catch (error) {
      console.error('KYC submission error:', error)
      throw error instanceof Error ? error : new Error('An error occurred while submitting KYC')
    }
  }

  /**
   * Récupérer le statut KYC de l'utilisateur
   */
  async getKYCStatus(token: string): Promise<KYCStatusResponse> {
    try {
      if (!token) {
        throw new Error('Authentication token is required')
      }

      console.log('Fetching KYC status from:', `${this.baseUrl}/api/v1/kyc/status`)

      const response = await fetch(`${this.baseUrl}/api/v1/kyc/status`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      console.log('Response status:', response.status)

      if (!response.ok) {
        const error = await response.json()
        console.error('KYC status error:', error)
        throw new Error(error.detail || error.message || 'Failed to fetch KYC status')
      }

      const result = await response.json()
      console.log('KYC status:', result)
      return result
    } catch (error) {
      console.error('KYC status error:', error)
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
