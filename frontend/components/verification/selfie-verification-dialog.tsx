'use client'

import { useState, useRef, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { 
  Camera, 
  RotateCcw, 
  Upload, 
  Check, 
  X,
  Loader2,
  Image as ImageIcon
} from 'lucide-react'
import { verificationService, type VerificationType } from '@/services/verification-service'

interface SelfieVerificationDialogProps {
  isOpen: boolean
  onClose: () => void
  onComplete: (imageUrl: string) => void
  verificationType: 'selfie' | 'selfie_with_pet' | 'selfie_with_document'
  maxSizeMb?: number
  contestId?: number
  contestantId?: number
}

export function SelfieVerificationDialog({
  isOpen,
  onClose,
  onComplete,
  verificationType,
  maxSizeMb = 50,
  contestId,
  contestantId
}: SelfieVerificationDialogProps) {
  const { t } = useLanguage()
  const [mode, setMode] = useState<'select' | 'camera' | 'preview'>('select')
  const [capturedImage, setCapturedImage] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const getTitle = () => {
    switch (verificationType) {
      case 'selfie_with_pet':
        return t('verification.selfie_with_pet') || 'Selfie avec votre animal'
      case 'selfie_with_document':
        return t('verification.selfie_with_document') || 'Selfie avec document'
      default:
        return t('verification.selfie') || 'Selfie de vérification'
    }
  }

  const getInstructions = () => {
    switch (verificationType) {
      case 'selfie_with_pet':
        return t('verification.selfie_pet_instructions') || 'Prenez une photo claire de vous avec votre animal de compagnie.'
      case 'selfie_with_document':
        return t('verification.selfie_document_instructions') || 'Prenez une photo de vous avec une pièce d\'identité visible.'
      default:
        return t('verification.selfie_instructions') || 'Prenez une photo claire de votre visage, bien éclairé.'
    }
  }

  const startCamera = async () => {
    try {
      setError(null)
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: 'user', width: { ideal: 720 }, height: { ideal: 720 } } 
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
      }
      setMode('camera')
    } catch (err) {
      console.error('Camera error:', err)
      setError(t('verification.camera_error') || 'Impossible d\'accéder à la caméra')
    }
  }

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }

  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current
      const canvas = canvasRef.current
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.drawImage(video, 0, 0)
        const imageDataUrl = canvas.toDataURL('image/jpeg', 0.8)
        setCapturedImage(imageDataUrl)
        stopCamera()
        setMode('preview')
      }
    }
  }

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    // Check file size
    if (file.size > maxSizeMb * 1024 * 1024) {
      setError(t('verification.file_too_large') || `Le fichier est trop volumineux (max ${maxSizeMb}MB)`)
      return
    }

    // Check file type
    if (!file.type.startsWith('image/')) {
      setError(t('verification.invalid_file_type') || 'Type de fichier invalide')
      return
    }

    setError(null)
    const reader = new FileReader()
    reader.onload = (e) => {
      setCapturedImage(e.target?.result as string)
      setMode('preview')
    }
    reader.readAsDataURL(file)
  }

  const retake = () => {
    setCapturedImage(null)
    setMode('select')
  }

  const handleSubmit = async () => {
    if (!capturedImage) return
    
    setIsUploading(true)
    try {
      // Convertir data URL en Blob
      const response = await fetch(capturedImage)
      const blob = await response.blob()
      
      // Upload et créer la vérification
      const verification = await verificationService.uploadAndCreateVerification(
        blob,
        `selfie_${Date.now()}.jpg`,
        verificationType as VerificationType,
        'image',
        {
          contest_id: contestId,
          contestant_id: contestantId
        }
      )
      
      onComplete(verification.media_url)
      onClose()
    } catch (err) {
      console.error('Verification upload error:', err)
      setError(err instanceof Error ? err.message : (t('verification.upload_error') || 'Erreur lors de l\'envoi'))
    } finally {
      setIsUploading(false)
    }
  }

  const handleClose = () => {
    stopCamera()
    setCapturedImage(null)
    setMode('select')
    setError(null)
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Camera className="w-5 h-5 text-myfav-primary" />
            {getTitle()}
          </DialogTitle>
          <DialogDescription>
            {getInstructions()}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2 text-red-700 dark:text-red-300">
              <X className="w-4 h-4" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          {/* Selection mode */}
          {mode === 'select' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Button 
                  variant="outline" 
                  className="h-24 flex-col gap-2"
                  onClick={startCamera}
                >
                  <Camera className="w-8 h-8 text-myfav-primary" />
                  <span>{t('verification.use_camera') || 'Utiliser la caméra'}</span>
                </Button>
                <Button 
                  variant="outline" 
                  className="h-24 flex-col gap-2"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="w-8 h-8 text-myfav-primary" />
                  <span>{t('verification.upload_image') || 'Importer une image'}</span>
                </Button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileSelect}
                className="hidden"
              />
            </div>
          )}

          {/* Camera mode */}
          {mode === 'camera' && (
            <div className="space-y-4">
              <div className="relative aspect-square bg-black rounded-xl overflow-hidden">
                <video 
                  ref={videoRef} 
                  autoPlay 
                  playsInline
                  muted
                  className="w-full h-full object-cover"
                />
                {/* Overlay guide */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="w-48 h-48 border-2 border-white/50 rounded-full" />
                </div>
              </div>
              <canvas ref={canvasRef} className="hidden" />
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => { stopCamera(); setMode('select'); }} className="flex-1">
                  <X className="w-4 h-4 mr-2" />
                  {t('common.cancel') || 'Annuler'}
                </Button>
                <Button onClick={capturePhoto} className="flex-1 bg-myfav-primary hover:bg-myfav-primary-dark">
                  <Camera className="w-4 h-4 mr-2" />
                  {t('verification.capture') || 'Capturer'}
                </Button>
              </div>
            </div>
          )}

          {/* Preview mode */}
          {mode === 'preview' && capturedImage && (
            <div className="space-y-4">
              <div className="relative aspect-square bg-gray-100 dark:bg-gray-800 rounded-xl overflow-hidden">
                <img 
                  src={capturedImage} 
                  alt="Preview" 
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="flex gap-3">
                <Button variant="outline" onClick={retake} className="flex-1">
                  <RotateCcw className="w-4 h-4 mr-2" />
                  {t('verification.retake') || 'Reprendre'}
                </Button>
                <Button 
                  onClick={handleSubmit} 
                  disabled={isUploading}
                  className="flex-1 bg-myfav-primary hover:bg-myfav-primary-dark"
                >
                  {isUploading ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4 mr-2" />
                  )}
                  {t('verification.confirm') || 'Confirmer'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
