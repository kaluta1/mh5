'use client'

import React, { useState, useEffect, useRef } from 'react'
import { X, Upload, FileText, Image as ImageIcon, Video, Eye, Link, Plus, AlertCircle, CheckCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ImagePreviewDialog } from '@/components/ui/image-preview-dialog'
import { VideoPreviewDialog } from '@/components/ui/video-preview-dialog'
import { VideoEmbed } from '@/components/ui/video-embed'
import { useLanguage } from '@/contexts/language-context'
import { useRouter } from 'next/navigation'
import { useModeratedUpload } from '@/hooks/use-moderated-upload'
import { useToast } from '@/components/ui/toast'
import { isValidVideoUrl, detectVideoPlatform, isYouTubeShort } from '@/lib/utils/video-platforms'

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
    videoMediaIds?: string
  ) => Promise<void>
  onCancel?: () => void
  isSubmitting?: boolean
  isEditing?: boolean
  initialData?: {
    title?: string
    description?: string
    imageUrls?: string[]
    videoUrl?: string
  }
  mediaRequirements?: MediaRequirements
  isNomination?: boolean
}

export function ParticipationForm({ contestId, onSubmit, onCancel, isSubmitting: externalIsSubmitting, isEditing = false, initialData, mediaRequirements, isNomination = false }: ParticipationFormProps) {
  const { t } = useLanguage()
  const router = useRouter()
  const { addToast } = useToast()
  
  const [title, setTitle] = useState<string>(initialData?.title || '')
  const [description, setDescription] = useState<string>(initialData?.description || '')
  const [imageUrls, setImageUrls] = useState<string[]>(initialData?.imageUrls || [])
  const [videoUrl, setVideoUrl] = useState<string>(initialData?.videoUrl || '')
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
  
  // Media requirements with defaults
  // Pour les nominations : images optionnelles (minImages = 0), vidéos obligatoires
  const minImages = isNomination ? 0 : (mediaRequirements?.minImages ?? 1)
  const maxImages = mediaRequirements?.maxImages ?? 10
  const requiresVideo = isNomination ? true : (mediaRequirements?.requiresVideo ?? false)
  const maxVideos = mediaRequirements?.maxVideos ?? 1

  // Récupérer le token depuis localStorage
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (token) {
      setAccessToken(token)
    }
  }, [])

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

  // Référence pour les inputs fichier
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
    
    if (imageInputRef.current) {
      imageInputRef.current.value = ''
    }
  }

  const handleVideoFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    // Pour les nominations : les fichiers vidéo ne sont pas autorisés, seulement les URLs
    if (isNomination) {
      addToast(t('participation.video_file_not_allowed') || 'Les fichiers vidéo ne sont pas autorisés pour les nominations. Veuillez utiliser une URL YouTube (y compris YouTube Shorts), TikTok, ou un autre lien vidéo.', 'error')
      if (videoInputRef.current) {
        videoInputRef.current.value = ''
      }
      return
    }
    
    await videoUpload.upload(file)
    
    if (videoInputRef.current) {
      videoInputRef.current.value = ''
    }
  }

  const handleRemoveImage = (index: number) => {
    setImageUrls(imageUrls.filter((_, i) => i !== index))
  }

  const handleRemoveVideo = () => {
    setVideoUrl('')
  }

  // URL validation
  const isValidUrl = (url: string) => {
    try {
      new URL(url)
      return true
    } catch {
      return false
    }
  }

  const isImageUrl = (url: string) => {
    const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg']
    const lowerUrl = url.toLowerCase()
    return imageExtensions.some(ext => lowerUrl.includes(ext)) || lowerUrl.includes('image')
  }

  const isVideoUrl = (url: string) => {
    // Vérifier si c'est une URL de plateforme vidéo supportée
    if (isValidVideoUrl(url)) {
      return true
    }
    // Vérifier si c'est une extension de fichier vidéo
    const videoExtensions = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v']
    const lowerUrl = url.toLowerCase()
    return videoExtensions.some(ext => lowerUrl.includes(ext)) || lowerUrl.includes('video')
  }

  const handleAddImageByUrl = () => {
    if (!imageUrlInput.trim()) {
      addToast(t('participation.url_required') || 'URL requise', 'error')
      return
    }
    if (!isValidUrl(imageUrlInput)) {
      addToast(t('participation.invalid_url') || 'URL invalide', 'error')
      return
    }
    if (imageUrls.length >= maxImages) {
      addToast(t('participation.max_images_reached') || `Maximum ${maxImages} images`, 'error')
      return
    }
    setImageUrls([...imageUrls, imageUrlInput.trim()])
    setImageUrlInput('')
    setShowImageUrlInput(false)
    addToast(t('participation.image_added') || 'Image ajoutée', 'success')
  }

  const handleAddVideoByUrl = () => {
    if (!videoUrlInput.trim()) {
      addToast(t('participation.url_required') || 'URL requise', 'error')
      return
    }
    if (!isValidUrl(videoUrlInput)) {
      addToast(t('participation.invalid_url') || 'URL invalide', 'error')
      return
    }
    
    // Vérifier si c'est un YouTube Short (interdit)
    if (isYouTubeShort(videoUrlInput)) {
      addToast(t('participation.youtube_shorts_not_allowed') || 'Les YouTube Shorts ne sont pas autorisés. Veuillez utiliser une vidéo YouTube standard.', 'error')
      return
    }
    
    // Pour les nominations : valider que ce n'est pas Facebook ou Vimeo
    if (isNomination) {
      const platform = detectVideoPlatform(videoUrlInput)
      if (platform === 'facebook') {
        addToast(t('participation.video_platform_not_allowed'), 'error')
        return
      }
      if (platform === 'vimeo') {
        addToast(t('participation.video_platform_not_allowed'), 'error')
        return
      }
    }
    
    if (!isVideoUrl(videoUrlInput)) {
      addToast(t('participation.invalid_video_url'), 'error')
      return
    }
    setVideoUrl(videoUrlInput.trim())
    setVideoUrlInput('')
    setShowVideoUrlInput(false)
    addToast(t('participation.video_added') || 'Vidéo ajoutée', 'success')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!title.trim()) {
      addToast(t('participation.errors.content_title_required') || 'Le titre du contenu est requis', 'error')
      return
    }

    if (title.trim().length < 10) {
      addToast(t('participation.errors.content_title_min_length') || 'Le titre du contenu doit contenir au moins 10 caractères', 'error')
      return
    }

    if (!description.trim()) {
      addToast(t('participation.errors.content_description_required') || 'La description du contenu est requise', 'error')
      return
    }

    if (description.trim().length < 100) {
      addToast(t('participation.errors.content_description_min_length') || 'La description du contenu doit contenir au moins 100 caractères', 'error')
      return
    }

    // Pour les nominations, les images sont optionnelles
    if (!isNomination && imageUrls.length === 0) {
      addToast(t('participation.errors.content_image_required') || 'Au moins une image est requise', 'error')
      return
    }

    if (requiresVideo && !videoUrl) {
      addToast(t('participation.errors.content_video_required') || 'Une vidéo est requise pour ce concours', 'error')
      return
    }

    try {
      setIsSubmitting(true)

      if (onSubmit) {
        await onSubmit(
          title,
          description,
          JSON.stringify(imageUrls),
          videoUrl ? JSON.stringify([videoUrl]) : undefined
        )
      }
    } catch (err: any) {
      console.error('Erreur lors de la soumission:', err)
      addToast(err?.message || 'Erreur lors de la soumission', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Calculate errors
  const hasTitleError = title.trim().length > 0 && title.trim().length < 10
  const hasDescriptionError = description.trim().length > 0 && description.trim().length < 100
  // Pour les nominations, les images sont optionnelles
  const hasImageError = !isNomination && imageUrls.length === 0
  const hasVideoError = requiresVideo && !videoUrl

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Section 1: Content Title */}
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
          {t('participation.content_title') || 'Content Title'} *
        </h3>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t('participation.content_title_placeholder') || 'Enter content title (minimum 10 characters)'}
          maxLength={200}
          className={`w-full px-4 py-2 border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 ${
            (!title.trim() || (title.length > 0 && title.length < 10))
              ? 'border-red-500 focus:ring-red-500' 
              : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary'
          }`}
          disabled={isSubmitting}
        />
        <div className="flex items-center justify-between mt-2">
          <p className={`text-xs ${title.length > 0 && title.length < 10 ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'}`}>
            {title.length < 10 
              ? `${t('participation.min_characters') || 'Minimum'} 10 ${t('participation.characters') || 'characters'} (${title.length}/10)`
              : `${title.length}/200`
            }
          </p>
        </div>
        {/* Error message for title */}
        {(!title.trim() || hasTitleError) && (
          <div className="mt-2 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>
              {!title.trim() 
                ? t('participation.errors.content_title_required') || 'Content Title is required'
                : t('participation.errors.content_title_min_length') || 'Content title must contain at least 10 characters'
              }
            </span>
          </div>
        )}
      </div>

      {/* Section 2: Content Description */}
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <FileText className="w-5 h-5" />
          {t('participation.content_description') || 'Content Description'} *
        </h3>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t('participation.content_description_placeholder') || 'Enter content description (minimum 100 characters)'}
          maxLength={1000}
          rows={4}
          className={`w-full px-4 py-2 border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 resize-none ${
            (!description.trim() || (description.length > 0 && description.length < 100))
              ? 'border-red-500 focus:ring-red-500' 
              : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary'
          }`}
          disabled={isSubmitting}
        />
        <div className="flex items-center justify-between mt-2">
          <p className={`text-xs ${description.length > 0 && description.length < 100 ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'}`}>
            {description.length < 100 
              ? `${t('participation.min_characters') || 'Minimum'} 100 ${t('participation.characters') || 'characters'} (${description.length}/100)`
              : `${description.length}/1000`
            }
          </p>
        </div>
        {/* Error message for description */}
        {(!description.trim() || hasDescriptionError) && (
          <div className="mt-2 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>
              {!description.trim() 
                ? t('participation.errors.content_description_required') || 'Content Description is required'
                : t('participation.errors.content_description_min_length') || 'Content description must contain at least 100 characters'
              }
            </span>
          </div>
        )}
      </div>

      {/* Media Requirements Info */}
      {mediaRequirements && (
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
          <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-200 mb-2 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {t('participation.media_requirements') || 'Exigences média'}
          </h4>
          <ul className="text-sm text-blue-800 dark:text-blue-300 space-y-1">
            {!isNomination && (
            <li className="flex items-center gap-2">
              {imageUrls.length >= minImages ? <CheckCircle className="w-4 h-4 text-green-500" /> : <AlertCircle className="w-4 h-4 text-amber-500" />}
              {t('participation.images_required') || 'Images'}: {minImages} min, {maxImages} max ({imageUrls.length}/{maxImages})
            </li>
            )}
            {requiresVideo && (
              <li className="flex items-center gap-2">
                {videoUrl ? <CheckCircle className="w-4 h-4 text-green-500" /> : <AlertCircle className="w-4 h-4 text-amber-500" />}
                {t('participation.video_required') || 'Vidéo obligatoire'}
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Section 3: Content Images - Masqué pour les nominations */}
      {!isNomination && (
      <div className={`bg-gray-50 dark:bg-gray-800 rounded-lg p-6 border ${
        hasImageError 
          ? 'border-red-500 dark:border-red-500' 
          : 'border-gray-200 dark:border-gray-700'
      }`}>
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <ImageIcon className="w-5 h-5" />
          {t('participation.content_image') || 'Content Image'} {minImages > 0 && '*'} ({imageUrls.length}/{maxImages})
        </h3>
        
        {imageUrls.length < maxImages && (
          <div className="space-y-3 mb-4">
            {/* Upload button avec modération */}
            <div 
              className="p-6 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg bg-white/50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition cursor-pointer"
              onClick={() => !imageUpload.isUploading && !isSubmitting && imageInputRef.current?.click()}
            >
              <input
                ref={imageInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={handleImageFileSelect}
                className="hidden"
                disabled={isSubmitting || imageUpload.isUploading || imageUrls.length >= maxImages}
              />
              
              <div className="flex flex-col items-center justify-center text-center">
                {imageUpload.isUploading ? (
                  <>
                    <Loader2 className="w-8 h-8 text-gray-400 mb-2 animate-spin" />
                    <p className="font-semibold text-gray-700 dark:text-gray-300">
                      {t('moderation.analyzing') || 'Modération et upload...'} ({Math.round(imageUpload.progress)}%)
                    </p>
                  </>
                ) : (
                  <>
                    <Upload className="w-8 h-8 text-gray-400 mb-2" />
                    <p className="font-semibold text-gray-700 dark:text-gray-300">
                      {t('dashboard.contests.participation_form.click_add_images') || 'Cliquez pour ajouter des images'}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                      {t('dashboard.contests.participation_form.images_format') || 'JPG, PNG, GIF, WebP'}
                    </p>
                  </>
                )}
              </div>

              {/* Afficher les erreurs de modération */}
              {imageUpload.error && imageUpload.moderationFlags.length > 0 && (
                <div className="mt-3 p-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-xs">
                  <p className="text-red-700 dark:text-red-300 font-medium flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {t('moderation.content_rejected') || 'Contenu rejeté'}
                  </p>
                  <ul className="list-disc list-inside text-red-600 dark:text-red-400 mt-1">
                    {imageUpload.moderationFlags.map((flag, idx) => (
                      <li key={idx}>{flag.description}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* URL Import Option */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">{t('participation.or') || 'ou'}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowImageUrlInput(!showImageUrlInput)}
                className="gap-2"
              >
                <Link className="w-4 h-4" />
                {t('participation.add_by_url') || 'Ajouter par URL'}
              </Button>
            </div>

            {/* URL Input */}
            {showImageUrlInput && (
              <div className="flex gap-2">
                <Input
                  type="url"
                  value={imageUrlInput}
                  onChange={(e) => setImageUrlInput(e.target.value)}
                  placeholder={t('participation.image_url_placeholder') || 'https://exemple.com/image.jpg'}
                  className="flex-1"
                />
                <Button type="button" onClick={handleAddImageByUrl} className="gap-1">
                  <Plus className="w-4 h-4" />
                  {t('participation.add') || 'Ajouter'}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Uploaded Images List */}
        {imageUrls.length > 0 && (
          <div className="grid grid-cols-2 gap-3">
            {imageUrls.map((url, index) => (
              <div key={index} className="relative group">
                <img
                  src={url}
                  alt={`Image ${index + 1}`}
                  className="w-full h-32 object-cover rounded-lg border border-gray-200 dark:border-gray-600 cursor-pointer hover:opacity-75 transition"
                  onClick={() => {
                    setPreviewImageUrl(url)
                    setShowImagePreview(true)
                  }}
                />
                <div className="absolute inset-0 flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100 transition">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setPreviewImageUrl(url)
                      setShowImagePreview(true)
                    }}
                    className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-lg"
                    title="Prévisualiser"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRemoveImage(index)}
                    className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-lg"
                    disabled={isSubmitting}
                    title="Supprimer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {/* Error message for images */}
        {hasImageError && (
          <div className="mt-4 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>
              {t('participation.errors.content_image_required') || 'Content Image'} - {t('participation.errors.at_least_one_image') || 'At least one image is required'}
            </span>
          </div>
        )}
      </div>
      )}

      {/* Section 4: Content Video */}
      <div className={`bg-gray-50 dark:bg-gray-800 rounded-lg p-6 border ${
        hasVideoError 
          ? 'border-red-500 dark:border-red-500' 
          : 'border-gray-200 dark:border-gray-700'
      }`}>
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Video className="w-5 h-5" />
          {requiresVideo 
            ? (t('participation.content_video_required') || 'Content Video *')
            : (t('participation.content_video_optional') || 'Content Video (optional)')}
        </h3>
        
        {!videoUrl && (
          <div className="space-y-3">
            {/* Upload button avec modération - Masqué pour les nominations */}
            {!isNomination && (
            <div 
              className="p-6 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg bg-white/50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition cursor-pointer"
              onClick={() => !videoUpload.isUploading && !isSubmitting && videoInputRef.current?.click()}
            >
              <input
                ref={videoInputRef}
                type="file"
                accept="video/*"
                onChange={handleVideoFileSelect}
                className="hidden"
                disabled={isSubmitting || videoUpload.isUploading}
              />
              
              <div className="flex flex-col items-center justify-center text-center">
                {videoUpload.isUploading ? (
                  <>
                    <Loader2 className="w-8 h-8 text-gray-400 mb-2 animate-spin" />
                    <p className="font-semibold text-gray-700 dark:text-gray-300">
                      {t('moderation.analyzing') || 'Modération et upload...'} ({Math.round(videoUpload.progress)}%)
                    </p>
                  </>
                ) : (
                  <>
                    <Video className="w-8 h-8 text-gray-400 mb-2" />
                    <p className="font-semibold text-gray-700 dark:text-gray-300">
                      {t('dashboard.contests.participation_form.click_add_video') || 'Cliquez pour ajouter une vidéo'}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                      {t('dashboard.contests.participation_form.video_format') || 'MP4, WebM, MOV, YouTube, Vimeo, TikTok, Facebook'}
                    </p>
                  </>
                )}
              </div>

              {/* Afficher les erreurs de modération */}
              {videoUpload.error && videoUpload.moderationFlags.length > 0 && (
                <div className="mt-3 p-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-xs">
                  <p className="text-red-700 dark:text-red-300 font-medium flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {t('moderation.content_rejected') || 'Contenu rejeté'}
                  </p>
                  <ul className="list-disc list-inside text-red-600 dark:text-red-400 mt-1">
                    {videoUpload.moderationFlags.map((flag, idx) => (
                      <li key={idx}>{flag.description}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            )}

            {/* URL Import Option */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">{t('participation.or') || 'ou'}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowVideoUrlInput(!showVideoUrlInput)}
                className="gap-2"
              >
                <Link className="w-4 h-4" />
                {t('participation.add_video_by_url') || 'Ajouter par URL'}
              </Button>
            </div>

            {/* URL Input */}
            {showVideoUrlInput && (
              <div className="flex gap-2">
                <Input
                  type="url"
                  value={videoUrlInput}
                  onChange={(e) => setVideoUrlInput(e.target.value)}
                  placeholder={t('participation.video_url_placeholder') || 'https://youtube.com/watch?v=... ou https://exemple.com/video.mp4'}
                  className="flex-1"
                />
                <Button type="button" onClick={handleAddVideoByUrl} className="gap-1">
                  <Plus className="w-4 h-4" />
                  {t('participation.add') || 'Ajouter'}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Uploaded Video */}
        {videoUrl && (
          <div className="relative group">
            <div className="w-full aspect-video rounded-lg border border-gray-200 dark:border-gray-600 bg-black overflow-hidden">
              <VideoEmbed
                url={videoUrl}
                className="w-full h-full"
                allowFullscreen={true}
              />
            </div>
            <div className="absolute top-2 right-2 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition">
              {detectVideoPlatform(videoUrl) === 'direct' && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setPreviewVideoUrl(videoUrl)
                    setShowVideoPreview(true)
                  }}
                  className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-lg"
                  title="Prévisualiser"
                >
                  <Eye className="w-4 h-4" />
                </button>
              )}
              <button
                type="button"
                onClick={handleRemoveVideo}
                className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-lg"
                disabled={isSubmitting}
                title="Supprimer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
        {/* Error message for video */}
        {hasVideoError && (
          <div className="mt-4 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>
              {t('participation.errors.content_video_required') || 'Content Video'} - {t('participation.errors.video_required_for_contest') || 'A video is required for this contest'}
            </span>
          </div>
        )}
      </div>

      {/* Submit Buttons */}
      <div className="flex gap-3 pt-4">
        <Button
          type="button"
          onClick={() => onCancel ? onCancel() : router.back()}
          variant="outline"
          className="flex-1"
          disabled={isSubmitting}
        >
          {t('dashboard.contests.participation_form.cancel')}
        </Button>
        <Button
          type="submit"
          disabled={
            !title.trim() || 
            title.trim().length < 10 || 
            !description.trim() || 
            description.trim().length < 100 || 
            (!isNomination && imageUrls.length === 0) || 
            (requiresVideo && !videoUrl) ||
            isSubmitting
          }
          className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white font-bold"
        >
          {isSubmitting 
            ? t('common.submitting') 
            : isEditing 
              ? (t('dashboard.contests.participation_form.edit_participation') || 'Modifier ma candidature')
              : t('participation.submit')}
        </Button>
      </div>

      {/* Image Preview Dialog */}
      <ImagePreviewDialog
        isOpen={showImagePreview}
        imageUrl={previewImageUrl}
        imageAlt="Image preview"
        onClose={() => setShowImagePreview(false)}
      />

      {/* Video Preview Dialog */}
      <VideoPreviewDialog
        isOpen={showVideoPreview}
        videoUrl={previewVideoUrl}
        videoTitle="Video preview"
        onClose={() => setShowVideoPreview(false)}
      />
    </form>
  )
}
