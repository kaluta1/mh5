'use client'

import { useState, useEffect } from 'react'
import { X, Upload, FileText, Image as ImageIcon, Video, Eye, Link, Plus, AlertCircle, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ImagePreviewDialog } from '@/components/ui/image-preview-dialog'
import { VideoPreviewDialog } from '@/components/ui/video-preview-dialog'
import { useLanguage } from '@/contexts/language-context'
import { useRouter } from 'next/navigation'
import { UploadButton } from '@uploadthing/react'
import type { OurFileRouter } from '@/app/api/uploadthing/core'
import { useToast } from '@/components/ui/toast'

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
}

export function ParticipationForm({ contestId, onSubmit, onCancel, isSubmitting: externalIsSubmitting, isEditing = false, initialData, mediaRequirements }: ParticipationFormProps) {
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
  const minImages = mediaRequirements?.minImages ?? 1
  const maxImages = mediaRequirements?.maxImages ?? 10
  const requiresVideo = mediaRequirements?.requiresVideo ?? false
  const maxVideos = mediaRequirements?.maxVideos ?? 1

  // Récupérer le token depuis localStorage
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (token) {
      setAccessToken(token)
    }
  }, [])

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
    setVideoUrl(videoUrlInput.trim())
    setVideoUrlInput('')
    setShowVideoUrlInput(false)
    addToast(t('participation.video_added') || 'Vidéo ajoutée', 'success')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!title.trim()) {
      addToast('Le titre est requis', 'error')
      return
    }

    if (!description.trim()) {
      addToast('La description est requise', 'error')
      return
    }

    if (imageUrls.length === 0) {
      addToast('Au moins une image est requise', 'error')
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

  return (
    <form onSubmit={handleSubmit} className="space-y-6">

      {/* Section 1: Titre */}
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
          {t('participation.title')} *
        </h3>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t('participation.title_placeholder')}
          maxLength={200}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
          disabled={isSubmitting}
        />
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
          {title.length}/200
        </p>
      </div>

      {/* Section 2: Description */}
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <FileText className="w-5 h-5" />
          {t('participation.description')} *
        </h3>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t('participation.descriptionPlaceholder')}
          maxLength={1000}
          rows={4}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary resize-none"
          disabled={isSubmitting}
        />
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
          {description.length}/1000
        </p>
      </div>

      {/* Media Requirements Info */}
      {mediaRequirements && (
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
          <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-200 mb-2 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {t('participation.media_requirements') || 'Exigences média'}
          </h4>
          <ul className="text-sm text-blue-800 dark:text-blue-300 space-y-1">
            <li className="flex items-center gap-2">
              {imageUrls.length >= minImages ? <CheckCircle className="w-4 h-4 text-green-500" /> : <AlertCircle className="w-4 h-4 text-amber-500" />}
              {t('participation.images_required') || 'Images'}: {minImages} min, {maxImages} max ({imageUrls.length}/{maxImages})
            </li>
            {requiresVideo && (
              <li className="flex items-center gap-2">
                {videoUrl ? <CheckCircle className="w-4 h-4 text-green-500" /> : <AlertCircle className="w-4 h-4 text-amber-500" />}
                {t('participation.video_required') || 'Vidéo obligatoire'}
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Section 3: Images */}
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <ImageIcon className="w-5 h-5" />
          {t('participation.images')} {minImages > 0 && '*'} ({imageUrls.length}/{maxImages})
        </h3>
        
        {imageUrls.length < maxImages && (
          <div className="space-y-3 mb-4">
            {/* Upload button */}
            <div className="p-6 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg bg-white/50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
              {accessToken && (
                <UploadButton<OurFileRouter, 'contestantMedia'>
                  endpoint="contestantMedia"
                  headers={{
                    'x-access-token': accessToken
                  }}
                  onClientUploadComplete={(res) => {
                    if (res && res.length > 0) {
                      const newUrls = res.map(file => file.url)
                      setImageUrls([...imageUrls, ...newUrls])
                    }
                  }}
                  onUploadError={(error: Error) => {
                    // Vérifier si c'est une erreur de modération
                    if (error.message.includes('Contenu rejeté')) {
                      addToast(t('moderation.content_rejected') || `⚠️ ${error.message}`, 'error')
                    } else {
                      addToast(`${t('participation.uploadError') || "Erreur d'upload"}: ${error.message}`, 'error')
                    }
                  }}
                  content={{
                    button({ ready }) {
                      if (ready) return <div className="font-semibold">{t('dashboard.contests.participation_form.click_add_images')}</div>
                      return t('dashboard.contests.participation_form.preparing')
                    },
                    allowedContent({ ready, fileTypes, isUploading }) {
                      if (!ready) return t('dashboard.contests.participation_form.checking_files')
                      if (isUploading) return t('dashboard.contests.participation_form.uploading')
                      return `${t('dashboard.contests.participation_form.images_format')} (${fileTypes.join(', ')})`
                    },
                  }}
                  appearance={{
                    button: 'ut-uploading:opacity-50 bg-gray-800 hover:bg-gray-900 dark:bg-gray-700 dark:hover:bg-gray-600 text-white font-semibold py-2 px-4 rounded-lg transition',
                    container: 'w-full',
                    allowedContent: 'text-sm text-gray-600 dark:text-gray-400 mt-2',
                  }}
                  disabled={isSubmitting || imageUrls.length >= maxImages}
                />
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
      </div>

      {/* Section 4: Vidéo */}
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Video className="w-5 h-5" />
          {requiresVideo 
            ? (t('participation.video_required_title') || 'Vidéo *')
            : (t('participation.video_optional') || 'Vidéo (optionnel)')}
        </h3>
        
        {!videoUrl && (
          <div className="space-y-3">
            {/* Upload button */}
            <div className="p-6 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg bg-white/50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
              {accessToken && (
                <UploadButton<OurFileRouter, 'contestantMedia'>
                  endpoint="contestantMedia"
                  headers={{
                    'x-access-token': accessToken
                  }}
                  onClientUploadComplete={(res) => {
                    if (res && res.length > 0) {
                      setVideoUrl(res[0].url)
                    }
                  }}
                  onUploadError={(error: Error) => {
                    // Vérifier si c'est une erreur de modération
                    if (error.message.includes('Contenu rejeté')) {
                      addToast(t('moderation.content_rejected') || `⚠️ ${error.message}`, 'error')
                    } else {
                      addToast(`${t('participation.uploadError') || "Erreur d'upload"}: ${error.message}`, 'error')
                    }
                  }}
                  content={{
                    button({ ready }) {
                      if (ready) return <div className="font-semibold">{t('dashboard.contests.participation_form.click_add_video')}</div>
                      return t('dashboard.contests.participation_form.preparing')
                    },
                    allowedContent({ ready, fileTypes, isUploading }) {
                      if (!ready) return t('dashboard.contests.participation_form.checking_files')
                      if (isUploading) return t('dashboard.contests.participation_form.uploading')
                      return `${t('dashboard.contests.participation_form.video_format')} (${fileTypes.join(', ')})`
                    },
                  }}
                  appearance={{
                    button: 'ut-uploading:opacity-50 bg-gray-800 hover:bg-gray-900 dark:bg-gray-700 dark:hover:bg-gray-600 text-white font-semibold py-2 px-4 rounded-lg transition',
                    container: 'w-full',
                    allowedContent: 'text-sm text-gray-600 dark:text-gray-400 mt-2',
                  }}
                  disabled={isSubmitting}
                />
              )}
            </div>

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
                  placeholder={t('participation.video_url_placeholder') || 'https://exemple.com/video.mp4'}
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
            <video
              src={videoUrl}
              controls
              className="w-full h-48 rounded-lg border border-gray-200 dark:border-gray-600 bg-black cursor-pointer hover:opacity-75 transition"
              onClick={() => {
                setPreviewVideoUrl(videoUrl)
                setShowVideoPreview(true)
              }}
            />
            <div className="absolute inset-0 flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100 transition">
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
          disabled={!title.trim() || !description.trim() || imageUrls.length === 0 || isSubmitting}
          className="flex-1 bg-myfav-primary hover:bg-myfav-primary-dark text-white font-bold"
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
