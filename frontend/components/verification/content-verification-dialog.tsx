'use client'

import { useState, useRef } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useLanguage } from '@/contexts/language-context'
import { 
  FileCheck, 
  Upload, 
  Check, 
  X,
  Loader2,
  Link,
  AlertTriangle,
  Image as ImageIcon
} from 'lucide-react'
import { verificationService } from '@/services/verification-service'

interface ContentVerificationDialogProps {
  isOpen: boolean
  onClose: () => void
  onComplete: (data: ContentVerificationData) => void
  maxSizeMb?: number
  contestId?: number
  contestantId?: number
}

export interface ContentVerificationData {
  contentUrl?: string
  proofImageUrl?: string
  description: string
  platform?: string
}

export function ContentVerificationDialog({
  isOpen,
  onClose,
  onComplete,
  maxSizeMb = 50,
  contestId,
  contestantId
}: ContentVerificationDialogProps) {
  const { t } = useLanguage()
  const [contentUrl, setContentUrl] = useState('')
  const [description, setDescription] = useState('')
  const [platform, setPlatform] = useState('')
  const [proofImage, setProofImage] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Check file type first
    if (!file.type.startsWith('image/')) {
      setError(t('verification.invalid_file_type') || 'Invalid file type. Please upload a supported file.')
      return
    }

    // Check file size
    if (file.size > maxSizeMb * 1024 * 1024) {
      const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2)
      setError(t('verification.file_too_large_with_size') || `The image is too large (${fileSizeMB} MB). Maximum size: ${maxSizeMb} MB`)
      return
    }

    setError(null)
    const reader = new FileReader()
    reader.onload = () => {
      setProofImage(reader.result as string)
    }
    reader.readAsDataURL(file)
  }

  const handleSubmit = async () => {
    if (!description.trim()) {
      setError(t('verification.description_required') || 'Description is required')
      return
    }

    setIsUploading(true)
    setError(null)

    try {
      let proofImageUrl = proofImage
      
      // Si une image a été sélectionnée, l'uploader
      if (proofImage && proofImage.startsWith('data:')) {
        const response = await fetch(proofImage)
        const blob = await response.blob()
        
        const verification = await verificationService.uploadAndCreateVerification(
          blob,
          `content_proof_${Date.now()}.jpg`,
          'content',
          'image',
          {
            contest_id: contestId,
            contestant_id: contestantId
          }
        )
        
        proofImageUrl = verification.media_url
      }
      
      const verificationData: ContentVerificationData = {
        contentUrl: contentUrl || undefined,
        proofImageUrl: proofImageUrl || undefined,
        description: description.trim(),
        platform: platform || undefined
      }
      
      onComplete(verificationData)
    } catch (err) {
      console.error('Content verification error:', err)
      setError(err instanceof Error ? err.message : (t('verification.submit_error') || 'Submit Error'))
    } finally {
      setIsUploading(false)
    }
  }

  const handleClose = () => {
    setContentUrl('')
    setDescription('')
    setPlatform('')
    setProofImage(null)
    setError(null)
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileCheck className="w-5 h-5 text-myhigh5-primary" />
            {t('verification.content_ownership') || 'Content Ownership'}
          </DialogTitle>
          <DialogDescription>
            {t('verification.content_ownership_description') || 
              'Prove that you own the content you are submitting.'}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {/* Instructions */}
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-200">
              {t('verification.content_instructions') || 
                'Content Instructions'}
            </p>
          </div>

          {/* Content URL */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.content_url') || 'Link to your original content (optional)'}
            </label>
            <div className="flex gap-2">
              <Link className="w-5 h-5 text-gray-400 mt-2" />
              <Input
                type="url"
                value={contentUrl}
                onChange={(e) => setContentUrl(e.target.value)}
                placeholder="https://instagram.com/your-post"
                className="flex-1"
              />
            </div>
          </div>

          {/* Platform */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.platform') || 'Plateforme (optionnel)'}
            </label>
            <Input
              type="text"
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              placeholder="Instagram, TikTok, YouTube..."
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.content_description') || 'Description de la preuve'} *
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('verification.content_description_placeholder') || 
                'Explain how this content belongs to you...'}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary resize-none"
            />
          </div>

          {/* Proof Image Upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.proof_image') || 'Proof image (screenshot)'}
            </label>
            
            {proofImage ? (
              <div className="relative">
                <img 
                  src={proofImage} 
                  alt="Proof" 
                  className="w-full h-48 object-contain rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800"
                />
                <button
                  type="button"
                  onClick={() => setProofImage(null)}
                  className="absolute top-2 right-2 p-1 bg-red-500 text-white rounded-full hover:bg-red-600"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div 
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 text-center cursor-pointer hover:border-myhigh5-primary transition"
              >
                <ImageIcon className="w-8 h-8 mx-auto text-gray-400 mb-2" />
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {t('verification.click_upload_proof') || 'Click to upload proof'}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                  Max {maxSizeMb}MB
                </p>
              </div>
            )}
            
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileSelect}
              className="hidden"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-500" />
              <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <Button variant="outline" onClick={handleClose} className="flex-1">
            {t('common.cancel') || 'Cancel'}
          </Button>
          <Button 
            onClick={handleSubmit}
            disabled={isUploading || !description.trim()}
            className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary-dark"
          >
            {isUploading ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Check className="w-4 h-4 mr-2" />
            )}
            {t('verification.submit') || 'Soumettre'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
