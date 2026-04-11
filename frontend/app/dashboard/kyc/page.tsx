'use client'

import { useState, useEffect, Suspense, useCallback, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { KYCSkeleton } from '@/components/ui/skeleton'
import { kycService, KYCPaymentRequiredError } from '@/services/kyc-service'
import { PaymentDialog } from '@/components/dialogs/payment-dialog-v2'
import { logger } from '@/lib/logger'
import { 
  CheckCircle, 
  AlertCircle, 
  Shield, 
  ExternalLink, 
  Loader2,
  RefreshCw,
  FileCheck,
  User,
  Camera,
  Clock,
  XCircle,
  CreditCard
} from 'lucide-react'

interface KYCStatusData {
  status: string | null
  submitted_at?: string
  processed_at?: string
  rejection_reason?: string
  can_restart?: boolean
  can_continue?: boolean
  verification_url?: string
  attempts_count?: number
  max_attempts?: number
  attempts_remaining?: number
  max_attempts_reached?: boolean
  declared_residential_address?: string | null
  residential_address_locked?: boolean
  needs_proof_of_address?: boolean
  kyc_step?: number
  identity_verified?: boolean
  address_verified?: boolean
  // Payment info
  needs_payment?: boolean
  has_valid_payment?: boolean
  available_payments?: number
  kyc_price?: number
  kyc_currency?: string
}

function KYCPageContent() {
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, isAuthenticated, isLoading, refreshUser } = useAuth()

  const [isInitiating, setIsInitiating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [kycData, setKycData] = useState<KYCStatusData | null>(null)
  const [isLoadingStatus, setIsLoadingStatus] = useState(true)
  const [verificationUrl, setVerificationUrl] = useState<string | null>(null)
  
  // Payment dialog state
  const [showPaymentDialog, setShowPaymentDialog] = useState(false)
  const [residentialAddress, setResidentialAddress] = useState('')

  const [poaName, setPoaName] = useState('')
  const [poaAddressOnDoc, setPoaAddressOnDoc] = useState('')
  const [poaDocType, setPoaDocType] = useState<'utility_bill' | 'address_proof' | 'bank_statement'>(
    'utility_bill'
  )
  const poaFrontInputRef = useRef<HTMLInputElement>(null)
  const poaBackInputRef = useRef<HTMLInputElement>(null)
  const [isSubmittingPoa, setIsSubmittingPoa] = useState(false)

  const addrLocked = !!kycData?.residential_address_locked

  const residentialAddressField = (
    <div className="w-full text-left mb-6">
      <label
        htmlFor="kyc-residential-address"
        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
      >
        {t('residential address') || 'Residential address'}
        {addrLocked ? (
          <span className="ml-2 text-xs font-normal text-amber-600 dark:text-amber-400">
            ({t('kyc.address_locked') || 'locked for this verification'})
          </span>
        ) : null}
      </label>
      <Textarea
        id="kyc-residential-address"
        value={residentialAddress}
        onChange={(e) => setResidentialAddress(e.target.value)}
        disabled={addrLocked}
        readOnly={addrLocked}
        placeholder={
          t('Enter your address') ||
          'Street, city, postal code, country (min. 10 characters before starting verification)'
        }
        className="min-h-[100px] bg-white dark:bg-gray-900 disabled:opacity-70"
        autoComplete="street-address"
      />
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
        {t('kyc.residential_address_hint') ||
          'Enter the address that must match your proof-of-address document. It is locked once Shufti verification starts; changing it requires a new paid verification.'}
      </p>
    </div>
  )

  // Vérifier si on revient de Shufti Pro
  const statusParam = searchParams.get('status')

  // Charger le statut KYC au montage
  useEffect(() => {
    const loadKYCStatus = async () => {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
        
        if (!token) {
          setKycData(null)
          setIsLoadingStatus(false)
          return
        }

        const status = await kycService.getKYCStatus(token)
        setKycData(status)
        
        if (status.status === 'approved' || status.needs_proof_of_address) {
          refreshUser?.()
        }
      } catch (err) {
        // Handle 404 gracefully - no verification found is not an error
        if (err instanceof Error && err.message.includes('404')) {
          setKycData(null)
        } else {
          logger.error('Error loading KYC status:', err)
          setKycData(null)
        }
      } finally {
        setIsLoadingStatus(false)
      }
    }

    if (isAuthenticated) {
      loadKYCStatus()
    } else {
      setIsLoadingStatus(false)
    }
  }, [isAuthenticated, statusParam, refreshUser])

  useEffect(() => {
    const saved = kycData?.declared_residential_address
    if (typeof saved === 'string' && saved.trim().length > 0 && residentialAddress.trim() === '') {
      setResidentialAddress(saved)
    }
  }, [kycData?.declared_residential_address])

  // Démarrer ou reprendre la vérification Shufti Pro
  const handleStartVerification = async (forceNew = false) => {
    setIsInitiating(true)
    setError(null)

    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

      if (!token) {
        setError(t('kyc.login_required') || 'Veuillez vous connecter pour continuer')
        setIsInitiating(false)
        return
      }

      // Déterminer la langue
      const lang = document.documentElement.lang?.toUpperCase() || 'FR'

      const addrToSend = (
        residentialAddress.trim() ||
        (typeof kycData?.declared_residential_address === 'string'
          ? kycData.declared_residential_address.trim()
          : '')
      ).trim()

      if (addrToSend.length > 0 && addrToSend.length < 10) {
        setError(
          t('kyc.residential_address_too_short') ||
            'If you enter a residential address, use at least 10 characters (for your profile / internal verification).'
        )
        setIsInitiating(false)
        return
      }

      const reuseSession = !!kycData?.can_continue
      if (!reuseSession && addrToSend.length < 10) {
        setError(
          t('kyc.residential_address_required') ||
            'Residential address is required (at least 10 characters) before starting verification.'
        )
        setIsInitiating(false)
        return
      }

      const payloadAddr = addrToSend.length >= 10 ? addrToSend : undefined
      const result = await kycService.initiateVerification(token, lang, payloadAddr, forceNew)

      if (result.status === 'pending_proof_of_address' || result.needs_proof_of_address) {
        setVerificationUrl(null)
        const st = await kycService.getKYCStatus(token)
        setKycData(st)
        refreshUser?.()
        return
      }

      if (result.verification_url) {
        setVerificationUrl(result.verification_url)
      } else {
        setError(t('kyc.init_error') || 'Impossible de démarrer la vérification')
      }
    } catch (err) {
      // Gérer l'erreur de paiement requis
      if (err instanceof KYCPaymentRequiredError) {
        setShowPaymentDialog(true)
        setError(null) // Ne pas afficher d'erreur, on affiche le dialog
        // Don't log payment required errors - they're expected
      } else {
        logger.error('Error initiating verification:', err)
        setError(err instanceof Error ? err.message : t('common.error') || 'Une erreur est survenue')
      }
    } finally {
      setIsInitiating(false)
    }
  }

  // Continuer une vérification existante
  const handleContinueVerification = async () => {
    // Réutilisation d'une session en cours : le backend peut renvoyer l'URL sans nouvel appel Shufti
    await handleStartVerification(false)
  }

  /** Nouvelle URL Shufti (évite une iframe INVALID liée à une session ou config obsolète). */
  const handleRequestNewShuftiLink = async () => {
    setVerificationUrl(null)
    await handleStartVerification(true)
  }

  const handleSubmitProofOfAddress = async () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (!token) {
      setError(t('kyc.login_required') || 'Please sign in')
      return
    }
    const frontFile = poaFrontInputRef.current?.files?.[0]
    if (!frontFile) {
      setError(
        t('kyc.poa_file_required') || 'Please choose a proof-of-address file (photo or PDF).'
      )
      return
    }

    setIsSubmittingPoa(true)
    setError(null)
    try {
      const backFile = poaBackInputRef.current?.files?.[0]
      await kycService.submitProofOfAddress(token, {
        document_type: poaDocType,
        document_front: frontFile,
        document_back: backFile ?? null,
        name_on_document: poaName.trim(),
        address_as_shown_on_document: poaAddressOnDoc.trim(),
      })
      const st = await kycService.getKYCStatus(token)
      setKycData(st)
      await refreshUser?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error') || 'Error')
    } finally {
      setIsSubmittingPoa(false)
    }
  }

  // Rafraîchir le statut
  const handleRefreshStatus = async () => {
    setIsLoadingStatus(true)
    try {
      const token = localStorage.getItem('access_token')
      if (token) {
        const status = await kycService.getKYCStatus(token)
        setKycData(status)
        
        if (status.status === 'approved' || status.needs_proof_of_address) {
          refreshUser?.()
        }
      }
    } catch (err) {
      console.error('Error refreshing status:', err)
    } finally {
      setIsLoadingStatus(false)
    }
  }

  /** Après paiement crypto vérifié : met à jour le statut sans masquer toute la page, puis lance Shufti. */
  const handleKycPaymentSuccess = useCallback(async () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (!token) return

    let status = await kycService.getKYCStatus(token)
    for (let attempt = 0; attempt < 5; attempt++) {
      if (!status.needs_payment || status.has_valid_payment) break
      await new Promise((r) => setTimeout(r, 500))
      status = await kycService.getKYCStatus(token)
    }

    setKycData(status)
    if (status.status === 'approved' || status.needs_proof_of_address) {
      refreshUser?.()
    }
    setShowPaymentDialog(false)

    setIsInitiating(true)
    setError(null)
    try {
      const lang = document.documentElement.lang?.toUpperCase() || 'FR'
      const refreshed = status as KYCStatusData
      const declared =
        typeof refreshed.declared_residential_address === 'string'
          ? refreshed.declared_residential_address.trim()
          : ''
      const addrToSend = (residentialAddress.trim() || declared).trim()
      if (addrToSend.length < 10) {
        setError(
          t('kyc.residential_address_required') ||
            'Residential address is required (at least 10 characters) before starting verification.'
        )
        setIsInitiating(false)
        return
      }
      // Fresh Shufti session — reusing an old URL after payment often showed INVALID in the iframe.
      const result = await kycService.initiateVerification(token, lang, addrToSend, true)
      if (result.status === 'pending_proof_of_address' || result.needs_proof_of_address) {
        setVerificationUrl(null)
        const st = await kycService.getKYCStatus(token)
        setKycData(st)
        refreshUser?.()
        return
      }
      if (result.verification_url) {
        setVerificationUrl(result.verification_url)
      } else {
        setError(t('kyc.init_error') || 'Impossible de démarrer la vérification')
      }
    } catch (err) {
      if (err instanceof KYCPaymentRequiredError) {
        setShowPaymentDialog(true)
      } else {
        logger.error('KYC initiate after payment:', err)
        setError(err instanceof Error ? err.message : t('common.error') || 'Une erreur est survenue')
      }
    } finally {
      setIsInitiating(false)
    }
  }, [refreshUser, t, residentialAddress])

  if (isLoading || isLoadingStatus) {
    return <KYCSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  // Affichage de l'iframe Shufti Pro (PRIORITAIRE)
  if (verificationUrl) {
    return (
      <div className="min-h-[calc(100vh-6rem)] p-4">
        {/* Header compact */}
        <div className="max-w-4xl mx-auto mb-4">
          <div className="bg-white/50 dark:bg-gray-800/50 backdrop-blur-sm rounded-xl border border-gray-200 dark:border-gray-700 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-myhigh5-primary to-myhigh5-primary/80 rounded-xl flex items-center justify-center shadow-lg shadow-myhigh5-primary/20">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {t('kyc.verification_in_progress') || 'Vérification d\'identité'}
                </h1>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t('kyc.follow_instructions') || 'Suivez les étapes ci-dessous'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {verificationUrl ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="text-gray-600 dark:text-gray-300"
                  onClick={() => window.open(verificationUrl, '_blank', 'noopener,noreferrer')}
                >
                  <ExternalLink className="w-4 h-4 mr-1" />
                  {t('kyc.open_in_new_tab') || 'Open in new tab'}
                </Button>
              ) : null}
              <Button
                onClick={() => setVerificationUrl(null)}
                variant="ghost"
                size="sm"
                className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                <XCircle className="w-4 h-4 mr-1" />
                {t('common.cancel') || 'Annuler'}
              </Button>
            </div>
          </div>
        </div>

        {/* Iframe Shufti Pro */}
        <div className="max-w-4xl mx-auto">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl shadow-gray-200/50 dark:shadow-gray-900/50 border border-gray-200 dark:border-gray-700 overflow-hidden">
            <iframe
              src={verificationUrl}
              className="w-full border-0"
              style={{ height: 'calc(100vh - 220px)', minHeight: '500px' }}
              allow="camera; microphone"
              title="Shufti Pro Verification"
            />
          </div>
          
          {/* Footer info */}
          <div className="mt-4 text-center space-y-2">
            <p className="text-xs text-gray-400 dark:text-gray-500 flex items-center justify-center gap-1">
              <Shield className="w-3 h-3" />
              {t('kyc.secure_verification') || 'Vérification sécurisée et chiffrée'}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isInitiating}
              onClick={() => void handleRequestNewShuftiLink()}
              className="text-xs"
            >
              {isInitiating ? (
                <>
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                  {t('common.loading') || 'Loading...'}
                </>
              ) : (
                t('kyc.new_verification_link') || 'Get a new verification link'
              )}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  const fullyVerified =
    kycData?.status === 'approved' ||
    (!!user?.identity_verified && !!user?.address_verified)

  // KYC entièrement terminé (identité + domicile)
  if (fullyVerified) {
    return (
      <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="w-20 h-20 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-10 h-10 text-green-600 dark:text-green-400" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
              {t('kyc.already_verified') || 'Identité vérifiée'}
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              {t('kyc.already_verified_description') || 'Votre identité a été vérifiée avec succès. Vous pouvez maintenant profiter de toutes les fonctionnalités.'}
            </p>
            <Button
              onClick={() => router.push('/dashboard')}
              className="bg-myhigh5-primary hover:bg-myhigh5-primary/90"
            >
              {t('common.back_to_dashboard') || 'Retour au tableau de bord'}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // Étape 2 — justificatif de domicile
  if (kycData?.needs_proof_of_address || kycData?.status === 'pending_proof_of_address') {
    const declared =
      typeof kycData.declared_residential_address === 'string'
        ? kycData.declared_residential_address
        : ''
    return (
      <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-8">
            <div className="w-20 h-20 bg-emerald-100 dark:bg-emerald-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <FileCheck className="w-10 h-10 text-emerald-600 dark:text-emerald-400" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2 text-center">
              {t('kyc.step2_title') || 'Step 2: Proof of address'}
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mb-6 text-center text-sm">
              {t('kyc.step2_intro') ||
                'Identity verification is complete. Submit a utility bill, bank statement, or official letter and copy the name and address exactly as shown on the document.'}
            </p>
            {declared ? (
              <div className="mb-4 p-3 rounded-lg bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-600 text-sm">
                <p className="font-medium text-gray-800 dark:text-gray-200 mb-1">
                  {t('kyc.locked_residential_address') || 'Declared address (locked)'}
                </p>
                <p className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap">{declared}</p>
              </div>
            ) : null}
            {error && (
              <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}
            <div className="space-y-4 text-left">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('kyc.poa_document_type') || 'Document type'}
                </label>
                <select
                  value={poaDocType}
                  onChange={(e) =>
                    setPoaDocType(e.target.value as 'utility_bill' | 'address_proof' | 'bank_statement')
                  }
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
                >
                  <option value="utility_bill">{t('kyc.doc_utility') || 'Utility bill'}</option>
                  <option value="bank_statement">{t('kyc.doc_bank') || 'Bank statement'}</option>
                  <option value="address_proof">{t('kyc.doc_address_letter') || 'Official address letter'}</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('kyc.poa_front_file') || 'Document file (photo or PDF)'}
                </label>
                <input
                  ref={poaFrontInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif,application/pdf"
                  className="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-3 file:rounded-md file:border-0 file:bg-myhigh5-primary file:px-3 file:py-2 file:text-sm file:text-white"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {t('kyc.poa_file_hint') || 'JPEG, PNG, WebP, or PDF — max 10 MB.'}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('kyc.poa_back_file') || 'Second page / back (optional)'}
                </label>
                <input
                  ref={poaBackInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif,application/pdf"
                  className="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-3 file:rounded-md file:border-0 file:bg-gray-200 dark:file:bg-gray-700 file:px-3 file:py-2 file:text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('kyc.poa_name_on_doc') || 'Full name as on document'}
                </label>
                <Input
                  value={poaName}
                  onChange={(e) => setPoaName(e.target.value)}
                  className="bg-white dark:bg-gray-900"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('kyc.poa_address_on_doc') || 'Address as shown on document'}
                </label>
                <Textarea
                  value={poaAddressOnDoc}
                  onChange={(e) => setPoaAddressOnDoc(e.target.value)}
                  className="min-h-[80px] bg-white dark:bg-gray-900"
                />
              </div>
            </div>
            <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                onClick={() => void handleSubmitProofOfAddress()}
                disabled={isSubmittingPoa}
                className="bg-myhigh5-primary hover:bg-myhigh5-primary/90"
              >
                {isSubmittingPoa ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {t('common.loading') || 'Loading...'}
                  </>
                ) : (
                  <>
                    <FileCheck className="w-4 h-4 mr-2" />
                    {t('kyc.submit_poa') || 'Submit proof of address'}
                  </>
                )}
              </Button>
              <Button type="button" variant="outline" onClick={() => void handleRefreshStatus()}>
                <RefreshCw className="w-4 h-4 mr-2" />
                {t('common.refresh') || 'Refresh'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Statut KYC en cours - avec possibilité de continuer
  if (kycData?.can_continue) {
    return (
      <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="w-20 h-20 bg-amber-100 dark:bg-amber-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <Clock className="w-10 h-10 text-amber-600 dark:text-amber-400" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
              {t('kyc.verification_in_progress') || 'Vérification en cours'}
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              {t('kyc.verification_continue_description') || 'Vous avez une vérification en cours. Vous pouvez la continuer ou actualiser le statut.'}
            </p>

            {error && (
              <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 flex items-start gap-2 text-left">
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}
            {residentialAddressField}
            
            {kycData?.submitted_at && (
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                {t('kyc.submitted_on') || 'Soumis le'}: {new Date(kycData.submitted_at).toLocaleDateString('fr-FR', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </p>
            )}

            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                onClick={handleContinueVerification}
                disabled={isInitiating}
                className="bg-myhigh5-primary hover:bg-myhigh5-primary/90"
              >
                {isInitiating ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {t('common.loading') || 'Chargement...'}
                  </>
                ) : (
                  <>
                    <ExternalLink className="w-4 h-4 mr-2" />
                    {t('kyc.continue_verification') || 'Continuer la vérification'}
                  </>
                )}
              </Button>
              <Button
                onClick={handleRefreshStatus}
                variant="outline"
                disabled={isLoadingStatus}
              >
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoadingStatus ? 'animate-spin' : ''}`} />
                {t('common.refresh') || 'Actualiser'}
              </Button>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
              {t('kyc.invalid_iframe_hint') ||
                'If the verification window shows INVALID, request a fresh link (same payment):'}
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-1 text-myhigh5-primary"
              disabled={isInitiating}
              onClick={() => void handleStartVerification(true)}
            >
              {t('kyc.new_verification_link') || 'Get a new verification link'}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // KYC max tentatives atteint - Proposer le paiement pour continuer
  if (kycData?.max_attempts_reached) {
    return (
      <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="w-20 h-20 bg-amber-100 dark:bg-amber-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <AlertCircle className="w-10 h-10 text-amber-600 dark:text-amber-400" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
              {t('kyc.max_attempts_reached') || 'Nombre maximum de tentatives atteint'}
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              {t('kyc.max_attempts_can_pay') || 'Vous avez utilisé vos tentatives gratuites. Vous pouvez acheter des tentatives supplémentaires pour continuer.'}
            </p>
            
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 mb-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {t('kyc.attempts_used') || 'Tentatives utilisées'}: <span className="font-semibold">{kycData.attempts_count}/{kycData.max_attempts}</span>
              </p>
            </div>

            {error && (
              <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 flex items-start gap-2 text-left">
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}
            {residentialAddressField}

            {/* Option de paiement */}
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-6">
              <div className="flex items-center gap-2 mb-2">
                <CreditCard className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                  {t('kyc.buy_attempts') || 'Acheter des tentatives supplémentaires'}
                </p>
              </div>
              <p className="text-sm text-blue-700 dark:text-blue-300 mb-3">
                {t('kyc.price_per_attempt') || 'Prix par tentative'}: <span className="font-bold">{kycData.kyc_price || 10} {kycData.kyc_currency || 'USD'}</span>
              </p>
              <Button
                onClick={() => setShowPaymentDialog(true)}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <CreditCard className="w-4 h-4 mr-2" />
                {t('kyc.pay_and_retry') || 'Payer et réessayer'}
              </Button>
            </div>

            <Button
              onClick={() => router.push('/dashboard')}
              variant="outline"
            >
              {t('common.back_to_dashboard') || 'Retour au tableau de bord'}
            </Button>
          </div>
        </div>
        
        {/* Payment Dialog */}
        <PaymentDialog
          open={showPaymentDialog}
          onOpenChange={setShowPaymentDialog}
          initialProductCode="kyc"
          onPaymentInitiated={handleKycPaymentSuccess}
        />
      </div>
    )
  }

  // Tentatives épuisées ou paiement requis
  if (kycData?.max_attempts_reached || (kycData?.needs_payment && !kycData?.has_valid_payment)) {
    return (
      <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="w-20 h-20 bg-amber-100 dark:bg-amber-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <CreditCard className="w-10 h-10 text-amber-600 dark:text-amber-400" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
              {kycData?.max_attempts_reached 
                ? (t('kyc.max_attempts_reached') || 'Tentatives épuisées')
                : (t('kyc.payment_required') || 'Paiement requis')
              }
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              {kycData?.max_attempts_reached 
                ? (t('kyc.max_attempts_reached_description') || 'Vous avez utilisé toutes vos tentatives gratuites. Pour continuer la vérification, veuillez payer les frais de vérification.')
                : (t('kyc.payment_required_description') || 'Pour effectuer la vérification d\'identité, veuillez d\'abord payer les frais de vérification.')
              }
            </p>
            
            {/* Prix de la vérification */}
            <div className="bg-gradient-to-r from-myhigh5-primary/10 to-myhigh5-secondary/10 border border-myhigh5-primary/20 rounded-xl p-4 mb-6">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                {t('kyc.verification_fee') || 'Frais de vérification'}
              </p>
              <p className="text-2xl font-bold text-myhigh5-primary">
                {kycData?.kyc_price || 10} {kycData?.kyc_currency || 'USD'}
              </p>
            </div>

            {error && (
              <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 flex items-start gap-2 text-left">
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}
            {residentialAddressField}

            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                onClick={() => setShowPaymentDialog(true)}
                className="bg-myhigh5-primary hover:bg-myhigh5-primary/90"
              >
                <CreditCard className="w-4 h-4 mr-2" />
                {t('kyc.pay_now') || 'Payer maintenant'}
              </Button>
              <Button
                onClick={() => router.push('/dashboard')}
                variant="outline"
              >
                {t('common.back_to_dashboard') || 'Retour'}
              </Button>
            </div>
          </div>
        </div>
        
        {/* Payment Dialog */}
        <PaymentDialog
          open={showPaymentDialog}
          onOpenChange={setShowPaymentDialog}
          initialProductCode="kyc"
          onPaymentInitiated={handleKycPaymentSuccess}
        />
      </div>
    )
  }

  // KYC rejeté - avec possibilité de reprendre
  if (kycData?.can_restart || kycData?.status === 'rejected') {
    return (
      <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="w-20 h-20 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <XCircle className="w-10 h-10 text-red-600 dark:text-red-400" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
              {t('kyc.verification_rejected') || 'Vérification refusée'}
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              {t('kyc.verification_rejected_description') || 'Votre demande de vérification a été refusée. Vous pouvez soumettre une nouvelle demande.'}
            </p>
            
            {/* Afficher les tentatives restantes */}
            {kycData?.attempts_remaining !== undefined && kycData.attempts_remaining > 0 && (
              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 mb-4">
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  {t('kyc.attempts_remaining') || 'Tentatives restantes'}: <span className="font-bold">{kycData.attempts_remaining}</span> / {kycData.max_attempts}
                </p>
              </div>
            )}
            
            {/* Afficher si paiement requis */}
            {kycData?.needs_payment && (
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <CreditCard className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                    Paiement requis pour une nouvelle tentative
                  </p>
                </div>
                <p className="text-sm text-blue-700 dark:text-blue-300 mb-3">
                  Prix: <span className="font-bold">{kycData.kyc_price || 10} {kycData.kyc_currency || 'USD'}</span>
                </p>
                <Button
                  onClick={() => setShowPaymentDialog(true)}
                  size="sm"
                  className="bg-blue-600 hover:bg-blue-700"
                >
                  <CreditCard className="w-4 h-4 mr-2" />
                  Payer maintenant
                </Button>
              </div>
            )}
            
            {kycData?.rejection_reason && (
              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6 text-left">
                <p className="text-sm font-medium text-red-800 dark:text-red-200 mb-1">
                  {t('kyc.rejection_reason') || 'Raison du refus'}:
                </p>
                <p className="text-sm text-red-700 dark:text-red-300">
                  {kycData.rejection_reason}
                </p>
              </div>
            )}

            {error && (
              <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 flex items-start gap-2 text-left">
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}
            {residentialAddressField}

            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                onClick={() => void handleStartVerification()}
                disabled={isInitiating}
                className="bg-myhigh5-primary hover:bg-myhigh5-primary/90"
              >
                {isInitiating ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {t('common.loading') || 'Chargement...'}
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2" />
                    {t('kyc.submit_again') || 'Réessayer'}
                  </>
                )}
              </Button>
              <Button
                onClick={() => router.push('/dashboard')}
                variant="outline"
              >
                {t('common.back_to_dashboard') || 'Retour'}
              </Button>
            </div>
          </div>
        </div>
        
        {/* Payment Dialog */}
        <PaymentDialog
          open={showPaymentDialog}
          onOpenChange={setShowPaymentDialog}
          initialProductCode="kyc"
          onPaymentInitiated={handleKycPaymentSuccess}
        />
      </div>
    )
  }

  // Formulaire initial - Pas encore de KYC
  return (
    <div className="min-h-[calc(100vh-10rem)] p-4 py-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="w-16 h-16 bg-myhigh5-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Shield className="w-8 h-8 text-myhigh5-primary" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            {t('kyc.verification_required') || 'Identity verification required'}
          </h1>
          <p className="text-gray-600 dark:text-gray-400 max-w-xl mx-auto">
            {t('kyc.verification_required_description') || 'To participate in contests and withdraw your earnings, you must verify your identity.'}
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 flex items-start gap-3 max-w-xl mx-auto">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        {/* Process Steps */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 md:p-8 mb-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6 text-center">
            {t('kyc.verification_steps') || 'Comment ça marche ?'}
          </h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center">
              <div className="w-14 h-14 bg-blue-100 dark:bg-blue-900/30 rounded-xl flex items-center justify-center mx-auto mb-4">
                <User className="w-7 h-7 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="font-medium text-gray-900 dark:text-white mb-2">
                {t('kyc.step_1_title') || '1. Informations personnelles'}
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('kyc.step_1_desc') || 'Renseignez vos informations personnelles de base'}
              </p>
            </div>

            <div className="text-center">
              <div className="w-14 h-14 bg-purple-100 dark:bg-purple-900/30 rounded-xl flex items-center justify-center mx-auto mb-4">
                <FileCheck className="w-7 h-7 text-purple-600 dark:text-purple-400" />
              </div>
              <h3 className="font-medium text-gray-900 dark:text-white mb-2">
                {t('kyc.step_2_title') || '2. Document d\'identité'}
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('kyc.step_2_desc') || 'Prenez en photo votre pièce d\'identité'}
              </p>
            </div>

            <div className="text-center">
              <div className="w-14 h-14 bg-emerald-100 dark:bg-emerald-900/30 rounded-xl flex items-center justify-center mx-auto mb-4">
                <Camera className="w-7 h-7 text-emerald-600 dark:text-emerald-400" />
              </div>
              <h3 className="font-medium text-gray-900 dark:text-white mb-2">
                {t('kyc.step_3_title') || '3. Selfie de vérification'}
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('kyc.step_3_desc') || 'Prenez un selfie pour confirmer votre identité'}
              </p>
            </div>
          </div>
        </div>

        {/* Documents acceptés */}
        <div className="bg-gray-50 dark:bg-gray-800/50 rounded-2xl p-6 mb-8">
          <h3 className="font-medium text-gray-900 dark:text-white mb-4 text-center">
            {t('kyc.accepted_documents') || 'Documents acceptés'}
          </h3>
          <div className="flex flex-wrap justify-center gap-3">
            <span className="px-4 py-2 bg-white dark:bg-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
              {t('kyc.doc_passport') || 'Passeport'}
            </span>
            <span className="px-4 py-2 bg-white dark:bg-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
              {t('kyc.doc_id_card') || "Carte d'identité"}
            </span>
            <span className="px-4 py-2 bg-white dark:bg-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
              {t('kyc.doc_driving_license') || 'Permis de conduire'}
            </span>
          </div>
        </div>

        <div className="max-w-xl mx-auto mb-8">{residentialAddressField}</div>

        {/* CTA Button */}
        <div className="text-center">
          <Button
            onClick={() => void handleStartVerification()}
            disabled={isInitiating}
            size="lg"
            className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white px-8 py-6 text-lg rounded-xl shadow-lg shadow-myhigh5-primary/25"
          >
            {isInitiating ? (
              <>
                <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                {t('kyc.initiating') || 'Démarrage...'}
              </>
            ) : (
              <>
                <Shield className="w-5 h-5 mr-2" />
                {t('kyc.start_verification') || 'Démarrer la vérification'}
              </>
            )}
          </Button>
          
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-4">
            {t('kyc.secure_verification') || 'Vérification sécurisée par notre partenaire certifié'}
          </p>
        </div>
      </div>
      
      {/* Payment Dialog */}
      <PaymentDialog
        open={showPaymentDialog}
        onOpenChange={setShowPaymentDialog}
        initialProductCode="kyc"
        onPaymentInitiated={handleKycPaymentSuccess}
      />
    </div>
  )
}

export default function KYCPage() {
  return (
    <Suspense fallback={<KYCSkeleton />}>
      <KYCPageContent />
    </Suspense>
  )
}
