'use client'

import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
// import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { contestService } from '@/services/contest-service'
import { Loader2, Lightbulb } from 'lucide-react'

interface SuggestContestDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const CONTEST_CATEGORIES = [
  'beauty',
  'handsome',
  'latest_hits',
  'talent',
  'photography',
  'fitness',
  'fashion',
  'music',
  'dance',
  'cooking',
  'art',
  'comics',
  'other'
]

export function SuggestContestDialog({ open, onOpenChange }: SuggestContestDialogProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errors, setErrors] = useState<{ name?: string; category?: string; submit?: string }>({})

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // Validation
    const newErrors: { name?: string; category?: string } = {}
    if (!name.trim()) {
      newErrors.name = t('dashboard.contests.suggest_contest.error.name_required') || 'Le nom du concours est requis'
    }
    if (!category) {
      newErrors.category = t('dashboard.contests.suggest_contest.error.category_required') || 'La catégorie est requise'
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    setIsSubmitting(true)
    setErrors({})

    try {
      await contestService.createSuggestedContest({
        name: name.trim(),
        description: description.trim() || undefined,
        category: category
      })

      addToast(
        t('dashboard.contests.suggest_contest.success') || 'Votre suggestion a été envoyée avec succès !',
        'success'
      )

      // Réinitialiser le formulaire
      setName('')
      setDescription('')
      setCategory('')
      setErrors({})
      onOpenChange(false)
    } catch (error: any) {
      console.error('Error creating suggested contest:', error)
      
      let errorMessage = t('dashboard.contests.suggest_contest.error.submit_error') || 'Erreur lors de l\'envoi de la suggestion'
      
      if (error.response) {
        // Erreur HTTP avec réponse
        if (error.response.status === 400) {
          errorMessage = error.response.data?.detail || errorMessage
        } else if (error.response.status === 401 || error.response.status === 403) {
          errorMessage = error.response.data?.detail || 'Permission insuffisante'
        } else if (error.response.status >= 500) {
          errorMessage = t('dashboard.contests.suggest_contest.error.server_error') || 'Erreur serveur. Veuillez réessayer plus tard.'
        } else {
          errorMessage = error.response.data?.detail || errorMessage
        }
      } else if (error.request) {
        // Requête envoyée mais pas de réponse
        errorMessage = t('dashboard.contests.suggest_contest.error.network_error') || 'Erreur de connexion. Vérifiez votre connexion internet.'
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
      setName('')
      setDescription('')
      setCategory('')
      setErrors({})
      onOpenChange(false)
    }
  }

  const getCategoryLabel = (cat: string) => {
    const translationKey = `dashboard.contests.contest_type.${cat}`
    const translated = t(translationKey)
    if (translated && !translated.includes('dashboard.contests.contest_type')) {
      return translated
    }
    return cat.charAt(0).toUpperCase() + cat.slice(1).replace(/_/g, ' ')
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px] dark:bg-gray-800">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl text-gray-900 dark:text-white">
            <Lightbulb className="h-5 w-5 text-blue-500 dark:text-blue-400" />
            {t('dashboard.contests.suggest_contest.title') || 'Suggérer un concours'}
          </DialogTitle>
          <DialogDescription>
            {t('dashboard.contests.suggest_contest.description') || 'Proposez une idée de concours à notre équipe'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">
              {t('dashboard.contests.suggest_contest.name_label') || 'Nom du concours'} *
            </Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (errors.name) setErrors({ ...errors, name: undefined })
              }}
              placeholder={t('dashboard.contests.suggest_contest.name_placeholder') || 'Ex: Concours de beauté 2024'}
              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              disabled={isSubmitting}
            />
            {errors.name && (
              <p className="text-sm text-red-500 dark:text-red-400">{errors.name}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">
              {t('dashboard.contests.suggest_contest.description_label') || 'Description'}
            </Label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('dashboard.contests.suggest_contest.description_placeholder') || 'Décrivez votre idée de concours...'}
              className="flex min-h-[100px] w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="category">
              {t('dashboard.contests.suggest_contest.category_label') || 'Catégorie'} *
            </Label>
            <Select
              value={category}
              onValueChange={(value) => {
                setCategory(value)
                if (errors.category) setErrors({ ...errors, category: undefined })
              }}
              disabled={isSubmitting}
            >
              <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                <SelectValue placeholder={t('dashboard.contests.suggest_contest.category_placeholder') || 'Sélectionnez une catégorie'} />
              </SelectTrigger>
              <SelectContent className="dark:bg-gray-700">
                {CONTEST_CATEGORIES.map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {getCategoryLabel(cat)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.category && (
              <p className="text-sm text-red-500 dark:text-red-400">{errors.category}</p>
            )}
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
              {t('dashboard.contests.suggest_contest.cancel') || 'Annuler'}
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting}
              className="bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white font-semibold"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('dashboard.contests.suggest_contest.submitting') || 'Envoi en cours...'}
                </>
              ) : (
                t('dashboard.contests.suggest_contest.submit') || 'Envoyer la suggestion'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

