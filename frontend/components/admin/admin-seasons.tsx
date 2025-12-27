'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Plus, Edit2, Trash2, Calendar, Loader2 } from 'lucide-react'
import api from '@/lib/api'
import { cn } from '@/lib/utils'

interface Season {
  id: number
  title: string
  level: 'city' | 'country' | 'regional' | 'continent' | 'global'
  contestants_count?: number
  contests_count?: number
}

export default function AdminSeasons() {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [seasons, setSeasons] = useState<Season[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [seasonToDelete, setSeasonToDelete] = useState<number | null>(null)
  const [formData, setFormData] = useState({
    title: '',
    level: 'city' as Season['level']
  })

  useEffect(() => {
    fetchSeasons()
  }, [])

  const fetchSeasons = async () => {
    try {
      setLoading(true)
      const response = await api.get('/api/v1/admin/seasons')
      setSeasons(response.data)
    } catch (error) {
      console.error('Erreur lors du chargement des saisons:', error)
      addToast(t('admin.seasons.load_error'), 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      if (editingId) {
        await api.put(`/api/v1/admin/seasons/${editingId}`, formData)
        addToast(t('admin.seasons.update_success'), 'success')
      } else {
        await api.post('/api/v1/admin/seasons', formData)
        addToast(t('admin.seasons.create_success'), 'success')
      }
      fetchSeasons()
      setShowForm(false)
      setEditingId(null)
      setFormData({
        title: '',
        level: 'city'
      })
    } catch (error: any) {
      console.error('Erreur lors de la sauvegarde:', error)
      let errorMessage = error.response?.data?.detail || error.message || t('admin.seasons.save_error')
      
      // Traduire les messages d'erreur spécifiques
      if (errorMessage && typeof errorMessage === 'string') {
        // Détecter l'erreur de niveau déjà existant
        const levelExistsMatch = errorMessage.match(/Une saison avec le niveau '([^']+)' existe déjà/i) || 
                                 errorMessage.match(/A season with the level '([^']+)' already exists/i) ||
                                 errorMessage.match(/Ya existe una temporada con el nivel '([^']+)'/i) ||
                                 errorMessage.match(/Eine Saison mit der Ebene '([^']+)' existiert bereits/i)
        
        if (levelExistsMatch) {
          const levelKey = levelExistsMatch[1].toLowerCase()
          const levelTranslations: Record<string, string> = {
            'ville': 'level_city',
            'city': 'level_city',
            'ciudad': 'level_city',
            'stadt': 'level_city',
            'pays': 'level_country',
            'country': 'level_country',
            'país': 'level_country',
            'land': 'level_country',
            'régional': 'level_regional',
            'regional': 'level_regional',
            'continent': 'level_continent',
            'continente': 'level_continent',
            'kontinent': 'level_continent',
            'global': 'level_global'
          }
          const levelTranslationKey = levelTranslations[levelKey] || levelKey
          const levelName = t(`admin.seasons.${levelTranslationKey}`) || levelExistsMatch[1]
          const translatedMessage = t('admin.seasons.error_level_exists')
          errorMessage = translatedMessage.replace('{level}', levelName)
        }
        
        // Détecter l'erreur de niveau invalide
        if (errorMessage.includes('Niveau invalide') || errorMessage.includes('Invalid level') || 
            errorMessage.includes('Nivel inválido') || errorMessage.includes('Ungültige Ebene')) {
          const validLevels = ['city', 'country', 'regional', 'continent', 'global']
          const translatedLevels = validLevels.map(l => t(`admin.seasons.level_${l}`)).join(', ')
          const translatedMessage = t('admin.seasons.error_invalid_level')
          errorMessage = translatedMessage.replace('{levels}', translatedLevels)
        }
      }
      
      addToast(errorMessage, 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleEdit = (season: Season) => {
    setFormData({
      title: season.title,
      level: season.level
    })
    setEditingId(season.id)
    setShowForm(true)
  }

  const handleDeleteClick = (id: number) => {
    setSeasonToDelete(id)
    setShowDeleteDialog(true)
  }

  const handleConfirmDelete = async () => {
    if (!seasonToDelete) return
    
    setIsDeleting(true)
    try {
      await api.delete(`/api/v1/admin/seasons/${seasonToDelete}`)
      addToast(t('admin.seasons.delete_success'), 'success')
      fetchSeasons()
      setShowDeleteDialog(false)
      setSeasonToDelete(null)
    } catch (error) {
      console.error('Erreur lors de la suppression:', error)
      addToast(t('admin.seasons.delete_error'), 'error')
    } finally {
      setIsDeleting(false)
    }
  }

  const getLevelBadge = (level: Season['level']) => {
    const badges = {
      city: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-800 dark:text-blue-300', label: t('admin.seasons.level_city') },
      country: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-800 dark:text-green-300', label: t('admin.seasons.level_country') },
      regional: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-800 dark:text-purple-300', label: t('admin.seasons.level_regional') },
      continent: { bg: 'bg-orange-100 dark:bg-orange-900/30', text: 'text-orange-800 dark:text-orange-300', label: t('admin.seasons.level_continent') },
      global: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-800 dark:text-yellow-300', label: t('admin.seasons.level_global') }
    }
    const badge = badges[level] || badges.city
    return (
      <span className={cn("px-3 py-1 rounded-full text-xs font-semibold", badge.bg, badge.text)}>
        {badge.label}
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex items-center gap-3 mb-2">
          <Calendar className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
          <h1 className="text-4xl font-bold text-white dark:text-white">
            {t('admin.seasons.title')}
          </h1>
        </div>
        <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium">
          {t('admin.seasons.description')}
        </p>
      </div>

      {/* Form */}
      {showForm && (
        <Card className="border-gray-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle>{editingId ? t('admin.seasons.edit_season') : t('admin.seasons.create_season')}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('admin.seasons.season_title')} <span className="text-red-500">*</span>
                </label>
                <Input
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="Ex: Saison Printemps 2024"
                  required
                  disabled={isSubmitting}
                  className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('admin.seasons.level')} <span className="text-red-500">*</span>
                </label>
                <Select 
                  value={formData.level} 
                  onValueChange={(value) => setFormData({ ...formData, level: value as Season['level'] })}
                  disabled={isSubmitting}
                >
                  <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="city">{t('admin.seasons.level_city')}</SelectItem>
                    <SelectItem value="country">{t('admin.seasons.level_country')}</SelectItem>
                    <SelectItem value="regional">{t('admin.seasons.level_regional')}</SelectItem>
                    <SelectItem value="continent">{t('admin.seasons.level_continent')}</SelectItem>
                    <SelectItem value="global">{t('admin.seasons.level_global')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex gap-2 justify-end pt-4">
                <Button 
                  type="button" 
                  variant="outline" 
                  onClick={() => {
                    setShowForm(false)
                    setEditingId(null)
                    setFormData({ title: '', level: 'city' })
                  }}
                  disabled={isSubmitting}
                >
                  {t('admin.seasons.cancel')}
                </Button>
                <Button 
                  type="submit" 
                  className="bg-myhigh5-primary hover:bg-myhigh5-primary/90"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      {t('common.submitting')}
                    </>
                  ) : (
                    editingId ? t('admin.seasons.edit') : t('admin.seasons.create')
                  )}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      {!showForm && (
        <div className="flex justify-end">
          <Button 
            onClick={() => setShowForm(true)} 
            className="gap-2 bg-myhigh5-primary hover:bg-myhigh5-primary/90"
          >
            <Plus className="h-4 w-4" />
            {t('admin.seasons.new_season')}
          </Button>
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
        </div>
      ) : (
        <div className="grid gap-4">
          {seasons.length === 0 ? (
            <Card className="border-gray-200 dark:border-gray-700">
              <CardContent className="pt-6 text-center text-gray-500 dark:text-gray-400">
                {t('admin.seasons.no_seasons')}
              </CardContent>
            </Card>
          ) : (
            seasons.map((season) => (
              <Card key={season.id} className="border-gray-200 dark:border-gray-700 hover:shadow-lg transition-shadow">
                <CardContent className="pt-6">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-4 flex-1">
                      <div className="flex-1">
                        <h3 className="font-semibold text-lg text-gray-900 dark:text-white">
                          {season.title}
                        </h3>
                        <div className="mt-2 flex items-center gap-4 flex-wrap">
                          {getLevelBadge(season.level)}
                          <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                            <span className="flex items-center gap-1">
                              <span className="font-medium text-gray-900 dark:text-white">{season.contestants_count || 0}</span>
                              <span>{t('admin.seasons.contestants_count')}</span>
                            </span>
                            <span className="flex items-center gap-1">
                              <span className="font-medium text-gray-900 dark:text-white">{season.contests_count || 0}</span>
                              <span>{t('admin.seasons.contests_count')}</span>
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleEdit(season)}
                        className="gap-1.5"
                        disabled={isDeleting}
                      >
                        <Edit2 className="h-4 w-4" />
                        {t('admin.seasons.edit')}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleDeleteClick(season.id)}
                        className="gap-1.5"
                        disabled={isDeleting}
                      >
                        <Trash2 className="h-4 w-4" />
                        {t('admin.seasons.delete')}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        title={t('admin.seasons.confirm_delete_title')}
        message={t('admin.seasons.confirm_delete_message')}
        confirmText={t('admin.seasons.delete')}
        cancelText={t('admin.seasons.cancel')}
        onConfirm={handleConfirmDelete}
        isLoading={isDeleting}
        isDangerous={true}
      />
    </div>
  )
}
