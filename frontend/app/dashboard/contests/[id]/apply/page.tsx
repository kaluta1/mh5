'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useRouter, useParams, useSearchParams } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'

import { ParticipationForm } from '@/components/dashboard/participation-form'
import { contestService } from '@/services/contest-service'
// REST API
import ApiService from '@/lib/api-service'
import { getRoundNominationDeadlineMs } from '@/lib/nomination-deadline'
import { verificationService } from '@/services/verification-service'
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
  const { user } = useAuth()
  const { addToast } = useToast()

  const contestId = params?.id as string
  const roundIdParam = searchParams.get('roundId')
  const isEditMode = searchParams.get('edit') === 'true'
  const contestantIdParam = searchParams.get('contestantId')
  // If `entryType` is missing in the URL, do NOT default to 'participation' here.
  // We must default based on the contest's `contest_mode` once the contest is loaded.
  const entryTypeParam = searchParams.get('entryType')
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
  const [hasActiveSubmissionRound, setHasActiveSubmissionRound] = useState<boolean>(true)
  const [roundData, setRoundData] = useState<any>(null)

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
  const [verificationStatusLoaded, setVerificationStatusLoaded] = useState(false)
  const [hasError, setHasError] = useState(false) // Prevent infinite retry loop
  const errorShownRef = useRef(false) // Track if error was already shown

  // REST Data Fetching - Optimized with error handling
  const fetchContestDetails = useCallback(async () => {
    if (!contestId || hasError) return // Don't retry if error occurred

    const abortController = new AbortController()

    try {
      // Fetch contest details only, as roundId is passed via URL if specific round is targeted
      const c = await ApiService.getContest(parseInt(contestId)) as any

      setHasActiveSubmissionRound(true) // Always allow submissions regardless of rounds status (only deadline matters)

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
        contest_mode: c.contest_mode,
        participant_type: c.participant_type
      })

      // Determine effective entry type based on query param (if present) or contest mode.
      // If the URL param is missing and we don't find a match, we'll retry the "other" entry type.
      let expectedEntryType = entryTypeParam || (c.contest_mode === 'nomination' ? 'nomination' : 'participation')
      setIsNomination(expectedEntryType === 'nomination')

      // 3. User Participation check
      // The backend returns current_user_participation by season (ignores round_id and entry_type)
      // We must filter it ourselves to allow: different rounds + nomination vs participation
      let participationToUse: any = null

      // First try backend's current_user_participation (filtered by contest_mode on backend)
      // Reuse the same effective entry type for participation matching.
      // (expectedEntryType already computed above)
      if (c.current_user_participation) {
        const p = c.current_user_participation
        const pRoundId = p.round_id
        const pSeasonId = p.season_id
        const pEntryType = p.entry_type

        // Match by round, contest AND entry_type
        const roundMatch = !roundIdParam || !pRoundId || pRoundId === parseInt(roundIdParam)
        const contestMatch = !pSeasonId || pSeasonId === parseInt(contestId)
        const typeMatch = !pEntryType || pEntryType === expectedEntryType

        if (roundMatch && contestMatch && typeMatch) {
          participationToUse = p
        }
      }

      // If not found via backend, try fetching all user contestants and filter properly
      if (!participationToUse && user?.id) {
        try {
          const userContestants = await contestService.getContestantsByContest(contestId, { user_id: user.id })
          if (userContestants && userContestants.length > 0) {
            // Find a contestant matching round_id, contest AND entry_type
            const findMatchingEntryForType = (desiredEntryType: string) => {
              return userContestants.find((uc: any) => {
                const ucRoundId = uc.round_id
                const ucSeasonId = uc.season_id
                const ucEntryType = uc.entry_type
                const roundMatch = !roundIdParam || !ucRoundId || ucRoundId === parseInt(roundIdParam)
                const contestMatch = !ucSeasonId || ucSeasonId === parseInt(contestId)
                const typeMatch = !ucEntryType || ucEntryType === desiredEntryType
                return roundMatch && contestMatch && typeMatch
              })
            }

            // First attempt with expectedEntryType
            const matchingEntry = findMatchingEntryForType(expectedEntryType)
            if (matchingEntry) {
              participationToUse = matchingEntry
            } else if (entryTypeParam === null) {
              // URL entryType missing: retry with the other entry type
              const altEntryType = expectedEntryType === 'nomination' ? 'participation' : 'nomination'
              const altMatch = findMatchingEntryForType(altEntryType)
              if (altMatch) {
                expectedEntryType = altEntryType
                participationToUse = altMatch
              }
            }
          }
        } catch (err) {
          console.warn('Could not load user contestant:', err)
        }
      }

      // Prefer specific contestant when contestantId in URL (from My Applications)
      if (isEditMode && contestantIdParam && user?.id) {
        try {
          const specificContestant = await contestService.getContestantById(Number(contestantIdParam))
          // Use season_id to verify contest ownership (contestants have no contest_id column)
          if (specificContestant && specificContestant.user_id === user.id) {
            const scSeasonId = specificContestant.season_id
            if (!scSeasonId || scSeasonId === parseInt(contestId)) {
              participationToUse = specificContestant
            }
          }
        } catch (err) {
          console.warn('Could not load specific contestant for edit:', err)
        }
      }

      // Only block if we found a contestant matching the SAME entry_type AND round
      if (participationToUse) {
        // Keep UI mode consistent with the actual entry type we found.
        if (participationToUse?.entry_type) {
          setIsNomination(participationToUse.entry_type === 'nomination')
        }
        setUserAlreadyParticipating(true)
        setParticipantId(participationToUse.id)

        let imageUrls: string[] = []
        try {
          imageUrls = participationToUse?.image_media_ids ? JSON.parse(participationToUse.image_media_ids) : []
        } catch (e) { imageUrls = [] }

        let videoUrl = ''
        try {
          const vids = participationToUse?.video_media_ids ? JSON.parse(participationToUse.video_media_ids) : []
          videoUrl = Array.isArray(vids) && vids.length > 0 ? vids[0] : ''
        } catch (e) { videoUrl = '' }

        setExistingParticipationData({
          title: participationToUse?.title || '',
          description: participationToUse?.description || '',
          imageUrls: imageUrls,
          videoUrl: videoUrl,
          nominatorCity: participationToUse?.nominator_city || '',
          nominatorCountry: participationToUse?.nominator_country || ''
        })

        // Toujours activer le mode édition si une participation existe
        setIsEditingParticipation(true)
      }

      // Fetch round data if roundId provided in URL
      if (roundIdParam) {
        try {
          const round = await ApiService.getRound(parseInt(roundIdParam))
          setRoundData(round)
        } catch (err) {
          console.warn('Could not load round data:', err)
        }
      }

      setPageLoading(false)

    } catch (error) {
      console.error("Failed to fetch contest:", error)
      addToast(t('dashboard.contests.load_error') || "Failed to load contest", 'error')
      setPageLoading(false)
    }
  }, [contestId, user?.id, isEditMode, contestantIdParam, addToast, t])

  useEffect(() => {
    // Reset error state when contestId changes
    if (contestId) {
      setHasError(false)
      errorShownRef.current = false
      fetchContestDetails()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contestId]) // Only depend on contestId to prevent infinite loops

  // Load real verification status from backend API
  useEffect(() => {
    if (!user?.id || verificationStatusLoaded) return
    const loadVerificationStatus = async () => {
      try {
        const status = await verificationService.getMyVerificationsStatus()
        if (status) {
          // has_selfie covers selfie/selfie_with_pet/selfie_with_document
          if (status.has_selfie) setHasVisualVerification(true)
          if (status.has_voice) setHasVoiceVerification(true)
          if (status.has_brand) setHasBrandVerification(true)
          if (status.has_content) setHasContentVerification(true)
          setVerificationStatusLoaded(true)
        }
      } catch (err) {
        console.warn('Could not load verification status:', err)
      }
    }
    loadVerificationStatus()
  }, [user?.id, verificationStatusLoaded])

  const contestRequiresVerification = useMemo(() => {
    if (!contest) return false
    return !!(
      contest.requires_kyc ||
      contest.requires_visual_verification ||
      contest.requires_voice_verification ||
      contest.requires_brand_verification ||
      contest.requires_content_verification
    )
  }, [contest])

  const allVerificationRequirementsMet = useMemo(() => {
    if (!contest || !contestRequiresVerification) return true
    const kycDone =
      !contest.requires_kyc ||
      !!(user?.identity_verified || (user as { is_verified?: boolean })?.is_verified)
    const visualDone = !contest.requires_visual_verification || hasVisualVerification
    const voiceDone = !contest.requires_voice_verification || hasVoiceVerification
    const brandDone = !contest.requires_brand_verification || hasBrandVerification
    const contentDone = !contest.requires_content_verification || hasContentVerification
    return kycDone && visualDone && voiceDone && brandDone && contentDone
  }, [
    contest,
    contestRequiresVerification,
    user,
    hasVisualVerification,
    hasVoiceVerification,
    hasBrandVerification,
    hasContentVerification,
  ])

  const blockedByVerification =
    !isEditingParticipation &&
    contestRequiresVerification &&
    verificationStatusLoaded &&
    !allVerificationRequirementsMet

  useEffect(() => {
    if (pageLoading || !contest || isEditingParticipation) return
    if (!contestRequiresVerification) {
      setShowVerificationDialog(false)
      return
    }
    if (!verificationStatusLoaded) return
    setShowVerificationDialog(!allVerificationRequirementsMet)
  }, [
    pageLoading,
    contest,
    isEditingParticipation,
    contestRequiresVerification,
    verificationStatusLoaded,
    allVerificationRequirementsMet,
  ])

  const handleVerificationDialogClose = () => {
    setShowVerificationDialog(false)
    router.push(contestId ? `/dashboard/contests/${contestId}` : '/dashboard/contests')
  }

  // Temps restant jusqu'à la fin des nominations (grâce + extension alignée jour de vote — voir backend)
  useEffect(() => {
    if (!roundData?.submission_end_date) {
      setTimeValues({ days: 0, hours: 0, minutes: 0, seconds: 0, isClosed: false, isNA: true })
      return
    }

    const endMs = getRoundNominationDeadlineMs({
      submission_end_date: roundData.submission_end_date,
      voting_start_date: roundData.voting_start_date
    })
    if (endMs == null) {
      setTimeValues({ days: 0, hours: 0, minutes: 0, seconds: 0, isClosed: false, isNA: true })
      return
    }

    const updateTimeRemaining = () => {
      const difference = endMs - new Date().getTime()

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
  }, [roundData?.submission_end_date, roundData?.voting_start_date])

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

  // Auth redirect is handled by dashboard/layout.tsx

  // Vérifie si les soumissions sont encore ouvertes (basé sur la date du round)
  const isSubmissionActuallyOpen = useCallback((_contestData: any): boolean => {
    if (!roundData?.submission_end_date) return true

    const endMs = getRoundNominationDeadlineMs({
      submission_end_date: roundData.submission_end_date,
      voting_start_date: roundData.voting_start_date
    })
    if (endMs == null) return true
    return Date.now() <= endMs
  }, [roundData?.submission_end_date, roundData?.voting_start_date])




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
    if (
      !isEditingParticipation &&
      contest &&
      contestRequiresVerification &&
      !allVerificationRequirementsMet
    ) {
      addToast(
        t('verification.incomplete_warning') ||
          'Complétez toutes les vérifications requises avant de participer.',
        'error'
      )
      return
    }

    setIsSubmitting(true)

    try {
      let response
      // Legal guard: nominations must never carry image uploads.
      const safeImageMediaIds = isNomination ? undefined : imageMediaIds

      if (isEditingParticipation && participantId) {
        // Mettre à jour la candidature existante
        response = await contestService.updateContestant(
          participantId,
          title,
          description,
          safeImageMediaIds,
          videoMediaIds,
          nominatorCity,
          nominatorCountry
        )
      } else {
        // Créer une nouvelle candidature
        // Provide the active round ID given via URL query params
        const roundId = roundIdParam ? parseInt(roundIdParam, 10) : undefined;

        response = await contestService.submitContestant(
          contestId,
          title,
          description,
          safeImageMediaIds,
          videoMediaIds,
          nominatorCity,
          nominatorCountry,
          roundId,
          isNomination ? 'nomination' : 'participation'
        )
      }

      setSubmitSuccess(true)
      setUserAlreadyParticipating(true)

      // Mettre à jour les données existantes avec les nouvelles valeurs
      if (isEditingParticipation) {
        let updatedImageUrls: string[] = []
        try {
          updatedImageUrls = safeImageMediaIds ? JSON.parse(typeof safeImageMediaIds === 'string' ? safeImageMediaIds : JSON.stringify(safeImageMediaIds)) : []
          if (!Array.isArray(updatedImageUrls)) updatedImageUrls = []
        } catch { updatedImageUrls = [] }

        let updatedVideoUrl = ''
        try {
          const vids = videoMediaIds ? JSON.parse(typeof videoMediaIds === 'string' ? videoMediaIds : JSON.stringify(videoMediaIds)) : []
          updatedVideoUrl = Array.isArray(vids) && vids.length > 0 ? vids[0] : ''
        } catch { updatedVideoUrl = '' }

        setExistingParticipationData({
          title: title || '',
          description: description || '',
          imageUrls: updatedImageUrls,
          videoUrl: updatedVideoUrl,
          nominatorCity: nominatorCity || '',
          nominatorCountry: nominatorCountry || ''
        })
      }

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

  // Auth is handled by dashboard/layout.tsx - no need to check here


  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-4 sm:py-6 md:py-8">
      <div className="max-w-3xl mx-auto px-3 sm:px-4 md:px-6">
        {/* Back Button */}
        <button
          onClick={() => router.back()}
          className="mb-4 flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('common.back') || 'Retour'}
        </button>

        {/* Participation Form - Always visible, no skeleton wrapper */}
        <div className="bg-white dark:bg-gray-800/90 backdrop-blur-sm rounded-xl sm:rounded-2xl border border-gray-200 dark:border-gray-700/50 shadow-xl p-4 sm:p-6 md:p-8 space-y-4 sm:space-y-6">
          {/* Already Participating Alert */}
          {userAlreadyParticipating && !isEditingParticipation && !submitSuccess && (
            <div className="p-3 sm:p-4 bg-blue-900/20 border border-blue-800/50 rounded-xl space-y-3">
              <p className="text-blue-200">
                {t('dashboard.contests.participation_form.already_participating')}
              </p>
              {isSubmissionActuallyOpen(contest) && (
                <button
                  onClick={() => {
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
              <h2 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white mb-1 sm:mb-2">
                {isEditingParticipation
                  ? (t('dashboard.contests.participation_form.edit_title') || 'Edit a Contestant')
                  : isNomination
                    ? (t('dashboard.contests.participation_form.nominate_title') || 'Nominate a Contestant')
                    : (t('dashboard.contests.participation_form.title') || 'Participate in Contest')
                }
              </h2>
              <p className="text-gray-500 dark:text-gray-400 mb-3 sm:mb-4 text-xs sm:text-sm">
                {isEditingParticipation
                  ? (t('dashboard.contests.participation_form.edit_description') || 'Update your submission details')
                  : isNomination
                    ? (t('dashboard.contests.participation_form.nominate_description') || 'Import your video from YouTube or TikTok')
                    : t('dashboard.contests.participation_form.description')
                }
              </p>

              {/* Countdown is now integrated in the ParticipationForm stepper */}

              {contestRequiresVerification && !isEditingParticipation && !verificationStatusLoaded && (
                <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50 text-sm text-gray-600 dark:text-gray-300">
                  {t('common.loading') || 'Chargement du statut de vérification...'}
                </div>
              )}

              {blockedByVerification && (
                <div className="p-4 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 text-sm text-amber-900 dark:text-amber-100">
                  {t('verification.incomplete_warning') ||
                    'Complétez toutes les vérifications dans la fenêtre pour accéder au formulaire.'}
                </div>
              )}

              {/* Participation Form — hidden until verification requirements are satisfied */}
              {!blockedByVerification &&
                !(contestRequiresVerification && !isEditingParticipation && !verificationStatusLoaded) && (
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
                  roundData={roundData}
                  roundId={roundIdParam ? parseInt(roundIdParam, 10) : undefined}
                  contestantId={participantId ?? undefined}
                />
              )}

              {/* Profile Setup Alert - DISPLAYED AFTER FORM */}
              {needsProfileSetup && (
                <div className="p-3 sm:p-4 bg-yellow-900/20 border border-yellow-800/50 rounded-xl mb-3 sm:mb-4">
                  <p className="text-yellow-200 mb-3 text-sm">
                    {t('participation.profile_incomplete_title')} {t('participation.profile_incomplete_message')}
                  </p>
                  <button
                    onClick={() => router.push('/dashboard/settings')}
                    className="w-full px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg font-medium transition text-sm"
                  >
                    {t('participation.complete_profile_button')}
                  </button>
                </div>
              )}

              {/* KYC Notification (optionnel) - Ne pas afficher pour les nominations */}
              {needsKYC && !isNomination && (
                <div className="p-3 sm:p-4 bg-amber-900/20 border border-amber-800/50 rounded-xl mb-3 sm:mb-4">
                  <p className="text-amber-200 text-sm">
                    {t('participation.kyc_notification') || '⚠️ Votre identité n\'a pas été vérifiée. Nous vous recommandons de compléter votre vérification KYC pour une meilleure expérience.'}
                  </p>
                </div>
              )}

              {/* Submission Closed Alert */}
              {contest && !isSubmissionActuallyOpen(contest) && (
                <div className="p-3 sm:p-4 bg-red-900/20 border border-red-800/50 rounded-xl mb-3 sm:mb-4">
                  <p className="text-red-200 font-medium">
                    🚫 {t('dashboard.contests.submission_closed') || 'Submissions are closed for this contest.'}
                  </p>
                  <p className="text-red-300 text-sm mt-1">
                    {t('dashboard.contests.submission_closed_message') || 'The submission deadline has passed.'}
                  </p>
                </div>
              )}
            </>
          )}

          {/* Success Message */}
          {submitSuccess && (
            <div className="p-3 sm:p-4 bg-green-900/20 border border-green-800/50 rounded-xl space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div>
                  <p className="text-green-200 font-semibold">
                    {t('dashboard.contests.participation_form.success_title') || '✅ Candidature soumise avec succès !'}
                  </p>
                  <p className="text-green-300 text-sm mt-1">
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

        </div>
      </div>

      {/* Verification Dialogs */}
      {contest && (
        <>
          <VerificationRequirementsDialog
            isOpen={showVerificationDialog}
            onClose={handleVerificationDialogClose}
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
              isKycVerified: !!(user?.identity_verified || (user as { is_verified?: boolean })?.is_verified),
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

