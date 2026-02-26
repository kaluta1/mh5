'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter, useParams, useSearchParams } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { ParticipateFormSkeleton } from '@/components/ui/skeleton'
import { ParticipationForm } from '@/components/dashboard/participation-form'
import { contestService } from '@/services/contest-service'
// REST API
import ApiService from '@/lib/api-service'
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
  const contestantIdParam = searchParams.get('contestantId')
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
  const [activeRounds, setActiveRounds] = useState<any[]>([])
  const [hasActiveSubmissionRound, setHasActiveSubmissionRound] = useState<boolean>(true)

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
  const [hasError, setHasError] = useState(false) // Prevent infinite retry loop
  const errorShownRef = useRef(false) // Track if error was already shown

  // REST Data Fetching - Optimized with error handling
  const fetchContestDetails = useCallback(async () => {
    if (!contestId || hasError) return // Don't retry if error occurred

    const abortController = new AbortController()

    try {
      // Need to fetch contest + enrichment (participants etc)
      // Currently getContest returns everything if backend is updated
      const c = await ApiService.getContest(parseInt(contestId)) as any

      // Check if aborted
      if (abortController.signal.aborted) return

      // Fetch rounds for this contest (optional, not blocking submissions)
      try {
        const rounds = await contestService.getRoundsForContest(contestId)
        setActiveRounds(rounds || [])
        // Always allow submissions regardless of rounds status (only deadline matters)
        setHasActiveSubmissionRound(true)
      } catch (roundsError) {
        console.error('Failed to fetch rounds:', roundsError)
        // Always allow submissions even if rounds fetch fails
        setHasActiveSubmissionRound(true)
        setActiveRounds([])
      }

      // Data Mapping
      // 1. Check Profile Completeness
      if (user && (!(user as any)?.first_name || !(user as any)?.last_name || !(user as any)?.country || !(user as any)?.city || !(user as any)?.continent)) {
        if (contestId) sessionStorage.setItem('contestId', contestId)
        setNeedsProfileSetup(true)
      } else {
        setNeedsProfileSetup(false)
      }

      // Check KYC status
      if (user && !user?.is_verified) {
        setNeedsKYC(true)
      }

      // 2. Set Contest Data
      setContest({
        ...c,
        submission_end_date: c.submission_end_date,
        is_submission_open: c.is_submission_open,
        requires_kyc: c.requires_kyc,
        requires_visual_verification: c.requires_visual_verification,
        requires_voice_verification: c.requires_voice_verification,
        requires_brand_verification: c.requires_brand_verification,
        requires_content_verification: c.requires_content_verification,
        requires_video: c.requires_video,
        max_videos: c.max_videos,
        video_max_duration: c.video_max_duration,
        video_max_size_mb: c.video_max_size_mb,
        current_user_contesting: c.current_user_contesting || false,
        currentUserContesting: c.current_user_contesting || false,
        min_images: c.min_images,
        max_images: c.max_images,
        verification_video_max_duration: c.verification_video_max_duration,
        verification_max_size_mb: c.verification_max_size_mb,
        voting_type: c.voting_type,
        participant_type: c.participant_type
      })

      setIsNomination(c.voting_type != null)

      // 3. User Participation check - check both current_user_participation and current_user_contesting
      // Also check if user has any contestant for this contest
      let participationToUse: any = c.current_user_participation
      
      // If no participation found but current_user_contesting is true, fetch the contestant
      if (!participationToUse && (c.current_user_contesting || c.currentUserContesting) && user?.id) {
        try {
          // Fetch user's contestant for this contest
          const userContestants = await contestService.getContestantsByContest(contestId, { user_id: user.id })
          if (userContestants && userContestants.length > 0) {
            participationToUse = userContestants[0]
          }
        } catch (err) {
          console.warn('Could not load user contestant:', err)
        }
      }
      
      // Prefer specific contestant when contestantId in URL (from My Applications)
      if (isEditMode && contestantIdParam && user?.id) {
        try {
          const specificContestant = await contestService.getContestantById(Number(contestantIdParam))
          if (specificContestant && Number(specificContestant.contest_id) === Number(contestId) && specificContestant.user_id === user.id) {
            participationToUse = specificContestant
          }
        } catch (err) {
          console.warn('Could not load specific contestant for edit:', err)
        }
      }
      
      if (participationToUse || c.current_user_contesting || c.currentUserContesting) {
        setUserAlreadyParticipating(true)
        if (participationToUse) {
          setParticipantId(participationToUse.id)
        }

        let imageUrls: string[] = []
        try {
          imageUrls = participationToUse.image_media_ids ? JSON.parse(participationToUse.image_media_ids) : []
        } catch (e) { imageUrls = [] }

        let videoUrl = ''
        try {
          const vids = participationToUse.video_media_ids ? JSON.parse(participationToUse.video_media_ids) : []
          videoUrl = Array.isArray(vids) && vids.length > 0 ? vids[0] : ''
        } catch (e) { videoUrl = '' }

        setExistingParticipationData({
          title: participationToUse.title || '',
          description: participationToUse.description || '',
          imageUrls: imageUrls,
          videoUrl: videoUrl,
          nominatorCity: participationToUse.nominator_city || '',
          nominatorCountry: participationToUse.nominator_country || ''
        })

        if (isEditMode) setIsEditingParticipation(true)
      }

      // 4. Verification Check
      const needsVerification =
        c.requires_kyc ||
        c.requires_visual_verification ||
        c.requires_voice_verification ||
        c.requires_brand_verification ||
        c.requires_content_verification

      if (needsVerification && !isEditMode) {
        const kycDone = !c.requires_kyc || user?.identity_verified
        const visualDone = !c.requires_visual_verification || hasVisualVerification
        const voiceDone = !c.requires_voice_verification || hasVoiceVerification
        const brandDone = !c.requires_brand_verification || hasBrandVerification
        const contentDone = !c.requires_content_verification || hasContentVerification

        if (!kycDone || !visualDone || !voiceDone || !brandDone || !contentDone) {
          setShowVerificationDialog(true)
        }
      }

      setPageLoading(false)

    } catch (error: any) {
      // Ignore aborted requests
      if (error?.name === 'AbortError' || abortController.signal.aborted) {
        return
      }
      
      // Set error flag to prevent retry loop
      setHasError(true)
      setPageLoading(false)
      
      // Only show error once per contestId
      if (!errorShownRef.current) {
        errorShownRef.current = true
        // Handle CORS and network errors gracefully
        if (error?.code === 'ERR_NETWORK' || error?.message?.includes('CORS') || error?.message?.includes('Network Error')) {
          addToast(t('dashboard.contests.network_error') || "Network error. Please check your connection and try again.", 'error')
        } else {
          addToast(t('dashboard.contests.load_error') || "Failed to load contest", 'error')
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contestId, user?.id, isEditMode, contestantIdParam, hasVisualVerification, hasVoiceVerification, hasBrandVerification, hasContentVerification, hasError])

  useEffect(() => {
    // Reset error state when contestId changes
    if (contestId) {
      setHasError(false)
      errorShownRef.current = false
      fetchContestDetails()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contestId]) // Only depend on contestId to prevent infinite loops

  // Calculer le temps restant jusqu'au 28 février 2026 (ou submission_end_date si plus tard)
  useEffect(() => {
    // Default deadline: February 28, 2026
    const defaultDeadline = new Date('2026-02-28')
    defaultDeadline.setHours(23, 59, 59, 999)
    
    // Use submission_end_date if available, otherwise use default deadline
    let submissionDeadline = defaultDeadline
    if (contest?.submission_end_date) {
      const endDate = new Date(contest.submission_end_date)
      endDate.setHours(23, 59, 59, 999)
      // Use the later date between default deadline and actual end date
      submissionDeadline = endDate > defaultDeadline ? endDate : defaultDeadline
    }

    const updateTimeRemaining = () => {
      const now = new Date().getTime()
      const endDate = submissionDeadline.getTime()
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

    updateTimeRemaining()
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

  // Helper function to check if submissions are actually open
  // Only checks deadline date - allows submissions regardless of active rounds
  const isSubmissionActuallyOpen = useCallback((contestData: any): boolean => {
    if (!contestData) return false
    
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    
    // Default deadline: February 28, 2026
    const defaultDeadline = new Date('2026-02-28')
    defaultDeadline.setHours(23, 59, 59, 999)
    
    // Use submission_end_date if available, otherwise use default deadline
    let submissionDeadline = defaultDeadline
    if (contestData.submission_end_date) {
      const endDate = new Date(contestData.submission_end_date)
      endDate.setHours(23, 59, 59, 999)
      // Use the later date between default deadline and actual end date
      submissionDeadline = endDate > defaultDeadline ? endDate : defaultDeadline
    }
    
    // Check if deadline has passed
    const isDeadlinePassed = today > submissionDeadline
    
    // Submissions are open if deadline hasn't passed (rounds check removed)
    return !isDeadlinePassed
  }, [])




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
    videoMediaIds?: string,
    nominatorCity?: string,
    nominatorCountry?: string
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
          videoMediaIds,
          nominatorCity,
          nominatorCountry
        )
      } else {
        // Créer une nouvelle candidature
        response = await contestService.submitContestant(
          contestId,
          title,
          description,
          imageMediaIds,
          videoMediaIds,
          nominatorCity,
          nominatorCountry
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
      
      // Try to get error detail from different possible locations
      let errorDetail = ''
      if (err?.response?.data?.detail) {
        errorDetail = typeof err.response.data.detail === 'string' 
          ? err.response.data.detail 
          : JSON.stringify(err.response.data.detail)
      } else if (err?.response?.data?.message) {
        errorDetail = err.response.data.message
      } else if (err?.message) {
        errorDetail = err.message
      }

      // Log the full error for debugging
      console.error('Full error response:', err?.response?.data)
      console.error('Error detail:', errorDetail)

      // Détecter le type d'erreur et utiliser les traductions appropriées
      let errorMessage = t('dashboard.contests.participation_form.error.submit_error') || 'An error occurred while submitting'

      if (errorDetail) {
        const errorLower = errorDetail.toLowerCase()

        // Détecter les erreurs de pays du nominateur
        if (errorLower.includes('nominator country') || errorLower.includes('country must match')) {
          errorMessage = errorDetail // Show the actual backend message
        }
        // Détecter les erreurs de genre
        else if (errorLower.includes('masculin') || errorLower.includes('male') || errorLower.includes('male participants only')) {
          errorMessage = t('dashboard.contests.participation_form.error.gender_restriction_male') || errorDetail
        } else if (errorLower.includes('féminin') || errorLower.includes('female') || errorLower.includes('female participants only')) {
          errorMessage = t('dashboard.contests.participation_form.error.gender_restriction_female') || errorDetail
        } else if (errorLower.includes('genre') || errorLower.includes('gender') || errorLower.includes('gender information')) {
          errorMessage = t('dashboard.contests.participation_form.error.gender_not_set') || errorDetail
        }
        // Détecter les erreurs de soumission déjà effectuée
        else if (errorLower.includes('already') && (errorLower.includes('submission') || errorLower.includes('candidature'))) {
          errorMessage = t('dashboard.contests.participation_form.error.already_submitted') || errorDetail
        }
        // Détecter les erreurs de soumission fermée (including "no active rounds")
        else if (errorLower.includes('closed') || errorLower.includes('fermée') || errorLower.includes('fermé') || errorLower.includes('not open') || errorLower.includes('no active rounds') || errorLower.includes('no active rounds accepting submissions')) {
          // Use the backend error message directly as it's more specific
          errorMessage = errorDetail || t('dashboard.contests.participation_form.error.submission_closed') || 'Submissions are closed for this contest.'
        }
        // Détecter les erreurs de date limite
        else if (errorLower.includes('deadline') || errorLower.includes('date limite') || errorLower.includes('dépassée') || errorLower.includes('passed')) {
          errorMessage = t('dashboard.contests.participation_form.error.deadline_passed') || errorDetail
        }
        // Détecter les erreurs de validation
        else if (errorLower.includes('validation') || errorLower.includes('required') || errorLower.includes('invalid')) {
          errorMessage = errorDetail
        }
        // Utiliser le message d'erreur du backend s'il est disponible
        else {
          errorMessage = errorDetail
        }
      }

      // Display the error message to the user
      addToast(errorMessage, 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Only block full page for initial AUTH check. 
  // Once auth loaded, we use skeletons inside the layout.
  if (isLoading) {
    // Keep full skeleton for auth check to avoid redirect flash
    return <ParticipateFormSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }


  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-start justify-center py-8 overflow-hidden">
      <div className="w-full max-w-3xl relative px-4">
        {/* Participation Form */}
        <div>
          {pageLoading ? (
            <ParticipateFormSkeleton />
          ) : (
            <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-1 md:p-1 sticky top-4 space-y-6">
              {/* Already Participating Alert */}
              {userAlreadyParticipating && !isEditingParticipation && !submitSuccess && (
                <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg space-y-3">
                  <p className="text-blue-900 dark:text-blue-200">
                    {t('dashboard.contests.participation_form.already_participating')}
                  </p>
                  {isSubmissionActuallyOpen(contest) && (
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
                    {isEditingParticipation
                      ? (t('dashboard.contests.participation_form.edit_title') || 'Edit a Contestant')
                      : isNomination
                        ? (t('dashboard.contests.participation_form.nominate_title') || 'Nominate a Contestant')
                        : (t('dashboard.contests.participation_form.title') || 'Participate in Contest')
                    }
                  </h2>
                  <p className="text-gray-600 dark:text-gray-400 mb-4 text-sm">
                    {isEditingParticipation
                      ? (t('dashboard.contests.participation_form.edit_description') || 'Update your submission details')
                      : isNomination
                        ? (t('dashboard.contests.participation_form.nominate_description') || 'Import your video from YouTube or Vimeo')
                        : t('dashboard.contests.participation_form.description')
                    }
                  </p>

                  {/* Deadline Countdown - Show for nominations and participations */}
                  {!isEditingParticipation && !submitSuccess && timeValues && !timeValues.isNA && (
                    <div className="mb-6 p-4 bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                          <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                            {isNomination 
                              ? (t('dashboard.contests.time_remaining_to_nominate') || 'Time remaining to nominate')
                              : (t('dashboard.contests.time_remaining_to_participate') || 'Time remaining to participate')
                            }:
                          </span>
                        </div>
                        {timeValues.isClosed ? (
                          <span className="text-red-600 dark:text-red-400 font-bold text-lg">
                            {t('dashboard.contests.closed') || 'Closed'}
                          </span>
                        ) : (
                          <div className="flex items-center gap-2">
                            {timeValues.days > 0 && (
                              <span className="px-3 py-1 bg-blue-500 text-white rounded-lg font-bold text-lg">
                                {timeValues.days}{t('dashboard.contests.time_unit_days') || 'd'}
                              </span>
                            )}
                            <span className="px-3 py-1 bg-blue-500 text-white rounded-lg font-bold text-lg">
                              {String(timeValues.hours).padStart(2, '0')}{t('dashboard.contests.time_unit_hours') || 'h'}
                            </span>
                            <span className="px-3 py-1 bg-blue-500 text-white rounded-lg font-bold text-lg">
                              {String(timeValues.minutes).padStart(2, '0')}{t('dashboard.contests.time_unit_minutes') || 'm'}
                            </span>
                            {timeValues.days === 0 && (
                              <span className="px-3 py-1 bg-purple-500 text-white rounded-lg font-bold text-lg animate-pulse">
                                {String(timeValues.seconds).padStart(2, '0')}{t('dashboard.contests.time_unit_seconds') || 's'}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                      {!timeValues.isClosed && (
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                          {t('Deadline countdown') || 'Deadline: February 28, 2026'}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Participation Form - DISPLAYED FIRST */}
                  {!needsProfileSetup && isSubmissionActuallyOpen(contest) && (
                    <ParticipationForm
                      contestId={contestId}
                      onSubmit={handleParticipationSubmit}
                      onCancel={handleCancel}
                      isSubmitting={isSubmitting}
                      isEditing={isEditingParticipation}
                      initialData={{
                        ...existingParticipationData,
                        // Set default nominator country to user's country for nominations
                        nominatorCountry: existingParticipationData?.nominatorCountry || (isNomination && user?.country ? user.country : undefined)
                      }}
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

                  {/* Profile Setup Alert - DISPLAYED AFTER FORM */}
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
                  {contest && !isSubmissionActuallyOpen(contest) && (
                    <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg mb-4">
                      <p className="text-red-900 dark:text-red-200 font-medium">
                        🚫 {t('dashboard.contests.submission_closed') || 'Submissions are closed for this contest.'}
                      </p>
                      <p className="text-red-700 dark:text-red-300 text-sm mt-1">
                        {t('dashboard.contests.submission_closed_message') || 'The submission deadline has passed.'}
                      </p>
                    </div>
                  )}
                </>
              )}

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
                  {isSubmissionActuallyOpen(contest) && (
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
                  {isSubmissionActuallyOpen(contest) && (
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

