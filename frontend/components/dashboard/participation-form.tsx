'use client'

import React, { useState, useEffect, useRef, useMemo } from 'react'
import dynamic from 'next/dynamic'
import { X, Upload, FileText, Image as ImageIcon, Video, Eye, Link, Plus, AlertCircle, CheckCircle, Loader2, MapPin, Globe, ChevronRight, ChevronLeft, Clock, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ImagePreviewDialog } from '@/components/ui/image-preview-dialog'
import { VideoPreviewDialog } from '@/components/ui/video-preview-dialog'
import { VideoEmbed } from '@/components/ui/video-embed'
import { useLanguage } from '@/contexts/language-context'
import { useRouter } from 'next/navigation'
import { useModeratedUpload } from '@/hooks/use-moderated-upload'
import { useToast } from '@/components/ui/toast'
import { isValidVideoUrl, detectVideoPlatform, cleanVideoUrl } from '@/lib/utils/video-platforms'
import { countries } from '@/lib/countries'
import { getCitiesByCountry } from '@/lib/geography'

// WYSIWYG Editor - chargé dynamiquement pour éviter les erreurs SSR
const ReactQuill = dynamic(() => import('react-quill'), { ssr: false, loading: () => <div className="w-full h-40 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center"><Loader2 className="w-6 h-6 text-gray-400 animate-spin" /></div> })

interface MediaRequirements {
  requiresVideo?: boolean
  maxVideos?: number
  videoMaxDuration?: number
  videoMaxSizeMb?: number
  minImages?: number
  maxImages?: number
}

interface ParticipationFormProps {
  contestId: string
  onSubmit?: (
    title: string,
    description: string,
    imageMediaIds?: string,
    videoMediaIds?: string,
    nominatorCity?: string,
    nominatorCountry?: string
  ) => Promise<void>
  onCancel?: () => void
  isSubmitting?: boolean
  isEditing?: boolean
  initialData?: {
    title?: string
    description?: string
    imageUrls?: string[]
    videoUrl?: string
    nominatorCity?: string
    nominatorCountry?: string
  }
  mediaRequirements?: MediaRequirements
  isNomination?: boolean
  roundData?: {
    submission_start_date?: string
    submission_end_date?: string
    name?: string
  } | null
}

const QUILL_MODULES = {
  toolbar: [
    [{ 'header': [1, 2, 3, false] }],
    ['bold', 'italic', 'underline', 'strike'],
    [{ 'list': 'ordered'}, { 'list': 'bullet' }],
    ['blockquote'],
    ['clean']
  ],
}

const QUILL_FORMATS = [
  'header', 'bold', 'italic', 'underline', 'strike',
  'list', 'bullet', 'blockquote'
]

// Plateformes vidéo supportées pour l'affichage
const VIDEO_PLATFORMS = [
  { name: 'YouTube', bg: 'bg-red-500/10 dark:bg-red-500/20 border-red-500/30 text-red-600 dark:text-red-300', url: 'https://www.youtube.com/@KalutaMall' },
  { name: 'TikTok', bg: 'bg-pink-500/10 dark:bg-pink-500/20 border-pink-500/30 text-pink-600 dark:text-pink-300', url: 'https://www.tiktok.com/@kalutamall' },
  { name: 'Facebook', bg: 'bg-blue-500/10 dark:bg-blue-500/20 border-blue-500/30 text-blue-600 dark:text-blue-300', url: 'https://www.facebook.com/KalutaMall/' },
  { name: 'Vimeo', bg: 'bg-cyan-500/10 dark:bg-cyan-500/20 border-cyan-500/30 text-cyan-600 dark:text-cyan-300', url: 'https://vimeo.com' },
]

