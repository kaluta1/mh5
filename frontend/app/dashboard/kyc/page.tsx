'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { KYCSkeleton } from '@/components/ui/skeleton'
import { KYCStepSidebar } from '@/components/dashboard/kyc-step-sidebar'
import { KYCPersonalInfoStep } from '@/components/dashboard/kyc-personal-info-step'
import { KYCDocumentInfoStep } from '@/components/dashboard/kyc-document-info-step'
import { KYCDocumentUploadStep } from '@/components/dashboard/kyc-document-upload-step'
import { KYCReviewStep } from '@/components/dashboard/kyc-review-step'
import { KYCNavigationButtons } from '@/components/dashboard/kyc-navigation-buttons'
import { KYCStatusDisplay } from '@/components/dashboard/kyc-status-display'
import { kycService } from '@/services/kyc-service'
import { CheckCircle, AlertCircle } from 'lucide-react'

export default function KYCPage() {
  const { t } = useLanguage()
  const router = useRouter()

  // TODO: Intégrer avec le contexte d'authentification réel
  const isLoading = false
  const isAuthenticated = true
  const user = { is_verified: false }

  const [currentStep, setCurrentStep] = useState(1)
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    dateOfBirth: '',
    nationality: '',
    address: '',
    documentType: 'passport',
    documentNumber: '',
    issuingCountry: '',
    documentFront: '',
    documentBack: '',
    selfie: ''
  })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [kycStatus, setKycStatus] = useState<'pending' | 'approved' | 'rejected' | 'under_review' | null>(null)
  const [kycSubmissionData, setKycSubmissionData] = useState<any>(null)
  const [isLoadingStatus, setIsLoadingStatus] = useState(true)

  // Charger le statut KYC au montage
  useEffect(() => {
    const loadKYCStatus = async () => {
      try {
        // Récupérer le token depuis le localStorage
        const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
        
        if (!token) {
          setKycStatus(null)
          setIsLoadingStatus(false)
          return
        }

        const status = await kycService.getKYCStatus(token)
        setKycStatus(status.status as any)
        setKycSubmissionData(status)

        // Charger aussi les données soumises précédemment
        try {
          const submission = await kycService.getKYCSubmission(token)
          if (submission) {
            setFormData(submission)
          }
        } catch (err) {
          console.error('Error loading KYC submission data:', err)
        }
      } catch (err) {
        // Pas de soumission précédente ou token invalide
        console.error('Error loading KYC status:', err)
        setKycStatus(null)
      } finally {
        setIsLoadingStatus(false)
      }
    }

    if (isAuthenticated) {
      loadKYCStatus()
    }
  }, [isAuthenticated])

  if (isLoading) {
    return <KYCSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  // Si l'utilisateur a déjà soumis un KYC, afficher le statut
  if (kycStatus) {
    // Si le statut est en cours de traitement (pending ou under_review), afficher les infos en lecture seule
    if (kycStatus === 'pending' || kycStatus === 'under_review') {
      return (
        <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-2 md:p-4 py-8">
          <div className="w-full">
            <div className="mb-8">
              <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
                {t('kyc.verification_in_progress')}
              </h1>
              <p className="text-gray-600 dark:text-gray-400 text-lg">
                {t('kyc.verification_in_progress_description')}
              </p>
            </div>

            {/* Status Display */}
            <div className="mb-8">
              <KYCStatusDisplay
                status={kycStatus}
                submittedAt={kycSubmissionData?.submittedAt}
                reviewedAt={kycSubmissionData?.reviewedAt}
                rejectionReason={kycSubmissionData?.rejectionReason}
              />
            </div>

            {/* Read-only Information */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 md:p-6 mb-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Personal Information */}
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                    {t('kyc.personal_info')}
                  </h3>
                  <div className="space-y-3">
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{t('auth.first_name')}</p>
                      <p className="text-gray-900 dark:text-white font-medium">{formData.firstName || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{t('auth.last_name')}</p>
                      <p className="text-gray-900 dark:text-white font-medium">{formData.lastName || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{t('kyc.date_of_birth')}</p>
                      <p className="text-gray-900 dark:text-white font-medium">{formData.dateOfBirth || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{t('kyc.nationality')}</p>
                      <p className="text-gray-900 dark:text-white font-medium">{formData.nationality || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{t('kyc.address')}</p>
                      <p className="text-gray-900 dark:text-white font-medium">{formData.address || '-'}</p>
                    </div>
                  </div>
                </div>

                {/* Document Information */}
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                    {t('kyc.document_info')}
                  </h3>
                  <div className="space-y-3">
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{t('kyc.document_type')}</p>
                      <p className="text-gray-900 dark:text-white font-medium">{formData.documentType || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{t('kyc.document_number')}</p>
                      <p className="text-gray-900 dark:text-white font-medium">{formData.documentNumber || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">{t('kyc.issuing_country')}</p>
                      <p className="text-gray-900 dark:text-white font-medium">{formData.issuingCountry || '-'}</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Document Images */}
              <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                  {t('kyc.uploaded_documents')}
                </h3>
                {formData.documentFront || formData.documentBack || formData.selfie ? (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {formData.documentFront && (
                      <div>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{t('kyc.document_front')}</p>
                        <img
                          src={formData.documentFront}
                          alt="Document Front"
                          className="w-full h-40 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
                          onError={(e) => {
                            console.error('Error loading document front image:', formData.documentFront)
                            e.currentTarget.style.display = 'none'
                          }}
                        />
                      </div>
                    )}
                    {formData.documentBack && (
                      <div>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{t('kyc.document_back')}</p>
                        <img
                          src={formData.documentBack}
                          alt="Document Back"
                          className="w-full h-40 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
                          onError={(e) => {
                            console.error('Error loading document back image:', formData.documentBack)
                            e.currentTarget.style.display = 'none'
                          }}
                        />
                      </div>
                    )}
                    {formData.selfie && (
                      <div>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{t('kyc.selfie')}</p>
                        <img
                          src={formData.selfie}
                          alt="Selfie"
                          className="w-full h-40 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
                          onError={(e) => {
                            console.error('Error loading selfie image:', formData.selfie)
                            e.currentTarget.style.display = 'none'
                          }}
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-gray-600 dark:text-gray-400 text-sm">
                    {t('common.no_documents')}
                  </p>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                onClick={() => router.push('/dashboard')}
                variant="outline"
              >
                {t('common.back_to_dashboard')}
              </Button>
            </div>
          </div>
        </div>
      )
    }

    // Pour les autres statuts (approved, rejected), afficher le statut normal
    return (
      <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-4 py-8">
        <div className="w-full ">
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
              {t('kyc.verification_status')}
            </h1>
            <p className="text-gray-600 dark:text-gray-400 text-lg">
              {t('kyc.verification_status_description')}
            </p>
          </div>

          <KYCStatusDisplay
            status={kycStatus}
            submittedAt={kycSubmissionData?.submittedAt}
            reviewedAt={kycSubmissionData?.reviewedAt}
            rejectionReason={kycSubmissionData?.rejectionReason}
          />

          {kycStatus === 'rejected' && (
            <div className="mt-6">
              <Button
                onClick={() => setKycStatus(null)}
                className="bg-myfav-primary hover:bg-myfav-primary-dark text-white"
              >
                {t('kyc.submit_again')}
              </Button>
            </div>
          )}

          <div className="mt-6">
            <Button
              onClick={() => router.push('/dashboard')}
              variant="outline"
            >
              {t('common.back_to_dashboard')}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // Si l'utilisateur est déjà vérifié
  if (user.is_verified) {
    return (
      <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-4">
        <div className="w-full max-w-2xl bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 md:p-8">
          <div className="text-center">
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 bg-green-100 dark:bg-green-900/20 rounded-full flex items-center justify-center">
                <CheckCircle className="w-8 h-8 text-green-600 dark:text-green-400" />
              </div>
            </div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
              {t('kyc.already_verified')}
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mb-8">
              {t('kyc.already_verified_description')}
            </p>
            <Button
              onClick={() => router.push('/dashboard')}
              className="bg-myfav-primary hover:bg-myfav-primary-dark text-white"
            >
              {t('common.back_to_dashboard')}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const validateStep = (step: number): boolean => {
    const errors: string[] = []

    if (step === 1) {
      // Validation étape 1: Informations personnelles
      if (!formData.firstName.trim()) errors.push(t('kyc.errors.first_name_required'))
      if (!formData.lastName.trim()) errors.push(t('kyc.errors.last_name_required'))
      if (!formData.dateOfBirth) errors.push(t('kyc.errors.date_of_birth_required'))
      if (!formData.nationality) errors.push(t('kyc.errors.nationality_required'))
      if (!formData.address.trim()) errors.push(t('kyc.errors.address_required'))
    } else if (step === 2) {
      // Validation étape 2: Informations du document
      if (!formData.documentType) errors.push(t('kyc.errors.document_type_required'))
      if (!formData.documentNumber.trim()) errors.push(t('kyc.errors.document_number_required'))
      if (!formData.issuingCountry) errors.push(t('kyc.errors.issuing_country_required'))
    } else if (step === 3) {
      // Validation étape 3: Upload de documents
      if (!formData.documentFront) errors.push(t('kyc.errors.document_front_required'))
      if (!formData.documentBack) errors.push(t('kyc.errors.document_back_required'))
      if (!formData.selfie) errors.push(t('kyc.errors.selfie_required'))
    }

    if (errors.length > 0) {
      setError(errors.join(', '))
      return false
    }

    setError(null)
    return true
  }

  const handleNext = () => {
    if (validateStep(currentStep) && currentStep < 4) {
      setCurrentStep(currentStep + 1)
    }
  }

  const handlePrevious = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    // Valider toutes les étapes
    if (!validateStep(1) || !validateStep(2) || !validateStep(3)) {
      return
    }

    setIsSubmitting(true)

    try {
      // Récupérer le token depuis le localStorage
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

      if (!token) {
        setError('Authentication token not found. Please log in again.')
        setIsSubmitting(false)
        return
      }

      // Appeler l'API pour soumettre le KYC
      const response = await kycService.submitKYC(formData, token)

      if (response.success) {
        setSuccess(true)
        // Afficher le statut après 2 secondes
        setTimeout(() => {
          setKycStatus('pending')
          setKycSubmissionData({
            status: 'pending',
            submittedAt: new Date().toISOString()
          })
        }, 2000)
      } else {
        setError(response.message || 'Failed to submit KYC')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Une erreur est survenue')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-2 md:p-4 py-8">
      <div className="w-full ">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
            {t('kyc.verification_required')}
          </h1>
          <p className="text-gray-600 dark:text-gray-400 text-lg">
            {t('kyc.verification_required_description')}
          </p>
        </div>

        {/* Sidebar - Steps (Mobile) */}
        <div className="lg:hidden mb-6">
          <KYCStepSidebar
            steps={[
              {
                number: 1,
                title: t('kyc.personal_info'),
                description: t('kyc.personal_info_desc')
              },
              {
                number: 2,
                title: t('kyc.document_info'),
                description: t('kyc.document_info_desc')
              },
              {
                number: 3,
                title: 'Upload Documents',
                description: 'Upload your documents'
              },
              {
                number: 4,
                title: t('kyc.review_submit'),
                description: t('kyc.review_submit_desc')
              }
            ]}
            currentStep={currentStep}
            onStepClick={setCurrentStep}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar - Steps (Desktop) */}
          <div className="hidden lg:block">
            <KYCStepSidebar
              steps={[
                {
                  number: 1,
                  title: t('kyc.personal_info'),
                  description: t('kyc.personal_info_desc')
                },
                {
                  number: 2,
                  title: t('kyc.document_info'),
                  description: t('kyc.document_info_desc')
                },
                {
                  number: 3,
                  title: 'Upload Documents',
                  description: 'Upload your documents'
                },
                {
                  number: 4,
                  title: t('kyc.review_submit'),
                  description: t('kyc.review_submit_desc')
                }
              ]}
              currentStep={currentStep}
              onStepClick={setCurrentStep}
            />
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3">
            <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 md:p-6">
              {/* Success Message */}
              {success && (
                <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4 flex items-start gap-3">
                  <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-green-900 dark:text-green-100 font-medium">
                      {t('kyc.submission_success')}
                    </p>
                  </div>
                </div>
              )}

              {/* Error Message */}
              {error && (
                <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-red-900 dark:text-red-100 font-medium">
                      {error}
                    </p>
                  </div>
                </div>
              )}

              {/* Step 1: Personal Information */}
              {currentStep === 1 && (
                <KYCPersonalInfoStep
                  data={{
                    firstName: formData.firstName,
                    lastName: formData.lastName,
                    dateOfBirth: formData.dateOfBirth,
                    nationality: formData.nationality,
                    address: formData.address
                  }}
                  onChange={(field, value) => setFormData(prev => ({ ...prev, [field]: value }))}
                />
              )}

              {/* Step 2: Document Information */}
              {currentStep === 2 && (
                <KYCDocumentInfoStep
                  data={{
                    documentType: formData.documentType,
                    documentNumber: formData.documentNumber,
                    issuingCountry: formData.issuingCountry
                  }}
                  onChange={(field, value) => setFormData(prev => ({ ...prev, [field]: value }))}
                />
              )}

              {/* Step 3: Document Upload */}
              {currentStep === 3 && (
                <KYCDocumentUploadStep
                  data={{
                    documentFront: formData.documentFront,
                    documentBack: formData.documentBack,
                    selfie: formData.selfie
                  }}
                  onChange={(field, value) => setFormData(prev => ({ ...prev, [field]: value }))}
                />
              )}

              {/* Step 4: Review & Submit */}
              {currentStep === 4 && (
                <KYCReviewStep data={formData} />
              )}

              {/* Navigation Buttons */}
              <KYCNavigationButtons
                currentStep={currentStep}
                totalSteps={4}
                isSubmitting={isSubmitting}
                onPrevious={handlePrevious}
                onNext={handleNext}
                onSubmit={handleSubmit}
              />
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
