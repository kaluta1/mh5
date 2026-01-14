'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams, useSearchParams } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { ParticipateFormSkeleton } from '@/components/ui/skeleton'
import { ParticipationForm } from '@/components/dashboard/participation-form'
import { contestService } from '@/services/contest-service'
import { 
  VerificationRequirementsDialog, 
  SelfieVerificationDialog, 
  VoiceVerificationDialog,
  ContentVerificationDialog,
  BrandVerificationDialog
} from '@/components/verification'

export default function ApplyToContestPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { addToast } = useToast()
  
  const contestId = params?.id as string
  const isEditMode = searchParams.get('edit') === 'true'
  const [pageLoading, setPageLoading] = useState(true)
  const [needsProfileSetup, setNeedsProfileSetup] = useState(false)
  const [needsKYC, setNeedsKYC] = useState(false)
  const [contest, setContest] = useState<any>(null)
  const [isNomination, setIsNomination] = useState(false)
  const [userAlreadyParticipating, setUserAlreadyParticipating] = useState(false)
  const [isEditingParticipation, setIsEditingParticipation] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitSuccess, setSubmitSuccess] = useState(false)
  const [timeRemaining, setTimeRemaining] = useState<string>('')
  const [timeValues, setTimeValues] = useState<{ days: number; hours: number; minutes: number; seconds: number; isClosed: boolean; isNA: boolean } | null>(null)
  const [existingParticipationData, setExistingParticipationData] = useState<any>(null)
  const [participantId, setParticipantId] = useState<number | null>(null)
  
  // Verification states
  const [showVerificationDialog, setShowVerificationDialog] = useState(false)
  const [showSelfieDialog, setShowSelfieDialog] = useState(false)
  const [showVoiceDialog, setShowVoiceDialog] = useState(false)
  const [showBrandDialog, setShowBrandDialog] = useState(false)
  const [showContentDialog, setShowContentDialog] = useState(false)
  const [hasVisualVerification, setHasVisualVerification] = useState(false)
  const [hasVoiceVerification, setHasVoiceVerification] = useState(false)
  const [hasBrandVerification, setHasBrandVerification] = useState(false)
  const [hasContentVerification, setHasContentVerification] = useState(false)
  const [verificationsCompleted, setVerificationsCompleted] = useState(false)

  // Calculer le temps restant
  useEffect(() => {
    if (!contest?.submission_end_date) {
      setTimeValues({ days: 0, hours: 0, minutes: 0, seconds: 0, isClosed: false, isNA: true })
      return
    }

    const updateTimeRemaining = () => {
      const now = new Date().getTime()
      const endDate = new Date(contest.submission_end_date).getTime()
      const difference = endDate - now

      if (difference <= 0) {
        setTimeValues({ days: 0, hours: 0, minutes: 0, seconds: 0, isClosed: true, isNA: false })
        return
      }

      const days = Math.floor(difference / (1000 * 60 * 60 * 24))
      const hours = Math.floor((difference / (1000 * 60 * 60)) % 24)
      const minutes = Math.floor((difference / 1000 / 60) % 60)
      const seconds = Math.floor((difference / 1000) % 60)

      setTimeValues({ days, hours, minutes, seconds, isClosed: false, isNA: false })
    }

    // Mettre à jour immédiatement
    updateTimeRemaining()
    
    // Mettre à jour chaque seconde pour un décompteur en temps réel
    const interval = setInterval(updateTimeRemaining, 1000)

    return () => clearInterval(interval)
  }, [contest?.submission_end_date])

  // Formater le temps restant avec les traductions
  useEffect(() => {
    if (!timeValues) {
      setTimeRemaining('')
      return
    }

    if (timeValues.isNA) {
      setTimeRemaining('N/A')
      return
    }

    if (timeValues.isClosed) {
      setTimeRemaining(t('dashboard.contests.closed') || 'Fermé')
      return
    }

    const { days, hours, minutes, seconds } = timeValues
    const dayUnit = t('dashboard.contests.time_unit_days') || 'j'
    const hourUnit = t('dashboard.contests.time_unit_hours') || 'h'
    const minuteUnit = t('dashboard.contests.time_unit_minutes') || 'm'
    const secondUnit = t('dashboard.contests.time_unit_seconds') || 's'

    if (days > 0) {
      setTimeRemaining(`${days}${dayUnit} ${hours}${hourUnit} ${minutes}${minuteUnit}`)
    } else if (hours > 0) {
      setTimeRemaining(`${hours}${hourUnit} ${minutes}${minuteUnit} ${seconds}${secondUnit}`)
    } else if (minutes > 0) {
      setTimeRemaining(`${minutes}${minuteUnit} ${seconds}${secondUnit}`)
    } else {
      setTimeRemaining(`${seconds}${secondUnit}`)
    }
  }, [timeValues, t])

  // Redirection si non authentifié
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  // Vérifier le KYC et charger les données du contest
  useEffect(() => {
    const checkKYCAndLoadContest = async () => {
      try {
        setPageLoading(true)

        // Vérifier si l'utilisateur a complété son profil (first_name, last_name, country, city, continent)
        if (!(user as any)?.first_name || !(user as any)?.last_name || !(user as any)?.country || !(user as any)?.city || !(user as any)?.continent) {
          // Sauvegarder le contestId pour redirection après setup
          if (contestId) {
            sessionStorage.setItem('contestId', contestId)
          }
          setNeedsProfileSetup(true)
          return
        }

        // Vérifier si l'utilisateur a complété son KYC (optionnel, juste pour notification)
        if (!user?.is_verified) {
          setNeedsKYC(true)
        }

        // Charger les données du contest
        if (contestId) {
          const contestData = await contestService.getContestById(contestId)
          setContest(contestData)
          
          // Détecter si c'est une nomination (si voting_type existe)
          const isNominationContest = contestData.voting_type != null
          console.log('Contest Data:', contestData)
          console.log('voting_type:', contestData.voting_type)
          console.log('isNominationContest:', isNominationContest)
          setIsNomination(isNominationContest)
          
          // Vérifier si des vérifications sont requises pour ce contest
          const needsVerification = 
            contestData.requires_kyc || 
            contestData.requires_visual_verification || 
            contestData.requires_voice_verification ||
            contestData.requires_brand_verification ||
            contestData.requires_content_verification
          
          // Si des vérifications sont requises et pas encore complétées, afficher le dialog
          if (needsVerification && !isEditMode) {
            // Vérifier quelles vérifications sont déjà faites
            const kycDone = !contestData.requires_kyc || user?.identity_verified
            const visualDone = !contestData.requires_visual_verification || hasVisualVerification
            const voiceDone = !contestData.requires_voice_verification || hasVoiceVerification
            const brandDone = !contestData.requires_brand_verification || hasBrandVerification
            const contentDone = !contestData.requires_content_verification || hasContentVerification
            
            // Afficher le dialog si au moins une vérification est requise
            if (!kycDone || !visualDone || !voiceDone || !brandDone || !contentDone) {
              setShowVerificationDialog(true)
            }
          }
          
          // Vérifier si l'utilisateur a déjà une candidature
          const userContestants = await contestService.getContestantsByContest(contestId)
          const userParticipation = userContestants.find((c: any) => c.user_id === user?.id)
          if (userParticipation) {
            setUserAlreadyParticipating(true)
            setParticipantId(userParticipation.id)
            // Charger les données existantes pour l'édition
            console.log('Participation data:', userParticipation)
            
            // Parser les image_media_ids (JSON string)
            let imageUrls: string[] = []
            if (userParticipation.image_media_ids) {
              try {
                const parsed = JSON.parse(userParticipation.image_media_ids)
                imageUrls = Array.isArray(parsed) ? parsed : []
              } catch (e) {
                console.error('Erreur parsing image_media_ids:', e)
                imageUrls = []
              }
            }
            
            // Parser les video_media_ids (JSON string)
            let videoUrl = ''
            if (userParticipation.video_media_ids) {
              try {
                const parsed = JSON.parse(userParticipation.video_media_ids)
                videoUrl = Array.isArray(parsed) && parsed.length > 0 ? parsed[0] : ''
              } catch (e) {
                console.error('Erreur parsing video_media_ids:', e)
                videoUrl = ''
              }
            }
            
            setExistingParticipationData({
              title: userParticipation.title || '',
              description: userParticipation.description || '',
              imageUrls: imageUrls,
              videoUrl: videoUrl
            })
            
            // Si le mode édition est activé, afficher directement le formulaire
            if (isEditMode) {
              setIsEditingParticipation(true)
            }
          }
        }
      } catch (err) {
        console.error('Erreur lors du chargement:', err)
        // Ne pas afficher d'erreur générique au chargement
      } finally {
        setPageLoading(false)
      }
    }

    if (!isLoading && isAuthenticated && user) {
      checkKYCAndLoadContest()
    }
  }, [isLoading, isAuthenticated, user, contestId, isEditMode])

  const handleCancel = () => {
    // Si en mode édition, retourner à My Applications
    if (isEditingParticipation) {
      router.push('/dashboard/my-applications')
    } else {
      // Sinon, retourner à la page précédente
      router.back()
    }
  }

  const handleParticipationSubmit = async (
    title: string,
    description: string,
    imageMediaIds?: string,
    videoMediaIds?: string
  ) => {
    setIsSubmitting(true)

    try {
      let response
      
      if (isEditingParticipation && participantId) {
        // Mettre à jour la candidature existante
        response = await contestService.updateContestant(
          participantId,
          title,
          description,
          imageMediaIds,
          videoMediaIds
        )
      } else {
        // Créer une nouvelle candidature
        response = await contestService.submitContestant(
          contestId,
          title,
          description,
          imageMediaIds,
          videoMediaIds
        )
      }

      setSubmitSuccess(true)
      setUserAlreadyParticipating(true)
      
      // Afficher un toast de succès
      addToast(
        isEditingParticipation 
          ? t('dashboard.contests.participation_form.success') 
          : t('dashboard.contests.participation_form.success'),
        'success'
      )
    } catch (err: any) {
      console.error('Erreur lors de la soumission:', err)
      const errorDetail = err?.response?.data?.detail || err?.message || ''
      
      // Détecter le type d'erreur et utiliser les traductions appropriées
      let errorMessage = t('dashboard.contests.participation_form.error.submit_error')
      
      if (errorDetail) {
        const errorLower = errorDetail.toLowerCase()
        
        // Détecter les erreurs de genre
        if (errorLower.includes('masculin') || errorLower.includes('male') || errorLower.includes('male participants only')) {
          errorMessage = t('dashboard.contests.participation_form.error.gender_restriction_male')
        } else if (errorLower.includes('féminin') || errorLower.includes('female') || errorLower.includes('female participants only')) {
          errorMessage = t('dashboard.contests.participation_form.error.gender_restriction_female')
        } else if (errorLower.includes('genre') || errorLower.includes('gender') || errorLower.includes('gender information')) {
          errorMessage = t('dashboard.contests.participation_form.error.gender_not_set')
        } 
        // Détecter les erreurs de soumission déjà effectuée
        else if (errorLower.includes('already') && (errorLower.includes('submission') || errorLower.includes('candidature'))) {
          errorMessage = t('dashboard.contests.participation_form.error.already_submitted')
        }
        // Détecter les erreurs de soumission fermée
        else if (errorLower.includes('closed') || errorLower.includes('fermée') || errorLower.includes('fermé') || errorLower.includes('not open')) {
          errorMessage = t('dashboard.contests.participation_form.error.submission_closed')
        }
        // Détecter les erreurs de date limite
        else if (errorLower.includes('deadline') || errorLower.includes('date limite') || errorLower.includes('dépassée') || errorLower.includes('passed')) {
          errorMessage = t('dashboard.contests.participation_form.error.deadline_passed')
        }
          // Utiliser le message d'erreur du backend s'il est disponible
        else {
          errorMessage = errorDetail
        }
      }
      
      // Afficher l'erreur dans un toast
      addToast(errorMessage, 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading || pageLoading) {
    return <ParticipateFormSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-start justify-center py-8 overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 relative">
        {/* Left Column - Participation Form */}
        <div className="lg:col-span-2">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-1 md:p-1 sticky top-4 space-y-6">
            {/* Success Message */}
            {submitSuccess && (
              <div className="p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center">
                    <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-green-900 dark:text-green-200 font-semibold">
                      {t('dashboard.contests.participation_form.success_title') || '✅ Candidature soumise avec succès !'}
                    </p>
                    <p className="text-green-700 dark:text-green-300 text-sm mt-1">
                      {isEditingParticipation 
                        ? t('dashboard.contests.participation_form.success_edit') || 'Votre candidature a été mise à jour avec succès.'
                        : t('dashboard.contests.participation_form.success') || 'Votre candidature a été soumise avec succès. Elle sera examinée par notre équipe.'}
                    </p>
                  </div>
                </div>
                {contest?.is_submission_open && (
                  <button
                    onClick={() => {
                      // Permettre de modifier à nouveau
                      setIsEditingParticipation(true)
                      setSubmitSuccess(false)
                    }}
                    className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition text-sm"
                  >
                    ✏️ {t('dashboard.contests.participation_form.edit_participation') || 'Modifier ma candidature'}
                  </button>
                )}
              </div>
            )}

            {/* Already Participating Alert */}
            {userAlreadyParticipating && !isEditingParticipation && !submitSuccess && (
              <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg space-y-3">
                <p className="text-blue-900 dark:text-blue-200">
                  {t('dashboard.contests.participation_form.already_participating')}
                </p>
                {contest?.is_submission_open && (
                  <button
                    onClick={() => {
                      // Afficher le formulaire en mode édition
                      setIsEditingParticipation(true)
                    }}
                    className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition text-sm"
                  >
                    ✏️ {t('dashboard.contests.participation_form.edit_participation') || 'Modifier ma candidature'}
                  </button>
                )}
              </div>
            )}

            {/* Header */}
            {(!userAlreadyParticipating || isEditingParticipation) && !submitSuccess && (
              <>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                 
                  {isNomination 
                    ? 'Nominate a Contestant'
                    : t('dashboard.contests.participation_form.title') || 'Participate in Contest '} 
                </h2>
                <p className="text-gray-600 dark:text-gray-400 mb-4 text-sm">
                  {isNomination
                  ? 'Import your video from YouTube or Vimeo'
                  : t('dashboard.contests.participation_form.description')}
                </p>

                {/* Profile Setup Alert */}
                {needsProfileSetup && (
                  <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg mb-4">
                    <p className="text-yellow-900 dark:text-yellow-200 mb-3 text-sm">
                      {t('participation.profile_incomplete_title')} {t('participation.profile_incomplete_message')}
                    </p>
                    <button
                      onClick={() => router.push('/settings')}
                      className="w-full px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg font-medium transition text-sm"
                    >
                      {t('participation.complete_profile_button')}
                    </button>
                  </div>
                )}

                {/* KYC Notification (optionnel) - Ne pas afficher pour les nominations */}
                {needsKYC && !isNomination && (
                  <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg mb-4">
                    <p className="text-amber-900 dark:text-amber-200 text-sm">
                      {t('participation.kyc_notification') || '⚠️ Votre identité n\'a pas été vérifiée. Nous vous recommandons de compléter votre vérification KYC pour une meilleure expérience.'}
                    </p>
                  </div>
                )}

                {/* Submission Closed Alert */}
                {contest && !contest.is_submission_open && (
                  <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg mb-4">
                    <p className="text-red-900 dark:text-red-200 font-medium">
                      🚫 {t('dashboard.contests.submission_closed') || 'Les inscriptions sont fermées pour ce concours.'}
                    </p>
                    <p className="text-red-700 dark:text-red-300 text-sm mt-1">
                      {t('dashboard.contests.submission_closed_message') || 'La date limite de soumission est dépassée.'}
                    </p>
                  </div>
                )}

                {/* Participation Form */}
                {!needsProfileSetup && contest?.is_submission_open && (
                  <ParticipationForm
                    contestId={contestId}
                    onSubmit={handleParticipationSubmit}
                    onCancel={handleCancel}
                    isSubmitting={isSubmitting}
                    isEditing={isEditingParticipation}
                    initialData={existingParticipationData}
                    isNomination={isNomination}
                    mediaRequirements={{
                      requiresVideo: isNomination ? true : contest?.requires_video,
                      maxVideos: contest?.max_videos,
                      videoMaxDuration: contest?.video_max_duration,
                      videoMaxSizeMb: contest?.video_max_size_mb,
                      minImages: isNomination ? 0 : contest?.min_images,
                      maxImages: contest?.max_images
                    }}
                  />
                )}
              </>
            )}
          </div>
        </div>

        {/* Right Column - Contest Info & Leaderboard */}
        <div className="lg:col-span-1 space-y-6">
          {/* Contest Info */}
          {contest && (
            <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 md:p-8  top-4 z-100">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
                {contest.name}
              </h1>
              <p className="text-gray-600 dark:text-gray-400 mb-4 text-sm">
                {contest.description}
              </p>
              
              {/* Contest Details Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg p-3">
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                    {t('dashboard.contests.contestants')}
                  </p>
                  <p className="text-xl font-bold text-gray-900 dark:text-white">
                    {contest.entries_count || 0}
                  </p>
                </div>
                
                <div className="bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg p-3">
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                    {t('dashboard.contests.received')}
                  </p>
                  <p className="text-xl font-bold text-gray-900 dark:text-white">
                    {contest.total_votes || 0}
                  </p>
                </div>
                
                <div className="bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg p-3">
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                    {t('dashboard.contests.status')}
                  </p>
                  <p className="text-sm font-bold text-myfav-primary">
                    {contest.is_submission_open ? t('dashboard.contests.open') : t('dashboard.contests.closed')}
                  </p>
                </div>
                
                <div className="bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg p-3">
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                    {t('dashboard.contests.level')}
                  </p>
                  <p className="text-sm font-bold text-gray-900 dark:text-white capitalize">
                    {contest.level === 'country' ? t('dashboard.contests.country') : 
                     contest.level === 'continental' ? t('dashboard.contests.continental') :
                     contest.level === 'regional' ? t('dashboard.contests.regional') :
                     contest.level}
                  </p>
                </div>

                {/* Time Remaining */}
                <div className="col-span-2 bg-gradient-to-r from-orange-50 to-red-50 dark:from-orange-900/20 dark:to-red-900/20 rounded-lg p-3 border border-orange-200 dark:border-orange-800">
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                    ⏱️ {t('dashboard.contests.time_remaining')}
                  </p>
                  <p className="text-lg font-bold text-orange-600 dark:text-orange-400">
                    {timeRemaining || t('common.loading') || 'Chargement...'}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Verification Dialogs */}
      {contest && (
        <>
          <VerificationRequirementsDialog
            isOpen={showVerificationDialog}
            onClose={() => setShowVerificationDialog(false)}
            contestName={contest.name}
            requirements={{
              requiresKyc: contest.requires_kyc,
              requiresVisualVerification: contest.requires_visual_verification,
              requiresVoiceVerification: contest.requires_voice_verification,
              requiresBrandVerification: contest.requires_brand_verification,
              requiresContentVerification: contest.requires_content_verification,
              requiresVideo: contest.requires_video
            }}
            userVerifications={{
              isKycVerified: user?.identity_verified || false,
              hasVisualVerification,
              hasVoiceVerification,
              hasBrandVerification,
              hasContentVerification
            }}
            onStartVerification={(type) => {
              setShowVerificationDialog(false)
              if (type === 'kyc') {
                router.push('/dashboard/kyc')
              } else if (type === 'visual') {
                setShowSelfieDialog(true)
              } else if (type === 'voice') {
                setShowVoiceDialog(true)
              } else if (type === 'brand') {
                setShowBrandDialog(true)
              } else if (type === 'content') {
                setShowContentDialog(true)
              }
            }}
            onProceed={() => {
              setShowVerificationDialog(false)
              setVerificationsCompleted(true)
            }}
          />

          <SelfieVerificationDialog
            isOpen={showSelfieDialog}
            onClose={() => setShowSelfieDialog(false)}
            onComplete={(imageUrl) => {
              setHasVisualVerification(true)
              setShowSelfieDialog(false)
              setShowVerificationDialog(true)
              addToast(t('verification.selfie_success') || 'Selfie enregistré avec succès', 'success')
            }}
            verificationType={contest.participant_type === 'pet' ? 'selfie_with_pet' : 'selfie'}
            maxSizeMb={contest.verification_max_size_mb || 50}
          />

          <VoiceVerificationDialog
            isOpen={showVoiceDialog}
            onClose={() => setShowVoiceDialog(false)}
            onComplete={(audioUrl) => {
              setHasVoiceVerification(true)
              setShowVoiceDialog(false)
              setShowVerificationDialog(true)
              addToast(t('verification.voice_success') || 'Enregistrement vocal enregistré avec succès', 'success')
            }}
            maxDurationSeconds={contest.verification_video_max_duration || 30}
            maxSizeMb={contest.verification_max_size_mb || 50}
          />

          <BrandVerificationDialog
            isOpen={showBrandDialog}
            onClose={() => setShowBrandDialog(false)}
            onComplete={(data) => {
              setHasBrandVerification(true)
              setShowBrandDialog(false)
              setShowVerificationDialog(true)
              addToast(t('verification.brand_success') || 'Vérification de marque soumise', 'success')
              // TODO: Save brand verification data to backend
            }}
            maxSizeMb={contest.verification_max_size_mb || 50}
          />

          <ContentVerificationDialog
            isOpen={showContentDialog}
            onClose={() => setShowContentDialog(false)}
            onComplete={(data) => {
              setHasContentVerification(true)
              setShowContentDialog(false)
              setShowVerificationDialog(true)
              addToast(t('verification.content_success') || 'Vérification de contenu soumise', 'success')
              // TODO: Save content verification data to backend
            }}
            maxSizeMb={contest.verification_max_size_mb || 50}
          />
        </>
      )}
    </div>
  )
}

