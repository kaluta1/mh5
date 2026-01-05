'use client'

import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
// import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { contestService } from '@/services/contest-service'
import { Loader2, Flag } from 'lucide-react'

interface ReportContestantDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  contestantId: number
  contestId: number
  contestantTitle?: string
}

const REPORT_REASONS = [
  { value: 'spam', label: 'Spam' },
  { value: 'inappropriate', label: 'Contenu inapproprié' },
  { value: 'harassment', label: 'Harcèlement' },
  { value: 'fake', label: 'Faux compte' },
  { value: 'copyright', label: 'Violation de droits d\'auteur' },
  { value: 'other', label: 'Autre' }
]

export function ReportContestantDialog({
  open,
  onOpenChange,
  contestantId,
  contestId,
  contestantTitle
}: ReportContestantDialogProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [reason, setReason] = useState('')
  const [description, setDescription] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errors, setErrors] = useState<{ reason?: string; description?: string; submit?: string }>({})

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // Validation
    const newErrors: { reason?: string; description?: string } = {}
    if (!reason.trim()) {
      newErrors.reason = t('dashboard.contests.report_contestant.error.reason_required') || 'La raison est requise'
    }
    if (!description.trim()) {
      newErrors.description = t('dashboard.contests.report_contestant.error.description_required') || 'La description est requise'
    } else if (description.trim().length < 10) {
      newErrors.description = t('dashboard.contests.report_contestant.error.description_min_length') || 'La description doit contenir au moins 10 caractères'
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    setIsSubmitting(true)
    setErrors({})

    try {
      await contestService.reportContestant(contestantId, contestId, {
        reason: reason.trim(),
        description: description.trim()
      })

      addToast(
        t('dashboard.contests.report_contestant.success') || 'Votre signalement a été envoyé avec succès !',
        'success'
      )

      // Réinitialiser le formulaire
      setReason('')
      setDescription('')
      setErrors({})
      onOpenChange(false)
    } catch (error: any) {
      console.error('Error reporting contestant:', error)
      
      let errorMessage = t('dashboard.contests.report_contestant.error.submit_error') || 'Erreur lors de l\'envoi du signalement'
      
      if (error.response) {
        // Erreur HTTP avec réponse
        if (error.response.status === 400) {
          errorMessage = error.response.data?.detail || errorMessage
        } else if (error.response.status === 401 || error.response.status === 403) {
          errorMessage = error.response.data?.detail || 'Permission insuffisante'
        } else if (error.response.status >= 500) {
          errorMessage = t('dashboard.contests.report_contestant.error.server_error') || 'Erreur serveur. Veuillez réessayer plus tard.'
        } else {
          errorMessage = error.response.data?.detail || errorMessage
        }
      } else if (error.request) {
        // Requête envoyée mais pas de réponse
        errorMessage = t('dashboard.contests.report_contestant.error.network_error') || 'Erreur de connexion. Vérifiez votre connexion internet.'
      } else {
        // Erreur lors de la configuration de la requête
        errorMessage = error.message || errorMessage
      }
      
      setErrors({ submit: errorMessage })
      addToast(errorMessage, 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleClose = () => {
    if (!isSubmitting) {
      setReason('')
      setDescription('')
      setErrors({})
      onOpenChange(false)
    }
  }

  const getReasonLabel = (value: string) => {
    const reasonMap: { [key: string]: string } = {
      spam: t('dashboard.contests.report_contestant.reasons.spam') || 'Spam',
      inappropriate: t('dashboard.contests.report_contestant.reasons.inappropriate') || 'Contenu inapproprié',
      harassment: t('dashboard.contests.report_contestant.reasons.harassment') || 'Harcèlement',
      fake: t('dashboard.contests.report_contestant.reasons.fake') || 'Faux compte',
      copyright: t('dashboard.contests.report_contestant.reasons.copyright') || 'Violation de droits d\'auteur',
      other: t('dashboard.contests.report_contestant.reasons.other') || 'Autre'
    }
    return reasonMap[value] || value
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px] dark:bg-gray-800">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl text-gray-900 dark:text-white">
            <Flag className="h-5 w-5 text-red-500 dark:text-red-400" />
            {t('dashboard.contests.report_contestant.title') || 'Signaler un participant'}
          </DialogTitle>
          <DialogDescription>
            {t('dashboard.contests.report_contestant.description') || 'Décrivez la raison de votre signalement. Notre équipe examinera votre demande.'}
          </DialogDescription>
          {contestantTitle && (
            <DialogDescription className="text-sm font-medium text-gray-700 dark:text-gray-300 mt-2">
              {t('dashboard.contests.report_contestant.contestant') || 'Participant :'} {contestantTitle}
            </DialogDescription>
          )}
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="reason" className="text-gray-700 dark:text-gray-300">
              {t('dashboard.contests.report_contestant.reason_label') || 'Raison du signalement'}
            </Label>
            <Select value={reason} onValueChange={(value) => {
              setReason(value)
              if (errors.reason) {
                setErrors({ ...errors, reason: undefined })
              }
            }}>
              <SelectTrigger 
                id="reason"
                className={`dark:bg-gray-700 dark:border-gray-600 dark:text-white ${errors.reason ? 'border-red-500' : ''}`}
              >
                <SelectValue placeholder={t('dashboard.contests.report_contestant.reason_placeholder') || 'Sélectionnez une raison'} />
              </SelectTrigger>
              <SelectContent>
                {REPORT_REASONS.map((reasonOption) => (
                  <SelectItem key={reasonOption.value} value={reasonOption.value}>
                    {getReasonLabel(reasonOption.value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.reason && (
              <p className="text-sm text-red-600 dark:text-red-400">{errors.reason}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="description" className="text-gray-700 dark:text-gray-300">
              {t('dashboard.contests.report_contestant.description_label') || 'Description détaillée'}
            </Label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => {
                setDescription(e.target.value)
                if (errors.description) {
                  setErrors({ ...errors, description: undefined })
                }
              }}
              placeholder={t('dashboard.contests.report_contestant.description_placeholder') || 'Décrivez en détail la raison de votre signalement (minimum 10 caractères)...'}
              className={`flex min-h-[120px] w-full rounded-md border ${errors.description ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'} bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50`}
              disabled={isSubmitting}
              maxLength={2000}
            />
            {errors.description && (
              <p className="text-sm text-red-600 dark:text-red-400">{errors.description}</p>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {description.length}/2000 {t('dashboard.contests.report_contestant.characters') || 'caractères'}
            </p>
          </div>

          {errors.submit && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-600 dark:text-red-400">{errors.submit}</p>
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={isSubmitting}
              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
            >
              {t('dashboard.contests.report_contestant.cancel') || 'Annuler'}
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting}
              className="bg-red-500 hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700 text-white font-semibold"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('dashboard.contests.report_contestant.submitting') || 'Envoi en cours...'}
                </>
              ) : (
                t('dashboard.contests.report_contestant.submit') || 'Envoyer le signalement'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