export function ParticipationForm({ contestId, onSubmit, onCancel, isSubmitting: externalIsSubmitting, isEditing = false, initialData, mediaRequirements, isNomination = false, roundData }: ParticipationFormProps) {
  const { t } = useLanguage()
  const router = useRouter()
  const { addToast } = useToast()

  // Stepper state
  const [currentStep, setCurrentStep] = useState(0)
  const totalSteps = isNomination ? 3 : 3

  const hasAppliedInitialData = useRef(false)
  const [title, setTitle] = useState<string>(initialData?.title || '')
  const [description, setDescription] = useState<string>(initialData?.description || '')
  const [imageUrls, setImageUrls] = useState<string[]>(initialData?.imageUrls || [])
  const [videoUrl, setVideoUrl] = useState<string>(initialData?.videoUrl || '')

  // Synchroniser les données quand initialData arrive en retard (après fetch API)
  // N'appliquer qu'une seule fois pour ne pas écraser les modifications de l'utilisateur
  useEffect(() => {
    if (initialData && !hasAppliedInitialData.current) {
      // Ne marquer comme appliqué que si les données ont du contenu réel (pas juste un objet vide du spread)
      const hasContent = initialData.title || initialData.description || initialData.videoUrl ||
                         (initialData.imageUrls && initialData.imageUrls.length > 0)
      if (hasContent) {
        hasAppliedInitialData.current = true
      }
      if (initialData.title) setTitle(initialData.title)
      if (initialData.description) setDescription(initialData.description)
      if (initialData.imageUrls && initialData.imageUrls.length > 0) setImageUrls(initialData.imageUrls)
      if (initialData.videoUrl) setVideoUrl(initialData.videoUrl)
      if (initialData.nominatorCountry) setNominatorCountry(initialData.nominatorCountry)
      if (initialData.nominatorCity) setNominatorCity(initialData.nominatorCity)
    }
  }, [initialData])
  const [isSubmitting, setIsSubmitting] = useState(externalIsSubmitting || false)
  const [accessToken, setAccessToken] = useState<string>('')
  const [previewImageUrl, setPreviewImageUrl] = useState<string>('')
  const [previewVideoUrl, setPreviewVideoUrl] = useState<string>('')
  const [showImagePreview, setShowImagePreview] = useState(false)
  const [showVideoPreview, setShowVideoPreview] = useState(false)

  // URL import states
  const [showImageUrlInput, setShowImageUrlInput] = useState(false)
  const [showVideoUrlInput, setShowVideoUrlInput] = useState(false)
  const [imageUrlInput, setImageUrlInput] = useState('')
  const [videoUrlInput, setVideoUrlInput] = useState('')

  // Nomination location states
  const [nominatorCountry, setNominatorCountry] = useState<string>(initialData?.nominatorCountry || '')
  const [nominatorCity, setNominatorCity] = useState<string>(initialData?.nominatorCity || '')
  const [availableCities, setAvailableCities] = useState<string[]>([])
  const [loadingCities, setLoadingCities] = useState(false)

  // Countdown state
  const [countdown, setCountdown] = useState<{ days: number; hours: number; minutes: number; seconds: number; isClosed: boolean } | null>(null)

  // Media requirements with defaults
  const minImages = isNomination ? 0 : (mediaRequirements?.minImages ?? 1)
  const maxImages = mediaRequirements?.maxImages ?? 10
  const requiresVideo = isNomination ? true : (mediaRequirements?.requiresVideo ?? false)
  const maxVideos = mediaRequirements?.maxVideos ?? 1

  // Récupérer le token depuis localStorage
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (token) setAccessToken(token)
  }, [])

  // Countdown timer basé sur les dates du round
  useEffect(() => {
    if (!roundData?.submission_end_date) {
      setCountdown(null)
      return
    }

    const deadline = new Date(roundData.submission_end_date)
    deadline.setHours(23, 59, 59, 999)

    const update = () => {
      const diff = deadline.getTime() - Date.now()
      if (diff <= 0) {
        setCountdown({ days: 0, hours: 0, minutes: 0, seconds: 0, isClosed: true })
        return
      }
      setCountdown({
        days: Math.floor(diff / (1000 * 60 * 60 * 24)),
        hours: Math.floor((diff / (1000 * 60 * 60)) % 24),
        minutes: Math.floor((diff / 1000 / 60) % 60),
        seconds: Math.floor((diff / 1000) % 60),
        isClosed: false
      })
    }

    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [roundData?.submission_end_date])

  // Load cities when country changes (for nominations)
  useEffect(() => {
    setAvailableCities([])
    setLoadingCities(false)

    if (!isNomination || !nominatorCountry || !nominatorCountry.trim()) return

    const trimmedCountryName = nominatorCountry.trim()
    const country = countries.find(c => c.name.trim().toLowerCase() === trimmedCountryName.toLowerCase())
    if (!country || !country.code) return

    const currentCountryCode = country.code.toUpperCase().trim()
    if (!/^[A-Z]{2}$/.test(currentCountryCode)) return

    setLoadingCities(true)
    try {
      const cities = getCitiesByCountry(currentCountryCode)
      let cleanCities = Array.isArray(cities) ? Array.from(cities) : []

      if (currentCountryCode !== 'TZ' && cleanCities.length > 0) {
        const tanzaniaCities = new Set([
          'Dar es Salaam', 'Mwanza', 'Arusha', 'Dodoma', 'Mbeya', 'Zanzibar City',
          'Morogoro', 'Tanga', 'Mtwara', 'Tabora', 'Kigoma', 'Iringa',
          'Songea', 'Shinyanga', 'Musoma', 'Bukoba', 'Sumbawanga', 'Singida',
          'Lindi', 'Moshi', 'Kilimanjaro', 'Bagamoyo', 'Pemba', 'Unguja',
          'Stone Town', 'Kibaha', 'Ifakara', 'Mpanda', 'Kasulu', 'Njombe',
          'Babati', 'Geita', 'Kahama', 'Same', 'Korogwe', 'Handeni'
        ])
        cleanCities = cleanCities.filter(city => !tanzaniaCities.has(city))
      }

      if (cleanCities.length > 0) setAvailableCities(cleanCities)
    } catch (error) {
      console.error('Error loading cities:', error)
      setAvailableCities([])
    } finally {
      setLoadingCities(false)
    }
  }, [nominatorCountry, isNomination])

  // Hook pour upload modéré des images
  const imageUpload = useModeratedUpload({
    accessToken,
    onSuccess: (result) => {
      setImageUrls(prev => [...prev, result.url])
      addToast(t('participation.image_added') || 'Image ajoutée', 'success')
    },
    onError: (error, flags) => {
      if (flags && flags.length > 0) {
        addToast(t('moderation.content_rejected') || `⚠️ ${error}`, 'error')
      } else {
        addToast(`${t('participation.uploadError') || "Erreur d'upload"}: ${error}`, 'error')
      }
    }
  })

  // Hook pour upload modéré des vidéos
  const videoUpload = useModeratedUpload({
    accessToken,
    onSuccess: (result) => {
      setVideoUrl(result.url)
      addToast(t('participation.video_added') || 'Vidéo ajoutée', 'success')
    },
    onError: (error, flags) => {
      if (flags && flags.length > 0) {
        addToast(t('moderation.content_rejected') || `⚠️ ${error}`, 'error')
      } else {
        addToast(`${t('participation.uploadError') || "Erreur d'upload"}: ${error}`, 'error')
      }
    }
  })

  const imageInputRef = useRef<HTMLInputElement>(null)
  const videoInputRef = useRef<HTMLInputElement>(null)

  // Handlers pour les uploads
  const handleImageFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    for (const file of files) {
      if (imageUrls.length >= maxImages) break
      await imageUpload.upload(file)
    }
    if (imageInputRef.current) imageInputRef.current.value = ''
  }

  const handleVideoFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (isNomination) {
      addToast(t('participation.video_file_not_allowed') || 'Les fichiers vidéo ne sont pas autorisés pour les nominations. Veuillez utiliser une URL vidéo.', 'error')
      if (videoInputRef.current) videoInputRef.current.value = ''
      return
    }
    await videoUpload.upload(file)
    if (videoInputRef.current) videoInputRef.current.value = ''
  }

  const handleRemoveImage = (index: number) => setImageUrls(imageUrls.filter((_, i) => i !== index))
  const handleRemoveVideo = () => setVideoUrl('')

  const isValidUrl = (url: string) => {
    try { new URL(url); return true } catch { return false }
  }

  const isVideoUrlValid = (url: string) => {
    return isValidVideoUrl(url)
  }

  const handleAddImageByUrl = () => {
    if (!imageUrlInput.trim()) { addToast(t('participation.url_required') || 'URL requise', 'error'); return }
    if (!isValidUrl(imageUrlInput)) { addToast(t('participation.invalid_url') || 'URL invalide', 'error'); return }
    if (imageUrls.length >= maxImages) { addToast(t('participation.max_images_reached') || `Maximum ${maxImages} images`, 'error'); return }
    setImageUrls([...imageUrls, imageUrlInput.trim()])
    setImageUrlInput('')
    setShowImageUrlInput(false)
    addToast(t('participation.image_added') || 'Image ajoutée', 'success')
  }

  const handleAddVideoByUrl = () => {
    if (!videoUrlInput.trim()) { addToast(t('participation.url_required') || 'URL requise', 'error'); return }
    if (!isValidUrl(videoUrlInput)) { addToast(t('participation.invalid_url') || 'URL invalide', 'error'); return }
    // Plateformes vidéo acceptées : YouTube et TikTok (pas de connexion requise pour visionner)
    if (!isVideoUrlValid(videoUrlInput)) { addToast(t('participation.invalid_video_url'), 'error'); return }
    setVideoUrl(cleanVideoUrl(videoUrlInput))
    setVideoUrlInput('')
    setShowVideoUrlInput(false)
    addToast(t('participation.video_added') || 'Vidéo ajoutée', 'success')
  }

  // Extraire le texte brut du HTML pour la validation de longueur
  const getPlainTextLength = (html: string): number => {
    if (!html) return 0
    const text = html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').trim()
    return text.length
  }

  const plainDescriptionLength = getPlainTextLength(description)

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()

    if (!title.trim()) { addToast(t('participation.errors.content_title_required') || 'Le titre est requis', 'error'); return }
    if (title.trim().length < 5) { addToast(t('participation.errors.content_title_min_length') || 'Le titre doit contenir au moins 5 caractères', 'error'); return }
    if (title.trim().length > 100) { addToast(t('participation.errors.content_title_max_length') || 'Le titre ne doit pas dépasser 100 caractères', 'error'); return }
    if (plainDescriptionLength < 20) { addToast(t('participation.errors.content_description_min_length') || 'La description doit contenir au moins 20 caractères', 'error'); return }
    if (plainDescriptionLength > 500) { addToast(t('participation.errors.content_description_max_length') || 'La description ne doit pas dépasser 500 caractères', 'error'); return }
    if (!isNomination && imageUrls.length === 0) { addToast(t('participation.errors.content_image_required') || 'Au moins une image est requise', 'error'); return }
    if (requiresVideo && !videoUrl) { addToast(t('participation.errors.content_video_required') || 'Une vidéo est requise', 'error'); return }
    if (isNomination && !nominatorCountry) { addToast(t('participation.errors.nominator_country_required') || 'Le pays est obligatoire', 'error'); return }

    try {
      setIsSubmitting(true)
      if (onSubmit) {
        await onSubmit(title, description, JSON.stringify(imageUrls), videoUrl ? JSON.stringify([videoUrl]) : undefined, isNomination ? nominatorCity : undefined, isNomination ? nominatorCountry : undefined)
      }
    } catch (err: any) {
      console.error('Erreur lors de la soumission:', err)
      const errorDetail = err?.response?.data?.detail || err?.message || 'Erreur lors de la soumission'
      addToast(errorDetail, 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Validation par étape
  const hasTitleError = title.trim().length > 0 && (title.trim().length < 5 || title.trim().length > 100)
  const hasDescriptionError = plainDescriptionLength > 0 && (plainDescriptionLength < 20 || plainDescriptionLength > 500)
  const hasImageError = !isNomination && imageUrls.length === 0
  const hasVideoError = requiresVideo && !videoUrl
  const hasNominatorCountryError = isNomination && !nominatorCountry

  const isStep1Valid = title.trim().length >= 5 && title.trim().length <= 100 && plainDescriptionLength >= 20 && plainDescriptionLength <= 500
  const isStep2Valid = isNomination
    ? (!!nominatorCountry && (requiresVideo ? !!videoUrl : true))
    : (imageUrls.length >= minImages && (requiresVideo ? !!videoUrl : true))

  const stepLabels = [
    t('participation.step_info') || 'Information',
    t('participation.step_media') || 'Media',
    t('participation.step_review') || 'Review'
  ]

  const canGoNext = () => {
    if (currentStep === 0) return isStep1Valid
    if (currentStep === 1) return isStep2Valid
    return true
  }

  const goNext = () => {
    if (canGoNext() && currentStep < totalSteps - 1) setCurrentStep(currentStep + 1)
  }
  const goPrev = () => {
    if (currentStep > 0) setCurrentStep(currentStep - 1)
  }

  // Detected video platform display
  const detectedPlatform = videoUrl ? detectVideoPlatform(videoUrl) : null
  const platformLabel: Record<string, string> = {
    youtube: 'YouTube',
    tiktok: 'TikTok',

    vimeo: 'Vimeo',
    direct: 'Vidéo directe'
  }

  return (
    <form onSubmit={(e) => e.preventDefault()} className="space-y-4 sm:space-y-6">
      {/* Theme-aware styles for react-quill */}
      <style jsx global>{`
        .ql-toolbar.ql-snow { border-color: rgb(229, 231, 235) !important; border-radius: 0.5rem 0.5rem 0 0; }
        .ql-container.ql-snow { border-color: rgb(229, 231, 235) !important; border-radius: 0 0 0.5rem 0.5rem; min-height: 100px; }
        @media (min-width: 640px) { .ql-container.ql-snow { min-height: 120px; } }
        .ql-editor { min-height: 100px; font-size: 14px; }
        @media (min-width: 640px) { .ql-editor { min-height: 120px; } }
        .ql-editor.ql-blank::before { font-style: normal !important; }
        .dark .ql-toolbar.ql-snow { background: rgb(55, 65, 81); border-color: rgb(75, 85, 99) !important; }
        .dark .ql-toolbar.ql-snow .ql-stroke { stroke: rgb(209, 213, 219) !important; }
        .dark .ql-toolbar.ql-snow .ql-fill { fill: rgb(209, 213, 219) !important; }
        .dark .ql-toolbar.ql-snow .ql-picker-label { color: rgb(209, 213, 219) !important; }
        .dark .ql-toolbar.ql-snow .ql-picker-options { background: rgb(55, 65, 81) !important; border-color: rgb(75, 85, 99) !important; }
        .dark .ql-toolbar.ql-snow .ql-picker-item { color: rgb(209, 213, 219) !important; }
        .dark .ql-container.ql-snow { border-color: rgb(75, 85, 99) !important; background: rgb(55, 65, 81); color: white; }
        .dark .ql-editor.ql-blank::before { color: rgb(156, 163, 175) !important; }
        .dark .ql-snow .ql-picker.ql-expanded .ql-picker-label { border-color: rgb(75, 85, 99) !important; }
      `}</style>

      {/* Countdown - Temps de participation restant */}
      {countdown && !countdown.isClosed && (
        <div className="p-3 sm:p-4 bg-gradient-to-r from-blue-100 dark:from-blue-900/40 to-purple-100 dark:to-purple-900/40 border border-blue-200 dark:border-blue-700/50 rounded-xl">
          <div className="flex items-center gap-2 mb-2 sm:mb-3">
            <Clock className="w-5 h-5 text-blue-400" />
            <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
              {t('participation.time_remaining') || 'Temps de participation restant'}
            </span>
          </div>
          <div className="flex items-center justify-center gap-2 sm:gap-3">
            {countdown.days > 0 && (
              <div className="text-center">
                <div className="px-3 py-1.5 sm:px-4 sm:py-2 bg-blue-600 rounded-lg font-bold text-lg sm:text-2xl text-white">{countdown.days}</div>
                <span className="text-xs text-gray-400 mt-1">{t('dashboard.contests.time_unit_days') || 'j'}</span>
              </div>
            )}
            <div className="text-center">
              <div className="px-3 py-1.5 sm:px-4 sm:py-2 bg-blue-600 rounded-lg font-bold text-lg sm:text-2xl text-white">{String(countdown.hours).padStart(2, '0')}</div>
              <span className="text-xs text-gray-400 mt-1">{t('dashboard.contests.time_unit_hours') || 'h'}</span>
            </div>
            <span className="text-lg sm:text-2xl text-gray-500 font-bold">:</span>
            <div className="text-center">
              <div className="px-3 py-1.5 sm:px-4 sm:py-2 bg-blue-600 rounded-lg font-bold text-lg sm:text-2xl text-white">{String(countdown.minutes).padStart(2, '0')}</div>
              <span className="text-xs text-gray-400 mt-1">{t('dashboard.contests.time_unit_minutes') || 'm'}</span>
            </div>
            <span className="text-lg sm:text-2xl text-gray-500 font-bold">:</span>
            <div className="text-center">
              <div className="px-3 py-1.5 sm:px-4 sm:py-2 bg-purple-600 rounded-lg font-bold text-lg sm:text-2xl text-white animate-pulse">{String(countdown.seconds).padStart(2, '0')}</div>
              <span className="text-xs text-gray-400 mt-1">{t('dashboard.contests.time_unit_seconds') || 's'}</span>
            </div>
          </div>
          {roundData?.submission_end_date && (
            <p className="text-xs text-gray-500 dark:text-gray-400 text-center mt-2">
              {t('participation.deadline') || 'Date limite'} : {new Date(roundData.submission_end_date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}
            </p>
          )}
        </div>
      )}

      {countdown?.isClosed && (
        <div className="p-3 sm:p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700/50 rounded-xl text-center">
          <span className="text-red-400 font-bold text-lg">{t('dashboard.contests.closed') || 'Fermé'}</span>
          <p className="text-red-300/70 text-sm mt-1">{t('participation.submission_period_ended') || 'La période de soumission est terminée'}</p>
        </div>
      )}

      {/* Stepper Header */}
      <div className="flex items-center justify-between px-0 sm:px-2">
        {stepLabels.map((label, index) => (
          <React.Fragment key={index}>
            <div className="flex flex-col items-center gap-1">
              <button
                type="button"
                onClick={() => {
                  if (index < currentStep) setCurrentStep(index)
                  else if (index === currentStep + 1 && canGoNext()) setCurrentStep(index)
                }}
                className={`w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center font-bold text-xs sm:text-sm transition-all ${
                  index < currentStep
                    ? 'bg-green-600 text-white cursor-pointer hover:bg-green-500'
                    : index === currentStep
                      ? 'bg-blue-600 text-white ring-2 ring-blue-400/50'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-400'
                }`}
              >
                {index < currentStep ? <Check className="w-5 h-5" /> : index + 1}
              </button>
              <span className={`text-[10px] sm:text-xs font-medium ${index === currentStep ? 'text-blue-400' : index < currentStep ? 'text-green-400' : 'text-gray-400 dark:text-gray-500'}`}>
                {label}
              </span>
            </div>
            {index < stepLabels.length - 1 && (
              <div className={`flex-1 h-0.5 mx-1 sm:mx-2 mt-[-16px] sm:mt-[-20px] ${index < currentStep ? 'bg-green-600' : 'bg-gray-200 dark:bg-gray-700'}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* ===== STEP 1: Informations (Titre + Description WYSIWYG) ===== */}
      {currentStep === 0 && (
        <div className="space-y-4 sm:space-y-5 animate-in fade-in duration-300">
          {/* Title */}
          <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 sm:p-5 border border-gray-200 dark:border-gray-700/50">
            <h3 className="text-sm sm:text-base font-bold text-gray-900 dark:text-white mb-2 sm:mb-3">
              {t('participation.content_title') || 'Titre du contenu'} *
            </h3>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('participation.content_title_placeholder') || 'Entrez le titre (5-100 caractères)'}
              maxLength={100}
              className={`w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-400 focus:outline-none focus:ring-2 ${
                hasTitleError ? 'border-red-500 focus:ring-red-500' : 'border-gray-300 dark:border-gray-600 focus:ring-blue-500'
              }`}
              disabled={isSubmitting}
            />
            <div className="flex items-center justify-between mt-2">
              <p className={`text-xs ${hasTitleError ? 'text-red-500 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}`}>
                {title.length}/100 {title.length < 5 && title.length > 0 ? `(min. 5)` : ''}
              </p>
              {title.trim().length >= 5 && title.trim().length <= 100 && (
                <CheckCircle className="w-4 h-4 text-green-500" />
              )}
            </div>
          </div>

          {/* Description WYSIWYG */}
          <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 sm:p-5 border border-gray-200 dark:border-gray-700/50">
            <h3 className="text-sm sm:text-base font-bold text-gray-900 dark:text-white mb-2 sm:mb-3 flex items-center gap-2">
              <FileText className="w-4 h-4" />
              {t('participation.content_description') || 'Description du contenu'} *
            </h3>
            <ReactQuill
                theme="snow"
                value={description}
                onChange={setDescription}
                modules={QUILL_MODULES}
                formats={QUILL_FORMATS}
                placeholder={t('participation.content_description_placeholder') || 'Décrivez votre candidature (20-500 caractères)'}
                readOnly={isSubmitting}
              />
            <div className="flex items-center justify-between mt-2">
              <p className={`text-xs ${hasDescriptionError ? 'text-red-500 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}`}>
                {plainDescriptionLength}/500 {plainDescriptionLength < 20 && plainDescriptionLength > 0 ? `(min. 20)` : ''}
              </p>
              {plainDescriptionLength >= 20 && plainDescriptionLength <= 500 && (
                <CheckCircle className="w-4 h-4 text-green-500" />
              )}
            </div>
          </div>
        </div>
      )}

      {/* ===== STEP 2: Médias (Location + Images + Vidéo) ===== */}
      {currentStep === 1 && (
        <div className="space-y-4 sm:space-y-5 animate-in fade-in duration-300">
          {/* Nominator Location (nominations only) */}
          {isNomination && (
            <div className={`bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 sm:p-5 border ${hasNominatorCountryError ? 'border-red-500' : 'border-gray-200 dark:border-gray-700/50'}`}>
              <h3 className="text-base font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <Globe className="w-4 h-4" />
                {t('participation.nominator_location') || 'Localisation du candidat'}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                {t('participation.nominator_location_description') || 'Indiquez la localisation de la personne que vous nominez.'}
              </p>
              <div className="mb-3 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800/50 rounded-lg">
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  <strong>Note :</strong> {t('participation.nominator_country_note') || 'Le pays doit correspondre à votre pays de profil.'}
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {t('participation.nominator_country') || 'Pays'} *
                  </label>
                  <select
                    value={nominatorCountry}
                    onChange={(e) => { setNominatorCountry(e.target.value); setNominatorCity('') }}
                    className={`w-full px-4 py-2 border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 ${
                      hasNominatorCountryError ? 'border-red-500 focus:ring-red-500' : 'border-gray-300 dark:border-gray-600 focus:ring-blue-500'
                    }`}
                    disabled={isSubmitting}
                  >
                    <option value="">{t('participation.select_country') || 'Sélectionnez un pays'}</option>
                    {countries.map((country) => (
                      <option key={country.code} value={country.name}>{country.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    <MapPin className="w-4 h-4 inline mr-1" />
                    {t('participation.nominator_city') || 'Ville'} ({t('common.optional') || 'optionnel'})
                  </label>
                  {nominatorCountry ? (
                    <select
                      value={nominatorCity}
                      onChange={(e) => setNominatorCity(e.target.value)}
                      className="w-full px-4 py-2 border rounded-lg bg-white text-gray-900 border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white dark:border-gray-600"
                      disabled={isSubmitting || loadingCities}
                    >
                      <option value="">{loadingCities ? (t('common.loading') || 'Chargement...') : (t('participation.select_city') || 'Sélectionnez une ville')}</option>
                      {availableCities.map((city) => (
                        <option key={city} value={city}>{city}</option>
                      ))}
                    </select>
                  ) : (
                    <input type="text" disabled placeholder={t('participation.select_country_first') || "Sélectionnez d'abord un pays"}
                      className="w-full px-4 py-2 border rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-500 cursor-not-allowed border-gray-300 dark:border-gray-600" />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Content Images (hidden for nominations) */}
          {!isNomination && (
            <div className={`bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 sm:p-5 border ${hasImageError ? 'border-red-500' : 'border-gray-200 dark:border-gray-700/50'}`}>
              <h3 className="text-sm sm:text-base font-bold text-gray-900 dark:text-white mb-2 sm:mb-3 flex items-center gap-2">
                <ImageIcon className="w-4 h-4" />
                {t('participation.content_image') || 'Images'} {minImages > 0 && '*'} ({imageUrls.length}/{maxImages})
              </h3>

              {imageUrls.length < maxImages && (
                <div className="space-y-3 mb-4">
                  <div
                    className="p-4 sm:p-5 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/30 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition cursor-pointer"
                    onClick={() => !imageUpload.isUploading && !isSubmitting && imageInputRef.current?.click()}
                  >
                    <input ref={imageInputRef} type="file" accept="image/*" multiple onChange={handleImageFileSelect} className="hidden" disabled={isSubmitting || imageUpload.isUploading || imageUrls.length >= maxImages} />
                    <div className="flex flex-col items-center text-center">
                      {imageUpload.isUploading ? (
                        <>
                          <Loader2 className="w-8 h-8 text-gray-400 mb-2 animate-spin" />
                          <p className="text-sm text-gray-600 dark:text-gray-300">{t('moderation.analyzing') || 'Upload...'} ({Math.round(imageUpload.progress)}%)</p>
                        </>
                      ) : (
                        <>
                          <Upload className="w-7 h-7 text-gray-400 mb-2" />
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('dashboard.contests.participation_form.click_add_images') || 'Cliquez pour ajouter des images'}</p>
                          <p className="text-xs text-gray-500 mt-1">JPG, PNG, GIF, WebP</p>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-400 dark:text-gray-500">{t('participation.or') || 'ou'}</span>
                    <Button type="button" variant="outline" size="sm" onClick={() => setShowImageUrlInput(!showImageUrlInput)} className="gap-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">
                      <Link className="w-4 h-4" /> {t('participation.add_by_url') || 'Ajouter par URL'}
                    </Button>
                  </div>
                  {showImageUrlInput && (
                    <div className="flex flex-col sm:flex-row gap-2">
                      <Input type="url" value={imageUrlInput} onChange={(e) => setImageUrlInput(e.target.value)} placeholder="https://exemple.com/image.jpg" className="flex-1 bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white" />
                      <Button type="button" onClick={handleAddImageByUrl} className="gap-1 w-full sm:w-auto"><Plus className="w-4 h-4" /> {t('participation.add') || 'Ajouter'}</Button>
                    </div>
                  )}
                </div>
              )}

              {imageUrls.length > 0 && (
                <div className="grid grid-cols-2 gap-2 sm:gap-3">
                  {imageUrls.map((url, index) => (
                    <div key={index} className="relative group">
                      <img src={url} alt={`Image ${index + 1}`} className="w-full h-24 sm:h-32 object-cover rounded-lg border border-gray-200 dark:border-gray-600 cursor-pointer hover:opacity-75 transition" onClick={() => { setPreviewImageUrl(url); setShowImagePreview(true) }} />
                      <div className="absolute inset-0 flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100 transition">
                        <button type="button" onClick={(e) => { e.stopPropagation(); setPreviewImageUrl(url); setShowImagePreview(true) }} className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-lg"><Eye className="w-4 h-4" /></button>
                        <button type="button" onClick={() => handleRemoveImage(index)} className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-lg" disabled={isSubmitting}><X className="w-4 h-4" /></button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Content Video */}
          <div className={`bg-gray-800/50 rounded-xl p-4 sm:p-5 border ${hasVideoError ? 'border-red-500' : 'border-gray-700/50'}`}>
            <h3 className="text-sm sm:text-base font-bold text-gray-900 dark:text-white mb-2 sm:mb-3 flex items-center gap-2">
              <Video className="w-4 h-4" />
              {requiresVideo
                ? (t('participation.content_video_required') || 'Vidéo *')
                : (t('participation.content_video_optional') || 'Vidéo (optionnel)')}
            </h3>

            {/* Plateformes supportées */}
            <div className="mb-3 sm:mb-4 p-2.5 sm:p-3 bg-gray-50 dark:bg-gray-700/30 border border-gray-200 dark:border-gray-600/50 rounded-lg">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('participation.supported_platforms') || 'Plateformes supportées'} :</p>
              <div className="flex flex-wrap gap-1.5">
                {VIDEO_PLATFORMS.map((p) => (
                  <a
                    key={p.name}
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`text-xs px-2.5 py-1 rounded-full border font-medium cursor-pointer hover:opacity-80 transition-opacity ${p.bg}`}
                  >
                    {p.name}
                  </a>
                ))}
              </div>
            </div>

            {!videoUrl && (
              <div className="space-y-3">
                {!isNomination && (
                  <div className="p-4 sm:p-5 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/30 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition cursor-pointer"
                    onClick={() => !videoUpload.isUploading && !isSubmitting && videoInputRef.current?.click()}>
                    <input ref={videoInputRef} type="file" accept="video/*" onChange={handleVideoFileSelect} className="hidden" disabled={isSubmitting || videoUpload.isUploading} />
                    <div className="flex flex-col items-center text-center">
                      {videoUpload.isUploading ? (
                        <>
                          <Loader2 className="w-8 h-8 text-gray-400 mb-2 animate-spin" />
                          <p className="text-sm text-gray-600 dark:text-gray-300">{t('moderation.analyzing') || 'Upload...'} ({Math.round(videoUpload.progress)}%)</p>
                        </>
                      ) : (
                        <>
                          <Video className="w-7 h-7 text-gray-400 mb-2" />
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('dashboard.contests.participation_form.click_add_video') || 'Cliquez pour ajouter une vidéo'}</p>
                          <p className="text-xs text-gray-500 mt-1">MP4, WebM, MOV</p>
                        </>
                      )}
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-2">
                  {!isNomination && <span className="text-sm text-gray-400 dark:text-gray-500">{t('participation.or') || 'ou'}</span>}
                  <Button type="button" variant="outline" size="sm" onClick={() => setShowVideoUrlInput(!showVideoUrlInput)} className="gap-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">
                    <Link className="w-4 h-4" /> {t('participation.add_video_by_url') || 'Ajouter par URL'}
                  </Button>
                </div>

                {showVideoUrlInput && (
                  <div className="space-y-2">
                    <div className="flex flex-col sm:flex-row gap-2">
                      <Input type="url" value={videoUrlInput} onChange={(e) => setVideoUrlInput(e.target.value)}
                        placeholder="https://youtube.com/shorts/... ou https://tiktok.com/..."
                        className="flex-1 bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white" />
                      <Button type="button" onClick={handleAddVideoByUrl} className="gap-1 w-full sm:w-auto"><Plus className="w-4 h-4" /> {t('participation.add') || 'Ajouter'}</Button>
                    </div>
                    {videoUrlInput && isValidUrl(videoUrlInput) && (
                      <div className="flex items-center gap-2 text-xs">
                        {isVideoUrlValid(videoUrlInput) ? (
                          <span className="text-green-400 flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" />
                            {platformLabel[detectVideoPlatform(videoUrlInput)] || 'Lien reconnu'}
                          </span>
                        ) : (
                          <span className="text-red-400 flex items-center gap-1">
                            <AlertCircle className="w-3 h-3" />
                            {t('participation.unrecognized_video_link') || 'Lien vidéo non reconnu'}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {videoUrl && (
              <div className="relative group">
                <div className="w-full aspect-video rounded-lg border border-gray-200 dark:border-gray-600 bg-black overflow-hidden">
                  <VideoEmbed url={videoUrl} className="w-full h-full" allowFullscreen={true} />
                </div>
                {detectedPlatform && detectedPlatform !== 'unknown' && (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded-full">
                      {platformLabel[detectedPlatform] || detectedPlatform}
                    </span>
                  </div>
                )}
                <div className="absolute top-2 right-2 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition">
                  {detectedPlatform === 'direct' && (
                    <button type="button" onClick={(e) => { e.stopPropagation(); setPreviewVideoUrl(videoUrl); setShowVideoPreview(true) }} className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-lg"><Eye className="w-4 h-4" /></button>
                  )}
                  <button type="button" onClick={handleRemoveVideo} className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-lg" disabled={isSubmitting}><X className="w-4 h-4" /></button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===== STEP 3: Vérification (Review) ===== */}
      {currentStep === 2 && (
        <div className="space-y-4 sm:space-y-5 animate-in fade-in duration-300">
          <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 sm:p-5 border border-gray-200 dark:border-gray-700/50">
            <h3 className="text-sm sm:text-base font-bold text-gray-900 dark:text-white mb-3 sm:mb-4">{t('participation.review_title') || 'Vérifiez votre candidature'}</h3>

            {/* Title review */}
            <div className="space-y-4">
              <div className="flex items-start gap-2 sm:gap-3 p-2.5 sm:p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 text-green-500 mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">{t('participation.content_title') || 'Titre'}</p>
                  <p className="text-gray-900 dark:text-white font-medium truncate">{title}</p>
                </div>
                <button type="button" onClick={() => setCurrentStep(0)} className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300">{t('common.edit') || 'Modifier'}</button>
              </div>

              {/* Description review */}
              <div className="flex items-start gap-2 sm:gap-3 p-2.5 sm:p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 text-green-500 mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">{t('participation.content_description') || 'Description'}</p>
                  <div className="text-white text-sm prose dark:prose-invert prose-sm max-w-none [&>*]:m-0" dangerouslySetInnerHTML={{ __html: description }} />
                </div>
                <button type="button" onClick={() => setCurrentStep(0)} className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300">{t('common.edit') || 'Modifier'}</button>
              </div>

              {/* Location review (nominations) */}
              {isNomination && nominatorCountry && (
                <div className="flex items-start gap-2 sm:gap-3 p-2.5 sm:p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                  <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 text-green-500 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">{t('participation.nominator_location') || 'Localisation'}</p>
                    <p className="text-gray-900 dark:text-white">{nominatorCity ? `${nominatorCity}, ` : ''}{nominatorCountry}</p>
                  </div>
                  <button type="button" onClick={() => setCurrentStep(1)} className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300">{t('common.edit') || 'Modifier'}</button>
                </div>
              )}

              {/* Images review */}
              {!isNomination && imageUrls.length > 0 && (
                <div className="flex items-start gap-2 sm:gap-3 p-2.5 sm:p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                  <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 text-green-500 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">{t('participation.content_image') || 'Images'} ({imageUrls.length})</p>
                    <div className="flex gap-2 mt-2 overflow-x-auto">
                      {imageUrls.map((url, i) => (
                        <img key={i} src={url} alt={`${i + 1}`} className="w-12 h-12 sm:w-16 sm:h-16 object-cover rounded border border-gray-600 flex-shrink-0" />
                      ))}
                    </div>
                  </div>
                  <button type="button" onClick={() => setCurrentStep(1)} className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300">{t('common.edit') || 'Modifier'}</button>
                </div>
              )}

              {/* Video review */}
              {videoUrl && (
                <div className="flex items-start gap-2 sm:gap-3 p-2.5 sm:p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                  <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 text-green-500 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">{t('participation.content_video') || 'Vidéo'}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <Video className="w-4 h-4 text-gray-400" />
                      <span className="text-gray-900 dark:text-white text-sm truncate">{videoUrl}</span>
                      {detectedPlatform && <span className="text-xs text-gray-400 px-2 py-0.5 bg-gray-700 rounded-full">{platformLabel[detectedPlatform] || ''}</span>}
                    </div>
                  </div>
                  <button type="button" onClick={() => setCurrentStep(1)} className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300">{t('common.edit') || 'Modifier'}</button>
                </div>
              )}
            </div>
          </div>

          {/* Ad Revenue Warning */}
          <div className="p-3 sm:p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 rounded-xl">
            <div className="flex gap-3">
              <AlertCircle className="w-5 h-5 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-amber-700 dark:text-amber-300">
                {t('participation.ad_revenue_warning') || 'Avertissement : Vous ne serez pas rémunéré pour les revenus publicitaires si nous détectons que le contenu ne provient pas de votre pays.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Buttons */}
      <div className="flex gap-2 sm:gap-3 pt-2">
        {currentStep === 0 ? (
          <Button type="button" onClick={() => onCancel ? onCancel() : router.back()} variant="outline" className="flex-1 h-11 sm:h-10 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700" disabled={isSubmitting}>
            {t('dashboard.contests.participation_form.cancel') || 'Annuler'}
          </Button>
        ) : (
          <Button type="button" onClick={goPrev} variant="outline" className="flex-1 h-11 sm:h-10 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 gap-2" disabled={isSubmitting}>
            <ChevronLeft className="w-4 h-4" /> {t('common.previous') || 'Précédent'}
          </Button>
        )}

        {currentStep < totalSteps - 1 ? (
          <Button type="button" onClick={goNext} disabled={!canGoNext() || isSubmitting} className="flex-1 h-11 sm:h-10 bg-blue-600 hover:bg-blue-700 text-white font-bold gap-2">
            {t('common.next') || 'Suivant'} <ChevronRight className="w-4 h-4" />
          </Button>
        ) : (
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={!isStep1Valid || !isStep2Valid || isSubmitting}
            className="flex-1 h-11 sm:h-10 bg-green-600 hover:bg-green-700 text-white font-bold gap-2"
          >
            {isSubmitting
              ? <><Loader2 className="w-4 h-4 animate-spin" /> {t('common.submitting') || 'Envoi...'}</>
              : isEditing
                ? (t('dashboard.contests.participation_form.edit_participation') || 'Modifier ma candidature')
                : <><Check className="w-4 h-4" /> {t('participation.submit') || 'Soumettre'}</>
            }
          </Button>
        )}
      </div>

      {/* Dialogs */}
      <ImagePreviewDialog isOpen={showImagePreview} imageUrl={previewImageUrl} imageAlt="Image preview" onClose={() => setShowImagePreview(false)} />
      <VideoPreviewDialog isOpen={showVideoPreview} videoUrl={previewVideoUrl} videoTitle="Video preview" onClose={() => setShowVideoPreview(false)} />
    </form>
  )
}
