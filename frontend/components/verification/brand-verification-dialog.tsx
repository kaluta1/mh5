'use client'

import { useState, useRef } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useLanguage } from '@/contexts/language-context'
import { 
  Award, 
  Upload, 
  Check, 
  X,
  Loader2,
  Link,
  AlertTriangle,
  Image as ImageIcon,
  Building2
} from 'lucide-react'
import { verificationService } from '@/services/verification-service'

interface BrandVerificationDialogProps {
  isOpen: boolean
  onClose: () => void
  onComplete: (data: BrandVerificationData) => void
  maxSizeMb?: number
  contestId?: number
  contestantId?: number
}

export interface BrandVerificationData {
  brandName: string
  brandWebsite?: string
  proofDocumentUrl?: string
  description: string
  role?: string
}

export function BrandVerificationDialog({
  isOpen,
  onClose,
  onComplete,
  maxSizeMb = 50,
  contestId,
  contestantId
}: BrandVerificationDialogProps) {
  const { t } = useLanguage()
  const [brandName, setBrandName] = useState('')
  const [brandWebsite, setBrandWebsite] = useState('')
  const [description, setDescription] = useState('')
  const [role, setRole] = useState('')
  const [proofDocument, setProofDocument] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Check file size
    if (file.size > maxSizeMb * 1024 * 1024) {
      setError(t('verification.file_too_large') || `Le fichier dépasse ${maxSizeMb}MB`)
      return
    }

    // Check file type (images and PDFs)
    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      setError(t('verification.invalid_file_type') || 'Type de fichier invalide (images ou PDF)')
      return
    }

    setError(null)
    const reader = new FileReader()
    reader.onload = () => {
      setProofDocument(reader.result as string)
    }
    reader.readAsDataURL(file)
  }

  const handleSubmit = async () => {
    if (!brandName.trim()) {
      setError(t('verification.brand_name_required') || 'Le nom de la marque est requis')
      return
    }

    if (!description.trim()) {
      setError(t('verification.description_required') || 'La description est requise')
      return
    }

    setIsUploading(true)
    setError(null)

    try {
      let proofDocumentUrl = proofDocument
      
      // Si un document a été sélectionné, l'uploader
      if (proofDocument && proofDocument.startsWith('data:')) {
        const response = await fetch(proofDocument)
        const blob = await response.blob()
        const ext = proofDocument.includes('pdf') ? 'pdf' : 'jpg'
        
        const verification = await verificationService.uploadAndCreateVerification(
          blob,
          `brand_proof_${Date.now()}.${ext}`,
          'brand',
          proofDocument.includes('pdf') ? 'document' : 'image',
          {
            contest_id: contestId,
            contestant_id: contestantId
          }
        )
        
        proofDocumentUrl = verification.media_url
      }
      
      const verificationData: BrandVerificationData = {
        brandName: brandName.trim(),
        brandWebsite: brandWebsite || undefined,
        proofDocumentUrl: proofDocumentUrl || undefined,
        description: description.trim(),
        role: role || undefined
      }
      
      onComplete(verificationData)
    } catch (err) {
      console.error('Brand verification error:', err)
      setError(err instanceof Error ? err.message : (t('verification.submit_error') || 'Erreur lors de la soumission'))
    } finally {
      setIsUploading(false)
    }
  }

  const handleClose = () => {
    setBrandName('')
    setBrandWebsite('')
    setDescription('')
    setRole('')
    setProofDocument(null)
    setError(null)
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Award className="w-5 h-5 text-myhigh5-primary" />
            {t('verification.brand_verification') || 'Vérification de marque'}
          </DialogTitle>
          <DialogDescription>
            {t('verification.brand_verification_description') || 
              'Prouvez votre affiliation à une marque ou organisation.'}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {/* Instructions */}
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-200">
              {t('verification.brand_instructions') || 
                'Fournissez des informations sur votre marque ou organisation et une preuve de votre affiliation.'}
            </p>
          </div>

          {/* Brand Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.brand_name') || 'Nom de la marque'} *
            </label>
            <div className="flex gap-2">
              <Building2 className="w-5 h-5 text-gray-400 mt-2" />
              <Input
                type="text"
                value={brandName}
                onChange={(e) => setBrandName(e.target.value)}
                placeholder="Nom de votre marque ou organisation"
                className="flex-1"
              />
            </div>
          </div>

          {/* Brand Website */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.brand_website') || 'Site web de la marque (optionnel)'}
            </label>
            <div className="flex gap-2">
              <Link className="w-5 h-5 text-gray-400 mt-2" />
              <Input
                type="url"
                value={brandWebsite}
                onChange={(e) => setBrandWebsite(e.target.value)}
                placeholder="https://www.votre-marque.com"
                className="flex-1"
              />
            </div>
          </div>

          {/* Role */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.your_role') || 'Votre rôle (optionnel)'}
            </label>
            <Input
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Fondateur, Manager, Ambassadeur..."
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.brand_description') || 'Description de votre affiliation'} *
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('verification.brand_description_placeholder') || 
                'Expliquez votre lien avec cette marque...'}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary resize-none"
            />
          </div>

          {/* Proof Document Upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('verification.proof_document') || 'Document de preuve (optionnel)'}
            </label>
            
            {proofDocument ? (
              <div className="relative p-4 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800">
                <div className="flex items-center gap-3">
                  <ImageIcon className="w-8 h-8 text-myhigh5-primary" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {t('verification.document_uploaded') || 'Document uploadé'}
                    </p>
                    <p className="text-xs text-gray-500">
                      {t('verification.click_change') || 'Cliquez pour changer'}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setProofDocument(null)}
                    className="p-1 bg-red-500 text-white rounded-full hover:bg-red-600"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ) : (
              <div 
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 text-center cursor-pointer hover:border-myhigh5-primary transition"
              >
                <Upload className="w-8 h-8 mx-auto text-gray-400 mb-2" />
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {t('verification.click_upload_document') || 'Cliquez pour ajouter un document'}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                  Images ou PDF - Max {maxSizeMb}MB
                </p>
              </div>
            )}
            
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,application/pdf"
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
            {t('common.cancel') || 'Annuler'}
          </Button>
          <Button 
            onClick={handleSubmit}
            disabled={isUploading || !brandName.trim() || !description.trim()}
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
