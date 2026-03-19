'use client'

import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { contestService } from '@/services/contest-service'
import { Loader2, Flag, Ban, AlertTriangle, UserX, Shield, Copyright, HelpCircle, CheckCircle2 } from 'lucide-react'

interface ReportContestantDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  contestantId: number
  contestId: number
  contestantTitle?: string
}

const REPORT_REASONS = [
  { value: 'spam', icon: Ban, color: 'text-orange-500', bg: 'bg-orange-500/10 border-orange-500/20 hover:bg-orange-500/20', selectedBg: 'bg-orange-500/20 border-orange-500 ring-1 ring-orange-500/50' },
  { value: 'inappropriate', icon: AlertTriangle, color: 'text-red-500', bg: 'bg-red-500/10 border-red-500/20 hover:bg-red-500/20', selectedBg: 'bg-red-500/20 border-red-500 ring-1 ring-red-500/50' },
  { value: 'harassment', icon: UserX, color: 'text-purple-500', bg: 'bg-purple-500/10 border-purple-500/20 hover:bg-purple-500/20', selectedBg: 'bg-purple-500/20 border-purple-500 ring-1 ring-purple-500/50' },
  { value: 'fake', icon: Shield, color: 'text-blue-500', bg: 'bg-blue-500/10 border-blue-500/20 hover:bg-blue-500/20', selectedBg: 'bg-blue-500/20 border-blue-500 ring-1 ring-blue-500/50' },
  { value: 'copyright', icon: Copyright, color: 'text-amber-500', bg: 'bg-amber-500/10 border-amber-500/20 hover:bg-amber-500/20', selectedBg: 'bg-amber-500/20 border-amber-500 ring-1 ring-amber-500/50' },
  { value: 'other', icon: HelpCircle, color: 'text-gray-500', bg: 'bg-gray-500/10 border-gray-500/20 hover:bg-gray-500/20', selectedBg: 'bg-gray-500/20 border-gray-500 ring-1 ring-gray-500/50' }
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
  const [isSuccess, setIsSuccess] = useState(false)
  const [errors, setErrors] = useState<{ reason?: string; description?: string; submit?: string }>({})

  const getReasonLabel = (value: string) => {
    const reasonMap: { [key: string]: string } = {
      spam: t('dashboard.contests.report_contestant.reasons.spam') || 'Spam',
      inappropriate: t('dashboard.contests.report_contestant.reasons.inappropriate') || 'Contenu inappropri\u00e9',
      harassment: t('dashboard.contests.report_contestant.reasons.harassment') || 'Harc\u00e8lement',
      fake: t('dashboard.contests.report_contestant.reasons.fake') || 'Faux compte',
      copyright: t('dashboard.contests.report_contestant.reasons.copyright') || 'Violation de droits d\'auteur',
      other: t('dashboard.contests.report_contestant.reasons.other') || 'Autre'
    }
    return reasonMap[value] || value
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const newErrors: { reason?: string; description?: string } = {}
    if (!reason.trim()) {
      newErrors.reason = t('dashboard.contests.report_contestant.error.reason_required') || 'Veuillez s\u00e9lectionner une raison'
    }
    if (!description.trim()) {
      newErrors.description = t('dashboard.contests.report_contestant.error.description_required') || 'La description est requise'
    } else if (description.trim().length < 10) {
      newErrors.description = t('dashboard.contests.report_contestant.error.description_min_length') || 'La description doit contenir au moins 10 caract\u00e8res'
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

      setIsSuccess(true)
      setTimeout(() => {
        setReason('')
        setDescription('')
        setErrors({})
        setIsSuccess(false)
        onOpenChange(false)
      }, 2000)
    } catch (error: any) {
      console.error('Error reporting contestant:', error)

      let errorMessage = t('dashboard.contests.report_contestant.error.submit_error') || 'Erreur lors de l\'envoi du signalement'

      if (error.response) {
        if (error.response.status === 400) {
          errorMessage = error.response.data?.detail || errorMessage
        } else if (error.response.status === 401 || error.response.status === 403) {
          errorMessage = error.response.data?.detail || 'Permission insuffisante'
        } else if (error.response.status >= 500) {
          errorMessage = t('dashboard.contests.report_contestant.error.server_error') || 'Erreur serveur. Veuillez r\u00e9essayer plus tard.'
        } else {
          errorMessage = error.response.data?.detail || errorMessage
        }
      } else if (error.request) {
        errorMessage = t('dashboard.contests.report_contestant.error.network_error') || 'Erreur de connexion. V\u00e9rifiez votre connexion internet.'
      } else {
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
      setIsSuccess(false)
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[520px] dark:bg-gray-800 p-0 overflow-hidden">
        {/* Header with gradient */}
        <div className="bg-gradient-to-r from-red-500/10 to-orange-500/10 dark:from-red-500/20 dark:to-orange-500/20 px-6 pt-6 pb-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3 text-xl text-gray-900 dark:text-white">
              <div className="w-10 h-10 rounded-full bg-red-500/15 dark:bg-red-500/25 flex items-center justify-center">
                <Flag className="h-5 w-5 text-red-500" />
              </div>
              {t('dashboard.contests.report_contestant.title') || 'Signaler un participant'}
            </DialogTitle>
            <DialogDescription className="text-gray-600 dark:text-gray-400 mt-2">
              {t('dashboard.contests.report_contestant.description') || 'D\u00e9crivez la raison de votre signalement. Notre \u00e9quipe examinera votre demande.'}
            </DialogDescription>
          </DialogHeader>
          {contestantTitle && (
            <div className="mt-3 inline-flex items-center gap-2 bg-white/60 dark:bg-gray-700/60 rounded-lg px-3 py-1.5 text-sm">
              <span className="text-gray-500 dark:text-gray-400">{t('dashboard.contests.report_contestant.contestant') || 'Participant :'}</span>
              <span className="font-medium text-gray-900 dark:text-white truncate max-w-[250px]">{contestantTitle}</span>
            </div>
          )}
        </div>

        {isSuccess ? (
          <div className="px-6 py-12 flex flex-col items-center gap-4 text-center">
            <div className="w-16 h-16 rounded-full bg-green-500/15 flex items-center justify-center animate-in zoom-in duration-300">
              <CheckCircle2 className="h-8 w-8 text-green-500" />
            </div>
            <div>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">
                {t('dashboard.contests.report_contestant.success_title') || 'Signalement envoy\u00e9'}
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t('dashboard.contests.report_contestant.success') || 'Votre signalement a \u00e9t\u00e9 envoy\u00e9 avec succ\u00e8s. Merci pour votre vigilance !'}
              </p>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="px-6 pb-6 pt-2 space-y-5">
            {/* Reason selection as grid of cards */}
            <div className="space-y-2">
              <Label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('dashboard.contests.report_contestant.reason_label') || 'Raison du signalement'}
              </Label>
              <div className="grid grid-cols-2 gap-2">
                {REPORT_REASONS.map((r) => {
                  const Icon = r.icon
                  const isSelected = reason === r.value
                  return (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() => {
                        setReason(r.value)
                        if (errors.reason) setErrors({ ...errors, reason: undefined })
                      }}
                      className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border text-left text-sm font-medium transition-all duration-150
                        ${isSelected ? r.selectedBg : r.bg}
                        ${isSelected ? 'dark:border-opacity-80' : 'dark:border-gray-600/50'}
                      `}
                    >
                      <Icon className={`w-4 h-4 flex-shrink-0 ${r.color}`} />
                      <span className="text-gray-800 dark:text-gray-200">{getReasonLabel(r.value)}</span>
                    </button>
                  )
                })}
              </div>
              {errors.reason && (
                <p className="text-sm text-red-500 mt-1">{errors.reason}</p>
              )}
            </div>

            {/* Description textarea */}
            <div className="space-y-2">
              <Label htmlFor="report-description" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('dashboard.contests.report_contestant.description_label') || 'Description d\u00e9taill\u00e9e'}
              </Label>
              <textarea
                id="report-description"
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value)
                  if (errors.description) setErrors({ ...errors, description: undefined })
                }}
                placeholder={t('dashboard.contests.report_contestant.description_placeholder') || 'D\u00e9crivez en d\u00e9tail la raison de votre signalement...'}
                className={`flex min-h-[100px] w-full rounded-lg border ${errors.description ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 dark:border-gray-600 focus:ring-blue-500'} bg-white dark:bg-gray-700/50 px-3 py-2.5 text-sm text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-offset-0 transition-shadow resize-none disabled:cursor-not-allowed disabled:opacity-50`}
                disabled={isSubmitting}
                maxLength={2000}
              />
              <div className="flex justify-between items-center">
                {errors.description ? (
                  <p className="text-sm text-red-500">{errors.description}</p>
                ) : (
                  <p className="text-xs text-gray-400">
                    {t('dashboard.contests.report_contestant.min_chars') || 'Minimum 10 caract\u00e8res'}
                  </p>
                )}
                <p className="text-xs text-gray-400">{description.length}/2000</p>
              </div>
            </div>

            {errors.submit && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-sm text-red-600 dark:text-red-400">{errors.submit}</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={handleClose}
                disabled={isSubmitting}
                className="flex-1 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              >
                {t('dashboard.contests.report_contestant.cancel') || 'Annuler'}
              </Button>
              <Button
                type="submit"
                disabled={isSubmitting || !reason}
                className="flex-1 bg-red-500 hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700 text-white font-semibold disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {t('dashboard.contests.report_contestant.submitting') || 'Envoi...'}
                  </>
                ) : (
                  <>
                    <Flag className="mr-2 h-4 w-4" />
                    {t('dashboard.contests.report_contestant.submit') || 'Envoyer'}
                  </>
                )}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
