'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CheckCircle2, XCircle, Eye, MessageCircle, ThumbsUp, Image, Video, Calendar, Trophy, X, Upload, Loader2, Trash2, EyeOff, Plus, Edit2 } from 'lucide-react'
import { MediaViewerModal, type MediaItem } from '@/components/media'
import { UploadButton } from '@/components/ui/upload-button'
import api from '@/lib/api'

interface Comment {
  id: number
  text: string
  author_name: string
  created_at: string
  is_hidden?: boolean
}

interface Contestant {
  id: number
  user_id: number
  season_id: number
  title?: string
  description?: string
  registration_date: string
  verification_status: string
  is_active: boolean
  is_qualified: boolean
  author_name?: string
  author_avatar_url?: string
  votes_count: number
  comments_count?: number
  images_count: number
  videos_count: number
  media_items?: MediaItem[]
  comments?: Comment[]
}

interface Season {
  id: number
  title: string
  level: string
}

interface User {
  id: number
  email: string
  full_name?: string
  username?: string
  avatar_url?: string
}

interface User {
  id: number
  email: string
  full_name?: string
  username?: string
}

interface AdminContestantsProps {
  contestId?: number
}

export default function AdminContestants({ contestId }: AdminContestantsProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [contestants, setContestants] = useState<Contestant[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedContestant, setSelectedContestant] = useState<Contestant | null>(null)
  const [loadingComments, setLoadingComments] = useState(false)
  const [showDialog, setShowDialog] = useState(false)
  const [selectedMedia, setSelectedMedia] = useState<MediaItem | null>(null)
  const [showMediaViewer, setShowMediaViewer] = useState(false)
  const [loadingContestantId, setLoadingContestantId] = useState<number | null>(null)
  const [loadingAction, setLoadingAction] = useState<'approve' | 'reject' | null>(null)
  const [uploadingContestantId, setUploadingContestantId] = useState<number | null>(null)
  const [showUploadDialog, setShowUploadDialog] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingContestant, setEditingContestant] = useState<Contestant | null>(null)
  const [seasons, setSeasons] = useState<Season[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [selectedLevel, setSelectedLevel] = useState<string>('city')
  const [availableSeasons, setAvailableSeasons] = useState<Season[]>([])
  const [loadingSeasons, setLoadingSeasons] = useState(false)
  const [availableLevels, setAvailableLevels] = useState<string[]>([])
  const [formData, setFormData] = useState({
    user_id: '',
    level: 'city' as 'city' | 'country' | 'regional' | 'continent' | 'global',
    season_id: '',
    title: '',
    description: '',
    verification_status: 'pending' as 'pending' | 'verified' | 'rejected'
  })
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    fetchContestants()
    fetchUsers()
  }, [filter, contestId])

  useEffect(() => {
    if (selectedLevel) {
      fetchSeasonsByLevel(selectedLevel)
    }
  }, [selectedLevel])

  useEffect(() => {
    if (editingContestant) {
      // Trouver le niveau de la saison du contestant
      const contestantSeason = seasons.find(s => s.id === editingContestant.season_id)
      if (contestantSeason) {
        setSelectedLevel(contestantSeason.level)
        setFormData({
          user_id: editingContestant.user_id.toString(),
          level: contestantSeason.level as 'city' | 'country' | 'regional' | 'continent' | 'global',
          season_id: editingContestant.season_id.toString(),
          title: editingContestant.title || '',
          description: editingContestant.description || '',
          verification_status: editingContestant.verification_status as 'pending' | 'verified' | 'rejected'
        })
      }
    } else {
      // En mode création, utiliser le premier niveau disponible
      const defaultLevel = availableLevels.length > 0 ? availableLevels[0] : 'city'
      setFormData({
        user_id: '',
        level: defaultLevel as 'city' | 'country' | 'regional' | 'continent' | 'global',
        season_id: '',
        title: '',
        description: '',
        verification_status: 'pending'
      })
      setSelectedLevel(defaultLevel)
    }
  }, [editingContestant, seasons, availableLevels])

  const loadContestantComments = async (contestantId: number) => {
    try {
      setLoadingComments(true)
      const response = await api.get(`/api/v1/admin/contestants/${contestantId}/comments`)
      const comments = response.data || []
      
      // Mettre à jour le contestant sélectionné avec les commentaires
      setSelectedContestant(prev => {
        if (prev && prev.id === contestantId) {
          return {
            ...prev,
            comments: comments
          }
        }
        return prev
      })
    } catch (error) {
      console.error('Erreur lors du chargement des commentaires:', error)
      // En cas d'erreur, initialiser avec un tableau vide
      setSelectedContestant(prev => {
        if (prev && prev.id === contestantId) {
          return {
            ...prev,
            comments: []
          }
        }
        return prev
      })
    } finally {
      setLoadingComments(false)
    }
  }

  const fetchContestants = async () => {
    try {
      setLoading(true)
      const statusParam = filter !== 'all' ? `?status_filter=${filter}` : ''
      const endpoint = contestId 
        ? `/api/v1/admin/contests/${contestId}/contestants${statusParam}`
        : `/api/v1/admin/contestants${statusParam}`
      const response = await api.get(endpoint)
      setContestants(response.data)
    } catch (error) {
      console.error('Erreur lors du chargement des candidats:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchUsers = async () => {
    try {
      const response = await api.get('/api/v1/admin/users')
      setUsers(response.data)
    } catch (error) {
      console.error('Erreur lors du chargement des utilisateurs:', error)
    }
  }

  const fetchSeasonsByLevel = async (level: string) => {
    try {
      setLoadingSeasons(true)
      const response = await api.get(`/api/v1/admin/seasons/by-level/${level}`)
      setAvailableSeasons(response.data)
      // Si on est en mode édition et que la saison actuelle n'est pas dans la liste, l'ajouter
      if (editingContestant && response.data.length > 0) {
        const currentSeason = seasons.find(s => s.id === editingContestant.season_id)
        if (currentSeason && !response.data.find(s => s.id === currentSeason.id)) {
          setAvailableSeasons([...response.data, currentSeason])
        }
      }
    } catch (error) {
      console.error('Erreur lors du chargement des saisons:', error)
      addToast(t('admin.contestants.seasons_load_error') || 'Erreur lors du chargement des saisons', 'error')
    } finally {
      setLoadingSeasons(false)
    }
  }

  const fetchAllSeasons = async () => {
    try {
      const response = await api.get<Season[]>('/api/v1/admin/seasons')
      setSeasons(response.data)
      // Extraire les niveaux uniques qui existent
      const uniqueLevels: string[] = Array.from(new Set(response.data.map((s: Season) => s.level)))
      setAvailableLevels(uniqueLevels)
      // Si le niveau actuel n'existe pas, réinitialiser au premier niveau disponible
      if (uniqueLevels.length > 0 && !uniqueLevels.includes(formData.level)) {
        setFormData(prev => ({ ...prev, level: uniqueLevels[0] as typeof formData.level }))
        setSelectedLevel(uniqueLevels[0])
      }
    } catch (error) {
      console.error('Erreur lors du chargement de toutes les saisons:', error)
    }
  }

  useEffect(() => {
    fetchAllSeasons()
  }, [])

  const handleApprove = async (id: number) => {
    try {
      setLoadingContestantId(id)
      setLoadingAction('approve')
      await api.post(`/api/v1/admin/contestants/${id}/approve`)
      
      // Update selected contestant if it's the one being approved
      if (selectedContestant?.id === id) {
        setSelectedContestant({
          ...selectedContestant,
          verification_status: 'verified'
        })
      }
      
      addToast(t('admin.contestants.approve_success') || 'Candidat approuvé avec succès', 'success')
      await fetchContestants()
    } catch (error) {
      console.error('Erreur lors de l\'approbation:', error)
      addToast(t('admin.contestants.approve_error') || 'Erreur lors de l\'approbation du candidat', 'error')
    } finally {
      setLoadingContestantId(null)
      setLoadingAction(null)
    }
  }

  const handleReject = async (id: number) => {
    try {
      setLoadingContestantId(id)
      setLoadingAction('reject')
      await api.post(`/api/v1/admin/contestants/${id}/reject`)
      
      // Update selected contestant if it's the one being rejected
      if (selectedContestant?.id === id) {
        setSelectedContestant({
          ...selectedContestant,
          verification_status: 'rejected'
        })
      }
      
      addToast(t('admin.contestants.reject_success') || 'Candidat rejeté avec succès', 'success')
      await fetchContestants()
    } catch (error) {
      console.error('Erreur lors du rejet:', error)
      addToast(t('admin.contestants.reject_error') || 'Erreur lors du rejet du candidat', 'error')
    } finally {
      setLoadingContestantId(null)
      setLoadingAction(null)
    }
  }

  const handleStatusChange = async (id: number, newStatus: string) => {
    try {
      setLoadingContestantId(id)
      setLoadingAction(newStatus as 'approve' | 'reject')
      
      await api.put(`/api/v1/admin/contestants/${id}/status?status=${newStatus}`)
      
      // Update selected contestant if it's the one being updated
      if (selectedContestant?.id === id) {
        setSelectedContestant({
          ...selectedContestant,
          verification_status: newStatus
        })
      }
      
      addToast(t('admin.contestants.status_update_success') || 'Statut du candidat mis à jour avec succès', 'success')
      await fetchContestants()
    } catch (error) {
      console.error('Erreur lors de la mise à jour du statut:', error)
      addToast(t('admin.contestants.status_update_error') || 'Erreur lors de la mise à jour du statut', 'error')
    } finally {
      setLoadingContestantId(null)
      setLoadingAction(null)
    }
  }

  const handleDeleteComment = async (commentId: number) => {
    try {
      await api.delete(`/api/v1/admin/comments/${commentId}`)
      
      // Update selected contestant by removing the comment
      if (selectedContestant) {
        setSelectedContestant({
          ...selectedContestant,
          comments: selectedContestant.comments?.filter(c => c.id !== commentId) || []
        })
      }
      addToast(t('admin.contestants.comment_delete_success') || 'Commentaire supprimé avec succès', 'success')
    } catch (error) {
      console.error('Erreur lors de la suppression du commentaire:', error)
      addToast(t('admin.contestants.comment_delete_error') || 'Erreur lors de la suppression du commentaire', 'error')
    }
  }

  const handleHideComment = async (commentId: number) => {
    try {
      await api.put(`/api/v1/admin/comments/${commentId}/hide`)
      
      // Update selected contestant by marking comment as hidden
      if (selectedContestant) {
        setSelectedContestant({
          ...selectedContestant,
          comments: selectedContestant.comments?.filter(c => c.id !== commentId) || []
        })
      }
      addToast(t('admin.contestants.comment_hide_success') || 'Commentaire caché avec succès', 'success')
    } catch (error) {
      console.error('Erreur lors du masquage du commentaire:', error)
      addToast(t('admin.contestants.comment_hide_error') || 'Erreur lors du masquage du commentaire', 'error')
    }
  }

  const handleShowComment = async (commentId: number) => {
    try {
      await api.put(`/api/v1/admin/comments/${commentId}/show`)
      
      // Refresh contestants to show the comment again
      addToast(t('admin.contestants.comment_show_success') || 'Commentaire affiché avec succès', 'success')
      await fetchContestants()
    } catch (error) {
      console.error('Erreur lors de l\'affichage du commentaire:', error)
      addToast(t('admin.contestants.comment_show_error') || 'Erreur lors de l\'affichage du commentaire', 'error')
    }
  }

  const handleRestoreComment = async (commentId: number) => {
    try {
      await api.put(`/api/v1/admin/comments/${commentId}/restore`)
      
      // Refresh contestants to show the comment again
      addToast(t('admin.contestants.comment_restore_success') || 'Commentaire restauré avec succès', 'success')
      await fetchContestants()
    } catch (error) {
      console.error('Erreur lors de la restauration du commentaire:', error)
      addToast(t('admin.contestants.comment_restore_error') || 'Erreur lors de la restauration du commentaire', 'error')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      const payload = {
        user_id: parseInt(formData.user_id),
        season_id: parseInt(formData.season_id),
        title: formData.title || null,
        description: formData.description || null,
        verification_status: formData.verification_status
      }

      if (editingContestant) {
        await api.put(`/api/v1/admin/contestants/${editingContestant.id}`, payload)
        addToast(t('admin.contestants.update_success') || 'Candidat mis à jour avec succès', 'success')
      } else {
        await api.post('/api/v1/admin/contestants', payload)
        addToast(t('admin.contestants.create_success') || 'Candidat créé avec succès', 'success')
      }
      
      setShowForm(false)
      setEditingContestant(null)
      await fetchContestants()
    } catch (error: any) {
      console.error('Erreur lors de la sauvegarde:', error)
      const errorMessage = error.response?.data?.detail || error.message || (t('admin.contestants.save_error') || 'Erreur lors de la sauvegarde')
      addToast(errorMessage, 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleEdit = (contestant: Contestant) => {
    setEditingContestant(contestant)
    setShowForm(true)
  }

  const handleCancel = () => {
    setShowForm(false)
    setEditingContestant(null)
    const defaultLevel = availableLevels.length > 0 ? availableLevels[0] : 'city'
    setFormData({
      user_id: '',
      level: defaultLevel as 'city' | 'country' | 'regional' | 'continent' | 'global',
      season_id: '',
      title: '',
      description: '',
      verification_status: 'pending'
    })
    setSelectedLevel(defaultLevel)
  }

  const filteredContestants = contestants.filter((c) =>
    c.author_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.title?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { bg: string; text: string; label: string }> = {
      pending: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'En attente' },
      verified: { bg: 'bg-green-100', text: 'text-green-800', label: 'Vérifié' },
      rejected: { bg: 'bg-red-100', text: 'text-red-800', label: 'Rejeté' }
    }
    const badge = badges[status] || badges.pending
    return <span className={`px-2 py-1 rounded text-sm font-medium ${badge.bg} ${badge.text}`}>{badge.label}</span>
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myfav-primary via-myfav-primary/80 to-myfav-secondary dark:from-myfav-primary/20 dark:via-myfav-primary/10 dark:to-myfav-secondary/10 rounded-xl p-8 border border-myfav-primary/30 dark:border-myfav-primary/20 shadow-lg">
        <div className="flex items-center gap-3 mb-2">
          <Trophy className="h-8 w-8 text-white dark:text-myfav-secondary" />
          <h1 className="text-4xl font-bold text-white dark:text-white">
            {t('admin.contestants.title') || 'Gestion des Candidats'}
          </h1>
        </div>
        <p className="text-white dark:text-gray-300 font-medium">
          {t('admin.contestants.description') || 'Approuvez ou rejetez les candidatures'}
        </p>
      </div>

      {/* Filters and Search */}
      <div className="bg-white dark:bg-gray-800/50 rounded-xl p-5 border border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="flex-1 w-full">
            <Input
              placeholder={t('admin.contestants.search_placeholder') || 'Rechercher par nom ou titre...'}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white border-gray-300 focus:border-myfav-primary focus:ring-myfav-primary"
            />
          </div>
          <div className="flex gap-2 w-full md:w-auto">
            {!showForm && (
              <Button
                onClick={() => setShowForm(true)}
                className="gap-2 bg-myfav-primary hover:bg-myfav-primary/90"
              >
                <Plus className="h-4 w-4" />
                {t('admin.contestants.new_contestant') || 'Nouveau candidat'}
              </Button>
            )}
            <Button
              variant={filter === 'all' ? 'default' : 'outline'}
              onClick={() => setFilter('all')}
              className={filter === 'all' ? 'bg-myfav-primary hover:bg-myfav-primary/90' : ''}
            >
              {t('admin.contestants.all') || 'Tous'}
            </Button>
            <Button
              variant={filter === 'pending' ? 'default' : 'outline'}
              onClick={() => setFilter('pending')}
              className={filter === 'pending' ? 'bg-yellow-600 hover:bg-yellow-700' : ''}
            >
              {t('admin.contestants.pending') || 'En attente'}
            </Button>
            <Button
              variant={filter === 'verified' ? 'default' : 'outline'}
              onClick={() => setFilter('verified')}
              className={filter === 'verified' ? 'bg-green-600 hover:bg-green-700' : ''}
            >
              {t('admin.contestants.verified') || 'Vérifiés'}
            </Button>
          </div>
        </div>
      </div>

      {/* Form for Create/Edit */}
      {showForm && (
        <Card className="border-gray-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle>
              {editingContestant ? (t('admin.contestants.edit_contestant') || 'Modifier le candidat') : (t('admin.contestants.new_contestant') || 'Nouveau candidat')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* User Selection */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('admin.contestants.user') || 'Utilisateur'} <span className="text-red-500">*</span>
                </label>
                <Select
                  value={formData.user_id}
                  onValueChange={(value) => setFormData({ ...formData, user_id: value })}
                  disabled={!!editingContestant}
                  required
                >
                  <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                    <SelectValue placeholder={t('admin.contestants.select_user') || 'Sélectionner un utilisateur'} />
                  </SelectTrigger>
                  <SelectContent>
                    {users.map((user) => (
                      <SelectItem key={user.id} value={user.id.toString()}>
                        {user.full_name || user.username || user.email}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Level Selection */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('admin.seasons.level') || 'Niveau'} <span className="text-red-500">*</span>
                </label>
                {availableLevels.length === 0 ? (
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {t('admin.contestants.no_seasons_available') || 'Aucune saison disponible. Veuillez créer une saison d\'abord.'}
                  </div>
                ) : (
                  <Select
                    value={formData.level}
                    onValueChange={(value) => {
                      setFormData({ ...formData, level: value as typeof formData.level, season_id: '' })
                      setSelectedLevel(value)
                    }}
                    required
                  >
                    <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availableLevels.includes('city') && (
                        <SelectItem value="city">{t('admin.seasons.level_city') || 'Ville'}</SelectItem>
                      )}
                      {availableLevels.includes('country') && (
                        <SelectItem value="country">{t('admin.seasons.level_country') || 'Pays'}</SelectItem>
                      )}
                      {availableLevels.includes('regional') && (
                        <SelectItem value="regional">{t('admin.seasons.level_regional') || 'Régional'}</SelectItem>
                      )}
                      {availableLevels.includes('continent') && (
                        <SelectItem value="continent">{t('admin.seasons.level_continent') || 'Continent'}</SelectItem>
                      )}
                      {availableLevels.includes('global') && (
                        <SelectItem value="global">{t('admin.seasons.level_global') || 'Global'}</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                )}
              </div>

              {/* Season Selection */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('admin.seasons.title') || 'Saison'} <span className="text-red-500">*</span>
                </label>
                {loadingSeasons ? (
                  <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('common.loading') || 'Chargement...'}
                  </div>
                ) : (
                  <Select
                    value={formData.season_id}
                    onValueChange={(value) => setFormData({ ...formData, season_id: value })}
                    required
                    disabled={availableSeasons.length === 0}
                  >
                    <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                      <SelectValue placeholder={availableSeasons.length === 0 ? (t('admin.contestants.no_seasons_for_level') || 'Aucune saison disponible pour ce niveau') : (t('admin.contestants.select_season') || 'Sélectionner une saison')} />
                    </SelectTrigger>
                    <SelectContent>
                      {availableSeasons.map((season) => (
                        <SelectItem key={season.id} value={season.id.toString()}>
                          {season.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>

              {/* Title */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('admin.contestants.title') || 'Titre'}
                </label>
                <Input
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder={t('admin.contestants.title_placeholder') || 'Titre du candidat'}
                  className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('admin.contestants.description') || 'Description'}
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder={t('admin.contestants.description_placeholder') || 'Description du candidat'}
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary focus:border-transparent resize-none"
                  rows={4}
                />
              </div>

              {/* Verification Status */}
              <div>
                <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                  {t('admin.contestants.status') || 'Statut'}
                </label>
                <Select
                  value={formData.verification_status}
                  onValueChange={(value) => setFormData({ ...formData, verification_status: value as typeof formData.verification_status })}
                >
                  <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">{t('admin.contestants.status_pending') || 'En attente'}</SelectItem>
                    <SelectItem value="verified">{t('admin.contestants.status_verified') || 'Vérifié'}</SelectItem>
                    <SelectItem value="rejected">{t('admin.contestants.status_rejected') || 'Rejeté'}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Actions */}
              <div className="flex gap-2 justify-end pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleCancel}
                  disabled={isSubmitting}
                >
                  {t('common.cancel') || 'Annuler'}
                </Button>
                <Button
                  type="submit"
                  className="bg-myfav-primary hover:bg-myfav-primary/90"
                  disabled={isSubmitting}
                >
                  {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {editingContestant ? (t('common.save') || 'Enregistrer') : (t('common.create') || 'Créer')}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myfav-primary"></div>
        </div>
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            {filteredContestants.length === 0 ? (
              <div className="text-center py-12 text-gray-500 dark:text-gray-400">
                {t('admin.contestants.no_contestants') || 'Aucun candidat trouvé'}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">{t('admin.contestants.author') || 'Auteur'}</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">Titre</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">{t('admin.contestants.status') || 'Statut'}</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">{t('admin.contestants.images') || 'Images'}</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">{t('admin.contestants.videos') || 'Vidéos'}</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">{t('admin.contestants.votes') || 'Votes'}</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">{t('admin.contestants.comments') || 'Commentaires'}</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">{t('admin.contestants.registration_date') || 'Date d\'inscription'}</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white">{t('admin.contestants.actions') || 'Actions'}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {filteredContestants.map((contestant) => (
                      <tr key={contestant.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            {contestant.author_avatar_url && (
                              <img
                                src={contestant.author_avatar_url}
                                alt={contestant.author_name}
                                className="h-10 w-10 rounded-full object-cover"
                              />
                            )}
                            <span className="text-sm font-medium text-gray-900 dark:text-white">{contestant.author_name || 'N/A'}</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">{contestant.title || 'Sans titre'}</td>
                        <td className="px-6 py-4">{getStatusBadge(contestant.verification_status)}</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 text-sm font-medium">
                            <Image className="h-4 w-4 text-purple-600" />
                            {contestant.images_count}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 text-sm font-medium">
                            <Video className="h-4 w-4 text-red-600" />
                            {contestant.videos_count}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 text-sm font-medium">
                            <ThumbsUp className="h-4 w-4 text-green-600" />
                            {contestant.votes_count}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 text-sm font-medium">
                            <MessageCircle className="h-4 w-4 text-blue-600" />
                            {contestant.comments_count || 0}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                          {new Date(contestant.registration_date).toLocaleDateString('fr-FR')}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex gap-2 flex-wrap">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleEdit(contestant)}
                              className="gap-1"
                              disabled={isSubmitting}
                            >
                              <Edit2 className="h-4 w-4" />
                              {t('common.edit') || 'Modifier'}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setUploadingContestantId(contestant.id)
                                setShowUploadDialog(true)
                              }}
                              className="gap-1"
                              title="Uploader des fichiers"
                            >
                              <Upload className="h-4 w-4" />
                              Upload
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={async () => {
                                setSelectedContestant(contestant)
                                setShowDialog(true)
                                setSelectedMedia(null)
                                setShowMediaViewer(false)
                                // Charger les commentaires séparément
                                if (contestant.id) {
                                  await loadContestantComments(contestant.id)
                                }
                              }}
                              className="gap-1"
                            >
                              <Eye className="h-4 w-4" />
                              {t('admin.contestants.view') || 'Voir'}
                            </Button>
                            {contestant.verification_status === 'pending' && (
                              <>
                                <Button
                                  size="sm"
                                  className="gap-1 bg-green-600 hover:bg-green-700 disabled:opacity-50"
                                  onClick={() => handleApprove(contestant.id)}
                                  disabled={loadingContestantId === contestant.id}
                                >
                                  {loadingContestantId === contestant.id && loadingAction === 'approve' ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <CheckCircle2 className="h-4 w-4" />
                                  )}
                                  {t('admin.contestants.approve') || 'Approuver'}
                                </Button>
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  className="gap-1 disabled:opacity-50"
                                  onClick={() => handleReject(contestant.id)}
                                  disabled={loadingContestantId === contestant.id}
                                >
                                  {loadingContestantId === contestant.id && loadingAction === 'reject' ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <XCircle className="h-4 w-4" />
                                  )}
                                  {t('admin.contestants.reject') || 'Rejeter'}
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Dialog pour voir les détails */}
      {showDialog && selectedContestant && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto">
          <Card className="w-full max-w-3xl dark:bg-gray-800 my-8">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b dark:border-gray-700">
              <CardTitle>{t('admin.contestants.contestant_details') || 'Détails du candidat'}</CardTitle>
              <button
                onClick={() => setShowDialog(false)}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                <X className="h-5 w-5" />
              </button>
            </CardHeader>
            <CardContent className="pt-6 space-y-4">
              <div className="flex items-center gap-4">
                {selectedContestant.author_avatar_url && (
                  <img
                    src={selectedContestant.author_avatar_url}
                    alt={selectedContestant.author_name}
                    className="h-16 w-16 rounded-full object-cover"
                  />
                )}
                <div>
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white">{selectedContestant.title || 'Sans titre'}</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{t('admin.contestants.author') || 'Auteur'}: {selectedContestant.author_name}</p>
                </div>
              </div>

              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                <p className="text-sm text-gray-600 dark:text-gray-400">{selectedContestant.description}</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-2">{t('admin.contestants.status') || 'Statut'}</p>
                  <select
                    value={selectedContestant.verification_status}
                    onChange={(e) => {
                      const newStatus = e.target.value
                      if (newStatus !== selectedContestant.verification_status) {
                        handleStatusChange(selectedContestant.id, newStatus)
                      }
                    }}
                    disabled={loadingContestantId === selectedContestant.id}
                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:opacity-50"
                  >
                    <option value="pending">{t('admin.contestants.status_pending') || 'En attente'}</option>
                    <option value="verified">{t('admin.contestants.status_verified') || 'Vérifié'}</option>
                    <option value="rejected">{t('admin.contestants.status_rejected') || 'Rejeté'}</option>
                  </select>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{t('admin.contestants.registration_date') || 'Date d\'inscription'}</p>
                  <p className="text-sm text-gray-900 dark:text-white">{new Date(selectedContestant.registration_date).toLocaleDateString('fr-FR')}</p>
                </div>
              </div>

              {/* Statistics */}
              <div className="grid grid-cols-4 gap-4">
                <div className="text-center p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                  <Image className="h-5 w-5 text-purple-600 mx-auto mb-1" />
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{selectedContestant.images_count}</p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">{t('admin.contestants.images') || 'Images'}</p>
                </div>
                <div className="text-center p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                  <Video className="h-5 w-5 text-red-600 mx-auto mb-1" />
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{selectedContestant.videos_count}</p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">{t('admin.contestants.videos') || 'Vidéos'}</p>
                </div>
                <div className="text-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <ThumbsUp className="h-5 w-5 text-green-600 mx-auto mb-1" />
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{selectedContestant.votes_count}</p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">{t('admin.contestants.votes') || 'Votes'}</p>
                </div>
                <div className="text-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <MessageCircle className="h-5 w-5 text-blue-600 mx-auto mb-1" />
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{selectedContestant.comments_count || 0}</p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">{t('admin.contestants.comments') || 'Commentaires'}</p>
                </div>
              </div>

              {/* Media Gallery */}
              {selectedContestant.media_items && selectedContestant.media_items.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">📸 Médias ({selectedContestant.media_items.length})</h4>
                  <div className="grid grid-cols-4 gap-3">
                    {selectedContestant.media_items.map((media) => (
                      <button
                        key={media.id}
                        onClick={() => {
                          setSelectedMedia(media)
                          setShowMediaViewer(true)
                        }}
                        className="group relative overflow-hidden rounded-lg bg-gray-200 dark:bg-gray-700 aspect-square hover:ring-2 hover:ring-myfav-primary transition-all"
                      >
                        {media.type === 'image' ? (
                          <img
                            src={media.url}
                            alt="Image"
                            className="w-full h-full object-cover group-hover:scale-110 transition-transform"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center bg-gray-300 dark:bg-gray-600">
                            <Video className="h-6 w-6 text-gray-600 dark:text-gray-300" />
                          </div>
                        )}
                        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                          <Eye className="h-6 w-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Comments Section */}
              {loadingComments && (
                <div className="bg-gray-50 dark:bg-gray-700/30 rounded-lg p-4">
                  <p className="text-sm text-gray-500 dark:text-gray-400">Chargement des commentaires...</p>
                </div>
              )}
              {!loadingComments && selectedContestant.comments && selectedContestant.comments.length > 0 && (
                <div className="bg-gray-50 dark:bg-gray-700/30 rounded-lg p-4">
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">💬 Commentaires ({selectedContestant.comments.length})</h4>
                  <div className="space-y-3 max-h-48 overflow-y-auto">
                    {selectedContestant.comments.map((comment) => (
                      <div key={comment.id} className={`rounded-lg p-3 border ${comment.is_hidden ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-700' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'}`}>
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <p className="text-sm font-semibold text-gray-900 dark:text-white">{comment.author_name}</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              {new Date(comment.created_at).toLocaleDateString('fr-FR')}
                              {comment.is_hidden && ' • Caché'}
                            </p>
                          </div>
                          <div className="flex gap-2">
                            {comment.is_hidden ? (
                              <button
                                onClick={() => handleShowComment(comment.id)}
                                className="p-1 text-gray-500 hover:text-green-600 dark:hover:text-green-400 transition-colors"
                                title="Afficher le commentaire"
                              >
                                <Eye className="h-4 w-4" />
                              </button>
                            ) : (
                              <button
                                onClick={() => handleHideComment(comment.id)}
                                className="p-1 text-gray-500 hover:text-yellow-600 dark:hover:text-yellow-400 transition-colors"
                                title="Cacher le commentaire"
                              >
                                <EyeOff className="h-4 w-4" />
                              </button>
                            )}
                            <button
                              onClick={() => handleDeleteComment(comment.id)}
                              className="p-1 text-gray-500 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                              title="Supprimer le commentaire"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                        <p className="text-sm text-gray-600 dark:text-gray-300">{comment.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-3 pt-4 border-t dark:border-gray-700">
                <Button
                  variant="outline"
                  onClick={() => setShowDialog(false)}
                  className="flex-1"
                >
                  {t('admin.contestants.close') || 'Fermer'}
                </Button>
                {selectedContestant.verification_status === 'pending' && (
                  <>
                    <Button
                      className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50"
                      onClick={() => {
                        handleApprove(selectedContestant.id)
                        setShowDialog(false)
                      }}
                      disabled={loadingContestantId === selectedContestant.id}
                    >
                      {loadingContestantId === selectedContestant.id && loadingAction === 'approve' ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 mr-2" />
                      )}
                      {t('admin.contestants.approve') || 'Approuver'}
                    </Button>
                    <Button
                      variant="destructive"
                      className="flex-1 disabled:opacity-50"
                      onClick={() => {
                        handleReject(selectedContestant.id)
                        setShowDialog(false)
                      }}
                      disabled={loadingContestantId === selectedContestant.id}
                    >
                      {loadingContestantId === selectedContestant.id && loadingAction === 'reject' ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <XCircle className="h-4 w-4 mr-2" />
                      )}
                      {t('admin.contestants.reject') || 'Rejeter'}
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Media Viewer Modal */}
      {showMediaViewer && selectedMedia && selectedContestant?.media_items && (
        <MediaViewerModal
          media={selectedMedia}
          allMedia={selectedContestant.media_items}
          onClose={() => {
            setShowMediaViewer(false)
            setSelectedMedia(null)
          }}
          onMediaChange={setSelectedMedia}
        />
      )}

      {/* Upload Dialog */}
      {showUploadDialog && uploadingContestantId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-md dark:bg-gray-800">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b dark:border-gray-700">
              <CardTitle>Uploader des fichiers</CardTitle>
              <button
                onClick={() => {
                  setShowUploadDialog(false)
                  setUploadingContestantId(null)
                }}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                <X className="h-5 w-5" />
              </button>
            </CardHeader>
            <CardContent className="pt-6 space-y-4">
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white mb-3">Images</p>
                <UploadButton
                  endpoint="profileImageUploader"
                  onClientUploadComplete={(res) => {
                    if (res && res.length > 0) {
                      console.log('Image uploaded:', res[0].url)
                      // Refresh contestants data
                      fetchContestants()
                      setShowUploadDialog(false)
                      setUploadingContestantId(null)
                    }
                  }}
                  onUploadError={(error) => {
                    console.error('Upload error:', error)
                  }}
                />
              </div>

              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white mb-3">Vidéos</p>
                <UploadButton
                  endpoint="profileImageUploader"
                  onClientUploadComplete={(res) => {
                    if (res && res.length > 0) {
                      console.log('Video uploaded:', res[0].url)
                      // Refresh contestants data
                      fetchContestants()
                      setShowUploadDialog(false)
                      setUploadingContestantId(null)
                    }
                  }}
                  onUploadError={(error) => {
                    console.error('Upload error:', error)
                  }}
                />
              </div>

              <Button
                variant="outline"
                onClick={() => {
                  setShowUploadDialog(false)
                  setUploadingContestantId(null)
                }}
                className="w-full"
              >
                Fermer
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
