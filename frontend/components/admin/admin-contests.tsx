'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Plus, Edit2, Trash2, Eye, Calendar, Users, Clock, Zap, X, Trophy, MapPin, CheckCircle2, AlertCircle, Upload, Vote } from 'lucide-react'
import { UploadButton } from '@/components/ui/upload-button'
import { contestService, type ContestResponse } from '@/lib/services/contest-service'
import api from '@/lib/api'

interface Contest {
  id: number
  name: string
  description?: string
  contest_type: string
  level: string
  season_id?: number
  is_active: boolean
  is_submission_open: boolean
  is_voting_open: boolean
  submission_start_date: string
  submission_end_date: string
  voting_start_date: string
  voting_end_date: string
  image_url?: string
  cover_image_url?: string
  voting_restriction: string
  participant_count?: number
  approved_count?: number
  pending_count?: number
}

export default function AdminContests() {
  const router = useRouter()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [contests, setContests] = useState<Contest[]>([])
  const [filteredContests, setFilteredContests] = useState<Contest[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<'name' | 'date' | 'status'>('date')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [deleteContestId, setDeleteContestId] = useState<number | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    contest_type: '',
    season_id: '',
    is_active: true,
    is_submission_open: true,
    is_voting_open: false,
    submission_start_date: '',
    submission_end_date: '',
    voting_start_date: '',
    voting_end_date: '',
    image_url: '',
    cover_image_url: '',
    voting_restriction: 'none',
    participant_count: 0
  })
  const [uploadedImage, setUploadedImage] = useState<string>('')
  const [seasons, setSeasons] = useState<Array<{ id: number; title: string; level: string }>>([])
  const [loadingSeasons, setLoadingSeasons] = useState(false)

  useEffect(() => {
    fetchContests()
    fetchSeasons()
  }, [])

  const fetchSeasons = async () => {
    try {
      setLoadingSeasons(true)
      const response = await api.get('/api/v1/admin/seasons')
      setSeasons(response.data)
    } catch (error) {
      console.error('Erreur lors du chargement des saisons:', error)
    } finally {
      setLoadingSeasons(false)
    }
  }

  useEffect(() => {
    // Filtrer par recherche
    let filtered = contests.filter(contest =>
      contest.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      contest.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      contest.contest_type.toLowerCase().includes(searchQuery.toLowerCase())
    )

    // Trier
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'name':
          return a.name.localeCompare(b.name)
        case 'date':
          return new Date(b.submission_start_date).getTime() - new Date(a.submission_start_date).getTime()
        case 'status':
          return (b.is_active ? 1 : 0) - (a.is_active ? 1 : 0)
        default:
          return 0
      }
    })

    setFilteredContests(filtered)
  }, [contests, searchQuery, sortBy])

  const fetchContests = async () => {
    try {
      setLoading(true)
      const data = await contestService.getAllContests()
      setContests(data as Contest[])
    } catch (error) {
      console.error('Erreur lors du chargement des concours:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      // Prepare data - remove dates as they are auto-generated on backend
      const dataToSend = {
        name: formData.name,
        description: formData.description,
        contest_type: formData.contest_type,
        season_id: formData.season_id ? parseInt(formData.season_id) : null,
        is_active: formData.is_active,
        is_submission_open: formData.is_submission_open,
        is_voting_open: formData.is_voting_open,
        image_url: formData.image_url,
        voting_restriction: formData.voting_restriction
      }

      if (editingId) {
        await contestService.updateContest(editingId, dataToSend)
        addToast(t('admin.contests.update_success') || 'Concours mis à jour avec succès', 'success')
      } else {
        await contestService.createContest(dataToSend)
        addToast(t('admin.contests.create_success') || 'Concours créé avec succès', 'success')
      }
      fetchContests()
      setShowForm(false)
      setEditingId(null)
      resetForm()
    } catch (error) {
      console.error('Erreur lors de la sauvegarde:', error)
      const errorMsg = editingId ? 'update_error' : 'create_error'
      addToast(t(`admin.contests.${errorMsg}`) || 'Erreur lors de la sauvegarde', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      contest_type: '',
      season_id: '',
      is_active: true,
      is_submission_open: true,
      is_voting_open: false,
      submission_start_date: '',
      submission_end_date: '',
      voting_start_date: '',
      voting_end_date: '',
      image_url: '',
      cover_image_url: '',
      voting_restriction: 'none',
      participant_count: 0
    })
    setUploadedImage('')
  }

  const handleEdit = (contest: Contest) => {
    setFormData({
      name: contest.name,
      description: contest.description || '',
      contest_type: contest.contest_type,
      season_id: contest.season_id?.toString() || '',
      is_active: contest.is_active,
      is_submission_open: contest.is_submission_open,
      is_voting_open: contest.is_voting_open,
      submission_start_date: contest.submission_start_date,
      submission_end_date: contest.submission_end_date,
      voting_start_date: contest.voting_start_date,
      voting_end_date: contest.voting_end_date,
      image_url: contest.image_url || '',
      cover_image_url: contest.cover_image_url || '',
      voting_restriction: contest.voting_restriction || 'none',
      participant_count: contest.participant_count || 0
    })
    if (contest.cover_image_url || contest.image_url) {
      setUploadedImage(contest.cover_image_url || contest.image_url || '')
    }
    setEditingId(contest.id)
    setShowForm(true)
  }

  const handleDeleteClick = (id: number) => {
    setDeleteContestId(id)
    setShowDeleteDialog(true)
  }

  const handleConfirmDelete = async () => {
    if (!deleteContestId) return
    
    setIsDeleting(true)
    try {
      await contestService.deleteContest(deleteContestId)
      addToast(t('admin.contests.delete_success') || 'Concours supprimé avec succès', 'success')
      fetchContests()
      setShowDeleteDialog(false)
      setDeleteContestId(null)
    } catch (error) {
      console.error('Erreur lors de la suppression:', error)
      addToast(t('admin.contests.delete_error') || 'Erreur lors de la suppression', 'error')
    } finally {
      setIsDeleting(false)
    }
  }

  const getLevelLabel = (level: string) => {
    const labels: Record<string, string> = {
      city: 'Ville',
      country: 'Pays',
      region: 'Région',
      continent: 'Continent',
      global: 'Mondial'
    }
    return labels[level] || level
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myfav-primary via-myfav-primary/80 to-myfav-secondary dark:from-myfav-primary/20 dark:via-myfav-primary/10 dark:to-myfav-secondary/10 rounded-xl p-8 border border-myfav-primary/30 dark:border-myfav-primary/20 shadow-lg">
        <div className="flex justify-between items-start gap-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-3">
              <Trophy className="h-8 w-8 text-white dark:text-myfav-secondary" />
              <h1 className="text-4xl font-bold text-white dark:text-white">
                {t('admin.contests.title') || 'Gestion des Concours'}
              </h1>
            </div>
            <p className="text-myfav-primary/90 dark:text-myfav-secondary/80 font-medium">
              {t('admin.contests.description') || 'Créez et gérez vos concours'}
            </p>
            <div className="flex gap-6 mt-4 text-sm">
              <div className="flex items-center gap-2 text-white dark:text-gray-300">
                <Users className="h-4 w-4" />
                <span>{contests.length} concours</span>
              </div>
              <div className="flex items-center gap-2 text-white dark:text-gray-300">
                <CheckCircle2 className="h-4 w-4" />
                <span>{contests.filter(c => c.is_active).length} actifs</span>
              </div>
            </div>
          </div>
          <Button
            onClick={() => {
              setShowForm(true)
              setEditingId(null)
              resetForm()
            }}
            className="gap-2 bg-white text-myfav-primary hover:bg-gray-100 dark:bg-myfav-secondary dark:text-gray-900 dark:hover:bg-myfav-secondary/90 shadow-lg hover:shadow-xl transition-all font-semibold"
          >
            <Plus className="h-5 w-5" />
            {t('admin.contests.new_contest') || 'Nouveau concours'}
          </Button>
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto dark:bg-gray-800">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4 border-b dark:border-gray-700">
              <CardTitle className="text-xl">
                {editingId ? t('admin.contests.edit_contest') : t('admin.contests.create_contest')}
              </CardTitle>
              <button
                onClick={() => {
                  setShowForm(false)
                  setEditingId(null)
                  resetForm()
                }}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                <X className="h-5 w-5" />
              </button>
            </CardHeader>
            <CardContent className="pt-6">
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Image Upload */}
                <div>
                  <label className="block text-sm font-medium mb-3 text-gray-900 dark:text-white">
                    📸 {t('admin.contests.image') || 'Image du concours'}
                  </label>
                  {uploadedImage && (
                    <div className="mb-3 relative">
                      <img src={uploadedImage} alt="Preview" className="h-40 w-40 object-cover rounded-lg border-2 border-myfav-primary/20" />
                      {editingId && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Image actuelle</p>
                      )}
                    </div>
                  )}
                  <UploadButton
                    endpoint="profileImageUploader"
                    onClientUploadComplete={(res) => {
                      if (res?.[0]) {
                        setUploadedImage(res[0].url)
                        setFormData({ ...formData, image_url: res[0].url, cover_image_url: res[0].url })
                      }
                    }}
                    onUploadError={(error) => {
                      console.error('Upload error:', error)
                    }}
                  />
                </div>

                {/* Dates (Editable) */}
                {editingId && (
                  <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
                    <h4 className="font-semibold text-sm text-blue-900 dark:text-blue-200 mb-4">📅 {t('admin.contests.contest_dates') || 'Dates du concours'}</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                          {t('admin.contests.submission_start') || 'Début des uploads'}
                        </label>
                        <Input
                          type="date"
                          value={formData.submission_start_date.split('T')[0]}
                          onChange={(e) => setFormData({ ...formData, submission_start_date: e.target.value })}
                          className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                          {t('admin.contests.submission_end') || 'Fin des uploads'}
                        </label>
                        <Input
                          type="date"
                          value={formData.submission_end_date.split('T')[0]}
                          onChange={(e) => setFormData({ ...formData, submission_end_date: e.target.value })}
                          className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                          {t('admin.contests.voting_start') || 'Début du vote'}
                        </label>
                        <Input
                          type="date"
                          value={formData.voting_start_date.split('T')[0]}
                          onChange={(e) => setFormData({ ...formData, voting_start_date: e.target.value })}
                          className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                          {t('admin.contests.voting_end') || 'Fin du vote'}
                        </label>
                        <Input
                          type="date"
                          value={formData.voting_end_date.split('T')[0]}
                          onChange={(e) => setFormData({ ...formData, voting_end_date: e.target.value })}
                          className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Nom du concours */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.name')}
                  </label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="Ex: Concours de beauté 2024"
                    required
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.contest_description')}
                  </label>
                  <Input
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Description du concours"
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                </div>

                {/* Type de concours */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.contest_type')}
                  </label>
                  <Input
                    value={formData.contest_type}
                    onChange={(e) => setFormData({ ...formData, contest_type: e.target.value })}
                    placeholder="Ex: beauty, handsome"
                    required
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                </div>

                {/* Saison du concours */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.seasons.title') || 'Saison'} <span className="text-red-500">*</span>
                  </label>
                  {loadingSeasons ? (
                    <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-myfav-primary"></div>
                      {t('common.loading') || 'Chargement...'}
                    </div>
                  ) : (
                    <Select 
                      value={formData.season_id} 
                      onValueChange={(value) => setFormData({ ...formData, season_id: value })}
                      required
                    >
                      <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                        <SelectValue placeholder={t('admin.contestants.select_season') || 'Sélectionner une saison'} />
                      </SelectTrigger>
                      <SelectContent className="dark:bg-gray-700">
                        {seasons.map((season) => (
                          <SelectItem key={season.id} value={season.id.toString()}>
                            {season.title} ({t(`admin.seasons.level_${season.level}`) || season.level})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>

                {/* Nombre de participants */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    👥 {t('admin.contests.participant_count') || 'Nombre de participants'}
                  </label>
                  <Input
                    type="number"
                    value={formData.participant_count}
                    onChange={(e) => setFormData({ ...formData, participant_count: parseInt(e.target.value) || 0 })}
                    placeholder="0"
                    min="0"
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                </div>

                {/* Restriction de vote */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.voting_restriction') || 'Restriction de vote'}
                  </label>
                  <Select value={formData.voting_restriction} onValueChange={(value) => setFormData({ ...formData, voting_restriction: value })}>
                    <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-gray-700">
                      <SelectItem value="none">{t('admin.contests.none') || 'Aucune'}</SelectItem>
                      <SelectItem value="male_only">{t('admin.contests.male_only') || 'Hommes uniquement'}</SelectItem>
                      <SelectItem value="female_only">{t('admin.contests.female_only') || 'Femmes uniquement'}</SelectItem>
                      <SelectItem value="geographic">{t('admin.contests.geographic') || 'Géographique'}</SelectItem>
                      <SelectItem value="age_restricted">{t('admin.contests.age_restricted') || 'Restriction d\'âge'}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Checkboxes */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-700">
                    <input
                      type="checkbox"
                      id="is_active"
                      checked={formData.is_active}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                      className="rounded"
                    />
                    <label htmlFor="is_active" className="text-sm font-medium cursor-pointer text-gray-900 dark:text-white">
                      {t('admin.contests.active')}
                    </label>
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-700">
                    <input
                      type="checkbox"
                      id="is_submission_open"
                      checked={formData.is_submission_open}
                      onChange={(e) => setFormData({ ...formData, is_submission_open: e.target.checked })}
                      className="rounded"
                    />
                    <label htmlFor="is_submission_open" className="text-sm font-medium cursor-pointer text-gray-900 dark:text-white">
                      {t('admin.contests.upload_open')}
                    </label>
                  </div>
                </div>

                {/* Info: Dates are auto-generated */}
                <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                  <p className="text-sm text-blue-900 dark:text-blue-200">
                    <strong>ℹ️ Dates automatiques :</strong> Les dates sont générées automatiquement :
                  </p>
                  <ul className="text-sm text-blue-900 dark:text-blue-200 mt-2 ml-4 list-disc">
                    <li>Début des uploads : date de création</li>
                    <li>Fin des uploads : 1 mois après le début</li>
                    <li>Début du vote : 1 jour après la fin des uploads</li>
                    <li>Fin du vote : 1 mois après le début du vote</li>
                  </ul>
                </div>

                {/* Actions */}
                <div className="flex gap-3 justify-end pt-4 border-t dark:border-gray-700">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setShowForm(false)
                      setEditingId(null)
                      resetForm()
                    }}
                    disabled={isSubmitting}
                  >
                    {t('admin.contests.cancel')}
                  </Button>
                  <Button
                    type="submit"
                    disabled={isSubmitting}
                    className="bg-gradient-to-r from-myfav-primary to-myfav-secondary hover:shadow-lg disabled:opacity-70 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? (
                      <div className="flex items-center gap-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        {editingId ? t('admin.contests.updating') : t('admin.contests.creating')}
                      </div>
                    ) : (
                      editingId ? t('admin.contests.edit') : t('admin.contests.create_contest')
                    )}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Barre de recherche et tri */}
      {!loading && contests.length > 0 && (
        <div className="bg-white dark:bg-gray-800/50 rounded-xl p-5 border border-gray-200 dark:border-gray-700 shadow-sm mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Recherche */}
            <div className="md:col-span-2">
              <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <Eye className="h-4 w-4 text-myfav-primary" />
                {t('admin.contests.search_placeholder') || 'Rechercher'}
              </label>
              <Input
                type="text"
                placeholder="Nom, type, description..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="dark:bg-gray-700 dark:border-gray-600 dark:text-white border-gray-300 focus:border-myfav-primary focus:ring-myfav-primary"
              />
            </div>

            {/* Tri */}
            <div>
              <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <Clock className="h-4 w-4 text-myfav-primary" />
                {t('admin.contests.sort') || 'Trier par'}
              </label>
              <Select value={sortBy} onValueChange={(value: any) => setSortBy(value)}>
                <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white border-gray-300 focus:border-myfav-primary focus:ring-myfav-primary">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="dark:bg-gray-700">
                  <SelectItem value="date">
                    <Calendar className="h-4 w-4 inline mr-2" />
                    {t('admin.contests.sort_date') || 'Date (récent)'}
                  </SelectItem>
                  <SelectItem value="name">
                    {t('admin.contests.sort_name') || 'Nom (A-Z)'}
                  </SelectItem>
                  <SelectItem value="status">
                    <CheckCircle2 className="h-4 w-4 inline mr-2" />
                    {t('admin.contests.sort_status') || 'Statut'}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Résultats */}
          {searchQuery && (
            <div className="mt-4 text-sm font-medium text-gray-600 dark:text-gray-400 flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              {filteredContests.length} {filteredContests.length === 1 ? 'résultat' : 'résultats'} trouvé(s)
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myfav-primary"></div>
        </div>
      ) : contests.length === 0 ? (
        <Card className="border-2 border-dashed border-gray-300 dark:border-gray-600">
          <CardContent className="pt-12 pb-12 text-center">
            <Zap className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600 dark:text-gray-400 text-lg">{t('admin.contests.no_contests') || 'Aucun concours trouvé'}</p>
          </CardContent>
        </Card>
      ) : filteredContests.length === 0 ? (
        <Card className="border-2 border-dashed border-gray-300 dark:border-gray-600">
          <CardContent className="pt-12 pb-12 text-center">
            <Zap className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600 dark:text-gray-400 text-lg">Aucun résultat pour "{searchQuery}"</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {filteredContests.map((contest) => (
            <Card key={contest.id} className="overflow-hidden hover:shadow-xl transition-all duration-300 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 hover:border-myfav-primary/50 dark:hover:border-myfav-primary/30">
              <CardContent className="p-0">
                <div className="flex gap-4 h-36 md:h-40">
                  {/* Image de couverture */}
                  <div className="w-40 h-36 md:h-40 flex-shrink-0 bg-gray-200 dark:bg-gray-700 overflow-hidden rounded-l-lg">
                    {contest.cover_image_url || contest.image_url ? (
                      <img
                        src={contest.cover_image_url || contest.image_url}
                        alt={contest.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-myfav-primary to-myfav-secondary">
                        <Zap className="h-8 w-8 text-white" />
                      </div>
                    )}
                  </div>

                  {/* Contenu */}
                  <div className="flex-1 py-4 px-4 flex flex-col justify-between">
                    <div>
                      <div className="mb-3">
                        <h3 className="font-bold text-lg text-gray-900 dark:text-white leading-tight">{contest.name}</h3>
                        <p className="text-xs text-myfav-primary dark:text-myfav-secondary font-semibold mt-1">{contest.contest_type.toUpperCase()}</p>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">{contest.description}</p>
                    </div>

                    <div className="flex flex-wrap gap-2 items-center pt-2">
                      <span className="inline-flex items-center gap-1 bg-myfav-primary/15 text-myfav-primary dark:bg-myfav-primary/25 dark:text-myfav-secondary px-2.5 py-1.5 rounded-full text-xs font-semibold">
                        <MapPin className="h-3.5 w-3.5" />
                        {getLevelLabel(contest.level)}
                      </span>
                      <span className="inline-flex items-center gap-1 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2.5 py-1.5 rounded-full text-xs font-semibold">
                        <Users className="h-3.5 w-3.5" />
                        {contest.participant_count || 0}
                      </span>
                      {(contest.approved_count || 0) > 0 && (
                        <span className="inline-flex items-center gap-1 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 px-2.5 py-1.5 rounded-full text-xs font-semibold">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          {contest.approved_count}
                        </span>
                      )}
                      {(contest.pending_count || 0) > 0 && (
                        <span className="inline-flex items-center gap-1 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-2.5 py-1.5 rounded-full text-xs font-semibold">
                          <AlertCircle className="h-3.5 w-3.5" />
                          {contest.pending_count}
                        </span>
                      )}
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs font-semibold ${contest.is_active ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-400'}`}>
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {contest.is_active ? 'Actif' : 'Inactif'}
                      </span>
                      {contest.is_submission_open && (
                        <span className="inline-flex items-center gap-1 bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 px-2.5 py-1.5 rounded-full text-xs font-semibold">
                          <Upload className="h-3.5 w-3.5" />
                          Upload
                        </span>
                      )}
                      {contest.is_voting_open && (
                        <span className="inline-flex items-center gap-1 bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 px-2.5 py-1.5 rounded-full text-xs font-semibold">
                          <Vote className="h-3.5 w-3.5" />
                          Vote
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-2 py-4 pr-4 min-w-fit justify-center">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleEdit(contest)}
                      className="gap-1.5 hover:bg-myfav-primary/10 hover:text-myfav-primary dark:hover:bg-myfav-primary/20 border-gray-300 dark:border-gray-600"
                    >
                      <Edit2 className="h-4 w-4" />
                      {t('admin.contests.edit') || 'Modifier'}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => router.push(`/dashboard/admin/contests/${contest.id}/contestants`)}
                      className="gap-1.5 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800 hover:bg-blue-50 dark:hover:bg-blue-900/20"
                    >
                      <Users className="h-4 w-4" />
                      {t('admin.contests.candidates') || 'Candidats'}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleDeleteClick(contest.id)}
                      className="gap-1.5 hover:bg-red-600 dark:hover:bg-red-700"
                    >
                      <Trash2 className="h-4 w-4" />
                      {t('admin.contests.delete') || 'Supprimer'}
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        title={t('admin.contests.confirm_delete_title') || 'Supprimer le concours'}
        message={t('admin.contests.confirm_delete_message') || 'Êtes-vous sûr de vouloir supprimer ce concours ? Cette action est irréversible.'}
        confirmText={t('admin.contests.delete') || 'Supprimer'}
        cancelText={t('admin.contests.cancel') || 'Annuler'}
        onConfirm={handleConfirmDelete}
        isLoading={isDeleting}
        isDangerous={true}
      />
    </div>
  )
}
