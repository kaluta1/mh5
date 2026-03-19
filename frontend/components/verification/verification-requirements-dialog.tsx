'use client'

import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { 
  CheckCircle, 
  XCircle, 
  Camera, 
  Mic, 
  Video, 
  Shield, 
  AlertTriangle,
  ChevronRight,
  Loader2,
  Award,
  FileCheck
} from 'lucide-react'

interface VerificationRequirement {
  id: string
  label: string
  icon: React.ReactNode
  required: boolean
  completed: boolean
  onVerify: () => void
}

interface VerificationRequirementsDialogProps {
  isOpen: boolean
  onClose: () => void
  contestName: string
  requirements: {
    requiresKyc?: boolean
    requiresVisualVerification?: boolean
    requiresVoiceVerification?: boolean
    requiresBrandVerification?: boolean
    requiresContentVerification?: boolean
    requiresVideo?: boolean
  }
  userVerifications: {
    isKycVerified?: boolean
    hasVisualVerification?: boolean
    hasVoiceVerification?: boolean
    hasBrandVerification?: boolean
    hasContentVerification?: boolean
  }
  onStartVerification: (type: 'kyc' | 'visual' | 'voice' | 'brand' | 'content' | 'video') => void
  onProceed: () => void
}

export function VerificationRequirementsDialog({
  isOpen,
  onClose,
  contestName,
  requirements,
  userVerifications,
  onStartVerification,
  onProceed
}: VerificationRequirementsDialogProps) {
  const { t } = useLanguage()
  const [isChecking, setIsChecking] = useState(false)

  const verificationItems: VerificationRequirement[] = []

  // KYC Verification
  if (requirements.requiresKyc) {
    verificationItems.push({
      id: 'kyc',
      label: t('verification.kyc_verification') || 'Vérification KYC',
      icon: <Shield className="w-5 h-5" />,
      required: true,
      completed: userVerifications.isKycVerified || false,
      onVerify: () => onStartVerification('kyc')
    })
  }

  // Visual Verification (Selfie)
  if (requirements.requiresVisualVerification) {
    verificationItems.push({
      id: 'visual',
      label: t('verification.visual_verification') || 'Vérification visuelle (Selfie)',
      icon: <Camera className="w-5 h-5" />,
      required: true,
      completed: userVerifications.hasVisualVerification || false,
      onVerify: () => onStartVerification('visual')
    })
  }

  // Voice Verification
  if (requirements.requiresVoiceVerification) {
    verificationItems.push({
      id: 'voice',
      label: t('verification.voice_verification') || 'Vérification vocale',
      icon: <Mic className="w-5 h-5" />,
      required: true,
      completed: userVerifications.hasVoiceVerification || false,
      onVerify: () => onStartVerification('voice')
    })
  }

  // Brand Verification
  if (requirements.requiresBrandVerification) {
    verificationItems.push({
      id: 'brand',
      label: t('verification.brand_verification') || 'Vérification de marque',
      icon: <Award className="w-5 h-5" />,
      required: true,
      completed: userVerifications.hasBrandVerification || false,
      onVerify: () => onStartVerification('brand')
    })
  }

  // Content Ownership Verification
  if (requirements.requiresContentVerification) {
    verificationItems.push({
      id: 'content',
      label: t('verification.content_ownership') || 'Propriété du contenu',
      icon: <FileCheck className="w-5 h-5" />,
      required: true,
      completed: userVerifications.hasContentVerification || false,
      onVerify: () => onStartVerification('content')
    })
  }

  const allCompleted = verificationItems.every(item => item.completed)
  const completedCount = verificationItems.filter(item => item.completed).length

  return (
    <Dialog open={isOpen} onOpenChange={() => {}}>
      <DialogContent className="max-w-md [&>button]:hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-myhigh5-primary" />
            {t('verification.requirements_title') || 'Vérifications requises'}
          </DialogTitle>
          <DialogDescription>
            {t('verification.requirements_description') || 'Ce concours nécessite les vérifications suivantes pour participer.'}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {/* Contest name */}
          <div className="mb-4 p-3 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('verification.contest') || 'Concours'}
            </p>
            <p className="font-semibold text-gray-900 dark:text-white">{contestName}</p>
          </div>

          {/* Progress */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {t('verification.progress') || 'Progression'}
              </span>
              <span className="text-sm font-medium text-myhigh5-primary">
                {completedCount}/{verificationItems.length}
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div 
                className="bg-myhigh5-primary h-2 rounded-full transition-all duration-300"
                style={{ width: `${(completedCount / verificationItems.length) * 100}%` }}
              />
            </div>
          </div>

          {/* Verification items */}
          <div className="space-y-3">
            {verificationItems.map((item) => (
              <div 
                key={item.id}
                className={`flex items-center justify-between p-3 rounded-lg border transition-all ${
                  item.completed 
                    ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800' 
                    : 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-full ${
                    item.completed 
                      ? 'bg-green-100 dark:bg-green-800 text-green-600 dark:text-green-400' 
                      : 'bg-amber-100 dark:bg-amber-800 text-amber-600 dark:text-amber-400'
                  }`}>
                    {item.icon}
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white text-sm">
                      {item.label}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {item.completed 
                        ? (t('verification.completed') || 'Complété') 
                        : (t('verification.required') || 'Requis')}
                    </p>
                  </div>
                </div>
                
                {item.completed ? (
                  <CheckCircle className="w-5 h-5 text-green-500" />
                ) : (
                  <Button 
                    size="sm" 
                    variant="outline"
                    onClick={item.onVerify}
                    className="text-amber-600 border-amber-300 hover:bg-amber-100 dark:text-amber-400 dark:border-amber-700 dark:hover:bg-amber-900/30"
                  >
                    {t('verification.verify') || 'Vérifier'}
                    <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                )}
              </div>
            ))}
          </div>

          {/* Warning if not all completed */}
          {!allCompleted && (
            <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-sm text-amber-800 dark:text-amber-200">
                {t('verification.incomplete_warning') || 'Complétez toutes les vérifications pour pouvoir participer.'}
              </p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <Button variant="outline" onClick={onClose} className="flex-1">
            {t('common.cancel') || 'Annuler'}
          </Button>
          <Button 
            onClick={onProceed}
            disabled={!allCompleted}
            className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary-dark"
          >
            {isChecking ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : null}
            {t('verification.proceed') || 'Continuer'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
