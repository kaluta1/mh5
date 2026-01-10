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
import { Plus, Edit2, Trash2, Eye, Calendar, Users, Clock, Zap, X, Trophy, MapPin, CheckCircle2, AlertCircle, Upload, Vote, ShieldCheck, Mic, FileCheck, PawPrint, Users2, Music, Award, Settings, Globe } from 'lucide-react'
import { UploadButton } from '@/components/ui/upload-button'
import { contestService, type ContestResponse } from '@/lib/services/contest-service'
import api from '@/lib/api'
import { cacheService } from '@/lib/cache-service'

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
  // Season dates
  city_season_start_date?: string
  city_season_end_date?: string
  country_season_start_date?: string
  country_season_end_date?: string
  regional_start_date?: string
  regional_end_date?: string
  continental_start_date?: string
  continental_end_date?: string
  global_start_date?: string
  global_end_date?: string
  // Verification requirements
  requires_kyc?: boolean
  verification_type?: string
  participant_type?: string
  requires_visual_verification?: boolean
  requires_voice_verification?: boolean
  requires_brand_verification?: boolean
  requires_content_verification?: boolean
  min_age?: number | null
  max_age?: number | null
  // Media requirements
  requires_video?: boolean
  max_videos?: number
  video_max_duration?: number
  video_max_size_mb?: number
  min_images?: number
  max_images?: number
  verification_video_max_duration?: number
  verification_max_size_mb?: number
  voting_type_id?: number | null
  voting_type?: {
    id: number
    name: string
    voting_level: string
    commission_source: string
    commission_rules?: any
  }
  category_id?: number | null
  category?: {
    id: number
    name: string
    slug: string
  }
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
    participant_count: 0,
    // Season dates
    city_season_start_date: '',
    city_season_end_date: '',
    country_season_start_date: '',
    country_season_end_date: '',
    regional_start_date: '',
    regional_end_date: '',
    continental_start_date: '',
    continental_end_date: '',
    global_start_date: '',
    global_end_date: '',
    // Verification requirements
    requires_kyc: false,
    verification_type: 'none',
    participant_type: 'individual',
    requires_visual_verification: false,
    requires_voice_verification: false,
    requires_brand_verification: false,
    requires_content_verification: false,
    min_age: null as number | null,
    max_age: null as number | null,
    // Media requirements
    requires_video: false,
    max_videos: 1,
    video_max_duration: 3000, // 50 minutes
    video_max_size_mb: 500,
    min_images: 0,
    max_images: 10,
    verification_video_max_duration: 30, // 30 seconds
    verification_max_size_mb: 50,
    voting_type_id: null as number | null,
    category_id: null as number | null
  })
  const [uploadedImage, setUploadedImage] = useState<string>('')
  const [seasons, setSeasons] = useState<Array<{ id: number; title: string; level: string }>>([])
  const [loadingSeasons, setLoadingSeasons] = useState(false)
  const [votingTypes, setVotingTypes] = useState<Array<{ id: number; name: string; voting_level: string; commission_source: string; commission_rules?: any }>>([])
  const [loadingVotingTypes, setLoadingVotingTypes] = useState(false)
  const [categories, setCategories] = useState<Array<{ id: number; name: string; slug: string; description?: string; is_active: boolean }>>([])
  const [loadingCategories, setLoadingCategories] = useState(false)
  const [showCategoryForm, setShowCategoryForm] = useState(false)
  const [categoryFormData, setCategoryFormData] = useState({
    name: '',
    slug: '',
    description: '',
    is_active: true
  })
  const [isCreatingCategory, setIsCreatingCategory] = useState(false)
  const [showVotingTypeForm, setShowVotingTypeForm] = useState(false)
  const [votingTypeFormData, setVotingTypeFormData] = useState({
    name: '',
    voting_level: 'city' as 'city' | 'country' | 'regional' | 'continent' | 'global',
    commission_source: 'advert' as 'advert' | 'affiliate' | 'kyc' | 'MFM',
    commission_rules: {} as Record<string, any>
  })
  const [isCreatingVotingType, setIsCreatingVotingType] = useState(false)

  useEffect(() => {
    fetchContests()
    fetchSeasons()
    fetchVotingTypes()
    fetchCategories()
  }, [])

  const fetchSeasons = async () => {
    try {
      setLoadingSeasons(true)
      const endpoint = '/api/v1/admin/seasons'
      const params = {}
      
      // Vérifier le cache
      const cachedData = cacheService.get<Array<{ id: number; title: string; level: string }>>(endpoint, params)
      if (cachedData) {
        setSeasons(cachedData)
        setLoadingSeasons(false)
        return
      }
      
      // Si pas de cache, faire l'appel API
      const response = await api.get(endpoint)
      const data = response.data
      setSeasons(data)
      
      // Mettre en cache (TTL de 5 minutes)
      cacheService.set(endpoint, data, params, 5 * 60 * 1000)
    } catch (error) {
      console.error('Erreur lors du chargement des saisons:', error)
    } finally {
      setLoadingSeasons(false)
    }
  }

  const fetchVotingTypes = async () => {
    try {
      setLoadingVotingTypes(true)
      const response = await api.get('/api/v1/voting-types')
      if (response.data && Array.isArray(response.data)) {
        setVotingTypes(response.data)
      } else {
        console.warn('Réponse inattendue pour voting-types:', response.data)
        setVotingTypes([])
      }
    } catch (error: any) {
      console.error('Erreur lors du chargement des types de vote:', error)
      console.error('URL appelée:', error.config?.url || '/api/v1/voting-types')
      console.error('Status:', error.response?.status)
      console.error('Response data:', error.response?.data)
      // Ne pas afficher d'erreur si c'est juste que l'endpoint n'existe pas encore
      if (error.response?.status !== 404) {
        addToast(t('admin.contests.voting_types_load_error') || 'Erreur lors du chargement des types de vote', 'error')
      }
      setVotingTypes([])
    } finally {
      setLoadingVotingTypes(false)
    }
  }

  const fetchCategories = async () => {
    try {
      setLoadingCategories(true)
      const endpoint = '/api/v1/categories'
      const params = { active_only: true }
      
      // Vérifier le cache
      const cachedData = cacheService.get<Array<{ id: number; name: string; slug: string; description?: string; is_active: boolean }>>(endpoint, params)
      if (cachedData) {
        setCategories(cachedData)
        setLoadingCategories(false)
        return
      }
      
      // Si pas de cache, faire l'appel API
      const response = await api.get(`${endpoint}/`, { params })
      const data = response.data && Array.isArray(response.data) ? response.data : []
      setCategories(data)
      
      // Mettre en cache (TTL de 5 minutes)
      cacheService.set(endpoint, data, params, 5 * 60 * 1000)
    } catch (error: any) {
      console.error('Erreur lors du chargement des catégories:', error)
      addToast(t('admin.contests.categories_load_error') || 'Erreur lors du chargement des catégories', 'error')
      setCategories([])
    } finally {
      setLoadingCategories(false)
    }
  }

  const handleCreateCategory = async () => {
    if (!categoryFormData.name.trim()) {
      addToast(t('admin.contests.category_name_required') || 'Le nom de la catégorie est requis', 'error')
      return
    }
    
    setIsCreatingCategory(true)
    try {
      // Générer le slug à partir du nom si non fourni
      const slug = categoryFormData.slug.trim() || categoryFormData.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
      
      const response = await api.post('/api/v1/categories/', {
        name: categoryFormData.name.trim(),
        slug: slug,
        description: categoryFormData.description.trim() || null,
        is_active: categoryFormData.is_active
      })
      
      // Invalider le cache des catégories
      cacheService.invalidate('/api/v1/categories')
      
      addToast(t('admin.contests.category_created') || 'Catégorie créée avec succès', 'success')
      setCategories([...categories, response.data])
      setFormData({ ...formData, category_id: response.data.id })
      setShowCategoryForm(false)
      setCategoryFormData({
        name: '',
        slug: '',
        description: '',
        is_active: true
      })
    } catch (error: any) {
      console.error('Erreur lors de la création de la catégorie:', error)
      const errorMessage = error.response?.data?.detail || t('admin.contests.category_create_error') || 'Erreur lors de la création'
      addToast(errorMessage, 'error')
    } finally {
      setIsCreatingCategory(false)
    }
  }

  const handleCreateVotingType = async () => {
    setIsCreatingVotingType(true)
    try {
      // Préparer les données en nettoyant commission_rules (enlever les valeurs undefined)
      const commissionRules: Record<string, any> = {}
      if (votingTypeFormData.commission_rules.L1 !== undefined && votingTypeFormData.commission_rules.L1 !== null) {
        commissionRules.L1 = votingTypeFormData.commission_rules.L1
      }
      if (votingTypeFormData.commission_rules['L2-10'] !== undefined && votingTypeFormData.commission_rules['L2-10'] !== null) {
        commissionRules['L2-10'] = votingTypeFormData.commission_rules['L2-10']
      }
      
      const dataToSend = {
        name: votingTypeFormData.name.trim(),
        voting_level: votingTypeFormData.voting_level,
        commission_source: votingTypeFormData.commission_source,
        commission_rules: Object.keys(commissionRules).length > 0 ? commissionRules : undefined
      }
      
      console.log('Création de voting type avec les données:', dataToSend)
      console.log('URL complète:', `${api.defaults.baseURL}/api/v1/voting-types`)
      
      const response = await api.post('/api/v1/voting-types', dataToSend)
      addToast(t('admin.contests.voting_type_created') || 'Type de vote créé avec succès', 'success')
      setVotingTypes([...votingTypes, response.data])
      setFormData({ ...formData, voting_type_id: response.data.id })
      setShowVotingTypeForm(false)
      setVotingTypeFormData({
        name: '',
        voting_level: 'city',
        commission_source: 'advert',
        commission_rules: {}
      })
    } catch (error: any) {
      console.error('Erreur lors de la création du type de vote:', error)
      console.error('URL appelée:', error.config?.url || '/api/v1/voting-types')
      console.error('Status:', error.response?.status)
      console.error('Response data:', error.response?.data)
      console.error('Request data:', error.config?.data)
      
      let errorMessage = t('admin.contests.voting_type_create_error') || 'Erreur lors de la création'
      
      if (error.response) {
        // Erreur HTTP avec réponse
        if (error.response.status === 404) {
          errorMessage = 'Endpoint non trouvé. Veuillez redémarrer le serveur backend.'
        } else if (error.response.status === 401 || error.response.status === 403) {
          errorMessage = error.response.data?.detail || 'Permission insuffisante. Vous devez être administrateur.'
        } else {
          errorMessage = error.response.data?.detail || error.response.data?.message || errorMessage
        }
      } else if (error.request) {
        // Requête envoyée mais pas de réponse
        errorMessage = 'Aucune réponse du serveur. Vérifiez que le serveur backend est démarré.'
      } else {
        // Erreur lors de la configuration de la requête
        errorMessage = error.message || errorMessage
      }
      
      addToast(errorMessage, 'error')
    } finally {
      setIsCreatingVotingType(false)
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
      // Le contestService gère déjà le cache, donc on l'utilise directement
      const data = await contestService.getAllContests()
      console.log('Fetched contests data:', data)
      if (data && data.length > 0) {
        console.log('First contest from API:', data[0])
        console.log('First contest category_id:', (data[0] as any).category_id)
        console.log('First contest category:', (data[0] as any).category)
      }
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
      // Prepare data
      console.log('Form data category_id:', formData.category_id)
      const dataToSend: any = {
        name: formData.name,
        description: formData.description,
        contest_type: formData.contest_type,
        category_id: formData.category_id ?? null,  // S'assurer que category_id est toujours envoyé, même si null
        season_id: formData.season_id ? parseInt(formData.season_id) : null,
        is_active: formData.is_active,
        is_submission_open: formData.is_submission_open,
        is_voting_open: formData.is_voting_open,
        image_url: formData.image_url,
        voting_restriction: formData.voting_restriction,
        // Verification requirements
        requires_kyc: formData.requires_kyc,
        verification_type: formData.verification_type,
        participant_type: formData.participant_type,
        requires_visual_verification: formData.requires_visual_verification,
        requires_voice_verification: formData.requires_voice_verification,
        requires_brand_verification: formData.requires_brand_verification,
        requires_content_verification: formData.requires_content_verification,
        min_age: formData.min_age,
        max_age: formData.max_age,
        // Media requirements
        requires_video: formData.requires_video,
        max_videos: formData.max_videos,
        video_max_duration: formData.video_max_duration,
        video_max_size_mb: formData.video_max_size_mb,
        min_images: formData.min_images,
        max_images: formData.max_images,
        verification_video_max_duration: formData.verification_video_max_duration,
        verification_max_size_mb: formData.verification_max_size_mb,
        // Voting type
        voting_type_id: formData.voting_type_id || null
      }

      // Pour la création, inclure les dates principales (les dates de saisons seront calculées automatiquement)
      if (!editingId) {
        dataToSend.submission_start_date = formData.submission_start_date
        dataToSend.submission_end_date = formData.submission_end_date
        dataToSend.voting_start_date = formData.voting_start_date
        dataToSend.voting_end_date = formData.voting_end_date
      } else {
        // Pour l'édition, inclure toutes les dates si elles sont modifiées
        if (formData.submission_start_date) dataToSend.submission_start_date = formData.submission_start_date
        if (formData.submission_end_date) dataToSend.submission_end_date = formData.submission_end_date
        if (formData.voting_start_date) dataToSend.voting_start_date = formData.voting_start_date
        if (formData.voting_end_date) dataToSend.voting_end_date = formData.voting_end_date
        
        // Dates des saisons (si modifiées)
        if (formData.city_season_start_date) dataToSend.city_season_start_date = formData.city_season_start_date
        if (formData.city_season_end_date) dataToSend.city_season_end_date = formData.city_season_end_date
        if (formData.country_season_start_date) dataToSend.country_season_start_date = formData.country_season_start_date
        if (formData.country_season_end_date) dataToSend.country_season_end_date = formData.country_season_end_date
        if (formData.regional_start_date) dataToSend.regional_start_date = formData.regional_start_date
        if (formData.regional_end_date) dataToSend.regional_end_date = formData.regional_end_date
        if (formData.continental_start_date) dataToSend.continental_start_date = formData.continental_start_date
        if (formData.continental_end_date) dataToSend.continental_end_date = formData.continental_end_date
        if (formData.global_start_date) dataToSend.global_start_date = formData.global_start_date
        if (formData.global_end_date) dataToSend.global_end_date = formData.global_end_date
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
      participant_count: 0,
      // Season dates
      city_season_start_date: '',
      city_season_end_date: '',
      country_season_start_date: '',
      country_season_end_date: '',
      regional_start_date: '',
      regional_end_date: '',
      continental_start_date: '',
      continental_end_date: '',
      global_start_date: '',
      global_end_date: '',
      requires_kyc: false,
      verification_type: 'none',
      participant_type: 'individual',
      requires_visual_verification: false,
      requires_voice_verification: false,
      requires_brand_verification: false,
        requires_content_verification: false,
        min_age: null,
        max_age: null,
        // Media requirements
        requires_video: false,
        max_videos: 1,
        video_max_duration: 3000,
        video_max_size_mb: 500,
        min_images: 0,
        max_images: 10,
        verification_video_max_duration: 30,
        verification_max_size_mb: 50,
        voting_type_id: null,
        category_id: null
    })
    setUploadedImage('')
  }

  const handleEdit = (contest: Contest) => {
    // Helper function to format date for input field
    const formatDateForInput = (dateStr?: string) => {
      if (!dateStr) return ''
      // If date includes time, extract just the date part
      return dateStr.split('T')[0]
    }

    console.log('Editing contest:', contest)
    console.log('Contest category_id:', contest.category_id)

    setFormData({
      name: contest.name,
      description: contest.description || '',
      contest_type: contest.contest_type,
      category_id: contest.category_id || null,
      season_id: contest.season_id?.toString() || '',
      is_active: contest.is_active,
      is_submission_open: contest.is_submission_open,
      is_voting_open: contest.is_voting_open,
      submission_start_date: formatDateForInput(contest.submission_start_date),
      submission_end_date: formatDateForInput(contest.submission_end_date),
      voting_start_date: formatDateForInput(contest.voting_start_date),
      voting_end_date: formatDateForInput(contest.voting_end_date),
      image_url: contest.image_url || '',
      cover_image_url: contest.cover_image_url || '',
      voting_restriction: contest.voting_restriction || 'none',
      participant_count: contest.participant_count || 0,
      // Season dates
      city_season_start_date: formatDateForInput(contest.city_season_start_date),
      city_season_end_date: formatDateForInput(contest.city_season_end_date),
      country_season_start_date: formatDateForInput(contest.country_season_start_date),
      country_season_end_date: formatDateForInput(contest.country_season_end_date),
      regional_start_date: formatDateForInput(contest.regional_start_date),
      regional_end_date: formatDateForInput(contest.regional_end_date),
      continental_start_date: formatDateForInput(contest.continental_start_date),
      continental_end_date: formatDateForInput(contest.continental_end_date),
      global_start_date: formatDateForInput(contest.global_start_date),
      global_end_date: formatDateForInput(contest.global_end_date),
      requires_kyc: contest.requires_kyc ?? false,
      verification_type: contest.verification_type || 'none',
      participant_type: contest.participant_type || 'individual',
      requires_visual_verification: contest.requires_visual_verification ?? false,
      requires_voice_verification: contest.requires_voice_verification ?? false,
      requires_brand_verification: contest.requires_brand_verification ?? false,
      requires_content_verification: contest.requires_content_verification ?? false,
      min_age: contest.min_age ?? null,
      max_age: contest.max_age ?? null,
      // Media requirements
      requires_video: contest.requires_video ?? false,
      max_videos: contest.max_videos ?? 1,
      video_max_duration: contest.video_max_duration ?? 3000,
      video_max_size_mb: contest.video_max_size_mb ?? 500,
      min_images: contest.min_images ?? 0,
      max_images: contest.max_images ?? 10,
      verification_video_max_duration: contest.verification_video_max_duration ?? 30,
      verification_max_size_mb: contest.verification_max_size_mb ?? 50,
      voting_type_id: contest.voting_type_id ?? null
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
      city: t('admin.contests.level_city') || 'Ville',
      country: t('admin.contests.level_country') || 'Pays',
      region: t('admin.contests.level_region') || 'Région',
      continent: t('admin.contests.level_continent') || 'Continent',
      global: t('admin.contests.level_global') || 'Mondial'
    }
    return labels[level] || level
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex justify-between items-start gap-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-3">
              <Trophy className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
              <h1 className="text-4xl font-bold text-white dark:text-white">
                {t('admin.contests.title') || 'Gestion des Concours'}
              </h1>
            </div>
            <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium">
              {t('admin.contests.description') || 'Créez et gérez vos concours'}
            </p>
            <div className="flex gap-6 mt-4 text-sm">
              <div className="flex items-center gap-2 text-white dark:text-gray-300">
                <Users className="h-4 w-4" />
                <span>{contests.length} {t('admin.contests.contests_count') || 'concours'}</span>
              </div>
              <div className="flex items-center gap-2 text-white dark:text-gray-300">
                <CheckCircle2 className="h-4 w-4" />
                <span>{contests.filter(c => c.is_active).length} {t('admin.contests.active_count') || 'actifs'}</span>
              </div>
            </div>
          </div>
          <Button
            onClick={() => {
              setShowForm(true)
              setEditingId(null)
              resetForm()
            }}
            className="gap-2 bg-white text-myhigh5-primary hover:bg-gray-100 dark:bg-myhigh5-secondary dark:text-gray-900 dark:hover:bg-myhigh5-secondary/90 shadow-lg hover:shadow-xl transition-all font-semibold"
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
                      <img src={uploadedImage} alt="Preview" className="h-40 w-40 object-cover rounded-lg border-2 border-myhigh5-primary/20" />
                      {editingId && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">{t('admin.contests.current_image') || 'Image actuelle'}</p>
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

                {/* Dates principales */}
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
                  <h4 className="font-semibold text-sm text-blue-900 dark:text-blue-200 mb-4">📅 {t('admin.contests.contest_dates') || 'Dates du concours'}</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                        {t('admin.contests.submission_start') || 'Début des uploads'}
                      </label>
                      <Input
                        type="date"
                        value={formData.submission_start_date && formData.submission_start_date.includes('T') ? formData.submission_start_date.split('T')[0] : (formData.submission_start_date || '')}
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
                        value={formData.submission_end_date && formData.submission_end_date.includes('T') ? formData.submission_end_date.split('T')[0] : (formData.submission_end_date || '')}
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
                        value={formData.voting_start_date && formData.voting_start_date.includes('T') ? formData.voting_start_date.split('T')[0] : (formData.voting_start_date || '')}
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
                        value={formData.voting_end_date && formData.voting_end_date.includes('T') ? formData.voting_end_date.split('T')[0] : (formData.voting_end_date || '')}
                        onChange={(e) => setFormData({ ...formData, voting_end_date: e.target.value })}
                        className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      />
                    </div>
                  </div>
                  
                  {/* Dates des saisons - Affichées lors de l'édition */}
                  {editingId && (
                    <>
                      <div className="mt-6 pt-4 border-t border-blue-300 dark:border-blue-700">
                        <h5 className="font-semibold text-xs text-blue-900 dark:text-blue-200 mb-4 uppercase">
                          {t('admin.contests.season_dates') || 'Dates des saisons'}
                        </h5>
                        <div className="grid grid-cols-2 gap-4">
                          {/* City Season */}
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🏙️ {t('admin.contests.city_season') || 'Saison Ville'} - {t('admin.contests.start_date') || 'Début'}
                            </label>
                            <Input
                              type="date"
                              value={formData.city_season_start_date || ''}
                              onChange={(e) => setFormData({ ...formData, city_season_start_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🏙️ {t('admin.contests.city_season') || 'Saison Ville'} - {t('admin.contests.end_date') || 'Fin'}
                            </label>
                            <Input
                              type="date"
                              value={formData.city_season_end_date || ''}
                              onChange={(e) => setFormData({ ...formData, city_season_end_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          
                          {/* Country Season */}
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🌍 {t('admin.contests.country_season') || 'Saison Pays'} - {t('admin.contests.start_date') || 'Début'}
                            </label>
                            <Input
                              type="date"
                              value={formData.country_season_start_date || ''}
                              onChange={(e) => setFormData({ ...formData, country_season_start_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🌍 {t('admin.contests.country_season') || 'Saison Pays'} - {t('admin.contests.end_date') || 'Fin'}
                            </label>
                            <Input
                              type="date"
                              value={formData.country_season_end_date || ''}
                              onChange={(e) => setFormData({ ...formData, country_season_end_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          
                          {/* Regional Season */}
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🗺️ {t('admin.contests.regional_season') || 'Saison Régionale'} - {t('admin.contests.start_date') || 'Début'}
                            </label>
                            <Input
                              type="date"
                              value={formData.regional_start_date || ''}
                              onChange={(e) => setFormData({ ...formData, regional_start_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🗺️ {t('admin.contests.regional_season') || 'Saison Régionale'} - {t('admin.contests.end_date') || 'Fin'}
                            </label>
                            <Input
                              type="date"
                              value={formData.regional_end_date || ''}
                              onChange={(e) => setFormData({ ...formData, regional_end_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          
                          {/* Continental Season */}
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🌎 {t('admin.contests.continental_season') || 'Saison Continentale'} - {t('admin.contests.start_date') || 'Début'}
                            </label>
                            <Input
                              type="date"
                              value={formData.continental_start_date || ''}
                              onChange={(e) => setFormData({ ...formData, continental_start_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🌎 {t('admin.contests.continental_season') || 'Saison Continentale'} - {t('admin.contests.end_date') || 'Fin'}
                            </label>
                            <Input
                              type="date"
                              value={formData.continental_end_date || ''}
                              onChange={(e) => setFormData({ ...formData, continental_end_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          
                          {/* Global Season */}
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🌐 {t('admin.contests.global_season') || 'Saison Globale'} - {t('admin.contests.start_date') || 'Début'}
                            </label>
                            <Input
                              type="date"
                              value={formData.global_start_date || ''}
                              onChange={(e) => setFormData({ ...formData, global_start_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                              🌐 {t('admin.contests.global_season') || 'Saison Globale'} - {t('admin.contests.end_date') || 'Fin'}
                            </label>
                            <Input
                              type="date"
                              value={formData.global_end_date || ''}
                              onChange={(e) => setFormData({ ...formData, global_end_date: e.target.value })}
                              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </div>

                {/* Nom du concours */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.name')}
                  </label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder={t('admin.contests.name_placeholder') || 'Ex: Concours de beauté 2024'}
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
                    placeholder={t('admin.contests.description_placeholder') || 'Description du concours'}
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                </div>

                {/* Catégorie */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.category') || 'Catégorie'}
                  </label>
                  <div className="flex gap-2">
                    <Select
                      value={formData.category_id ? formData.category_id.toString() : "none"}
                      onValueChange={(value) => {
                        const categoryId = value && value !== 'none' ? parseInt(value) : null
                        const selectedCategory = categories.find(c => c.id === categoryId)
                        setFormData({ 
                          ...formData, 
                          category_id: categoryId,
                          contest_type: selectedCategory ? selectedCategory.slug : formData.contest_type
                        })
                      }}
                    >
                      <SelectTrigger className="flex-1 dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                        <SelectValue placeholder={t('admin.contests.select_category') || 'Sélectionner une catégorie'} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">{t('admin.contests.no_category') || 'Aucune catégorie'}</SelectItem>
                        {categories.filter(c => c.is_active).map((category) => (
                          <SelectItem key={category.id} value={category.id.toString()}>
                            {category.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      onClick={() => setShowCategoryForm(true)}
                      variant="outline"
                      className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                    >
                      <Plus className="w-4 h-4 mr-1" />
                      {t('admin.contests.add_category') || 'Ajouter'}
                    </Button>
                  </div>
                </div>

                {/* Type de concours (auto-rempli si catégorie sélectionnée) */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.contest_type')}
                  </label>
                  <Input
                    value={formData.contest_type}
                    onChange={(e) => setFormData({ ...formData, contest_type: e.target.value })}
                    placeholder={t('admin.contests.type_placeholder') || 'Ex: beauty, handsome (auto-rempli si catégorie sélectionnée)'}
                    required
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                    disabled={!!formData.category_id}
                  />
                  {formData.category_id && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {t('admin.contests.contest_type_auto_filled') || 'Le type de concours est automatiquement rempli à partir de la catégorie'}
                    </p>
                  )}
                </div>

                {/* Saison du concours */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.seasons.title') || 'Saison'} <span className="text-red-500">*</span>
                  </label>
                  {loadingSeasons ? (
                    <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-myhigh5-primary"></div>
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

                {/* Type de vote */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white flex items-center gap-2">
                    <Vote className="h-4 w-4" />
                    {t('admin.contests.voting_type') || 'Type de vote'} (optionnel)
                  </label>
                  {loadingVotingTypes ? (
                    <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-myhigh5-primary"></div>
                      {t('common.loading') || 'Chargement...'}
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <Select 
                        value={formData.voting_type_id?.toString() || 'none'} 
                        onValueChange={(value) => setFormData({ ...formData, voting_type_id: value === 'none' ? null : parseInt(value) })}
                      >
                        <SelectTrigger className="flex-1 dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                          <SelectValue placeholder={t('admin.contests.select_voting_type') || 'Sélectionner un type de vote'} />
                        </SelectTrigger>
                        <SelectContent className="dark:bg-gray-700">
                          <SelectItem value="none">{t('admin.contests.none') || 'Aucun'}</SelectItem>
                          {votingTypes.map((vt) => (
                            <SelectItem key={vt.id} value={vt.id.toString()}>
                              {vt.name} ({vt.voting_level} - {vt.commission_source})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => setShowVotingTypeForm(true)}
                        className="gap-2"
                      >
                        <Plus className="h-4 w-4" />
                        {t('admin.contests.new_voting_type') || 'Nouveau'}
                      </Button>
                    </div>
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

                {/* ============== VERIFICATION REQUIREMENTS ============== */}
                <div className="bg-amber-50 dark:bg-amber-900/20 rounded-xl p-5 border border-amber-200 dark:border-amber-800">
                  <h4 className="font-semibold text-sm text-amber-900 dark:text-amber-200 mb-4 flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4" />
                    {t('admin.contests.verification_requirements') || 'Exigences de vérification'}
                  </h4>
                  
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    {/* Type de participant */}
                    <div>
                      <label className="block text-xs font-medium text-amber-700 dark:text-amber-300 mb-2">
                        {t('admin.contests.participant_type') || 'Type de participant'}
                      </label>
                      <Select value={formData.participant_type} onValueChange={(value) => setFormData({ ...formData, participant_type: value })}>
                        <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="dark:bg-gray-700">
                          <SelectItem value="individual"><span className="flex items-center gap-2"><Users className="h-4 w-4" /> {t('admin.contests.participant_individual') || 'Personne'}</span></SelectItem>
                          <SelectItem value="pet"><span className="flex items-center gap-2"><PawPrint className="h-4 w-4" /> {t('admin.contests.participant_pet') || 'Animal'}</span></SelectItem>
                          <SelectItem value="club"><span className="flex items-center gap-2"><Users2 className="h-4 w-4" /> {t('admin.contests.participant_club') || 'Club'}</span></SelectItem>
                          <SelectItem value="content"><span className="flex items-center gap-2"><Music className="h-4 w-4" /> {t('admin.contests.participant_content') || 'Contenu'}</span></SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Type de vérification */}
                    <div>
                      <label className="block text-xs font-medium text-amber-700 dark:text-amber-300 mb-2">
                        {t('admin.contests.verification_type') || 'Type de vérification'}
                      </label>
                      <Select value={formData.verification_type} onValueChange={(value) => setFormData({ ...formData, verification_type: value })}>
                        <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="dark:bg-gray-700">
                          <SelectItem value="none">{t('admin.contests.verification_none') || 'Aucune'}</SelectItem>
                          <SelectItem value="visual"><span className="flex items-center gap-2"><Eye className="h-4 w-4" /> {t('admin.contests.verification_visual') || 'Visuelle'}</span></SelectItem>
                          <SelectItem value="voice"><span className="flex items-center gap-2"><Mic className="h-4 w-4" /> {t('admin.contests.verification_voice') || 'Vocale'}</span></SelectItem>
                          <SelectItem value="brand"><span className="flex items-center gap-2"><Trophy className="h-4 w-4" /> {t('admin.contests.verification_brand') || 'Marque'}</span></SelectItem>
                          <SelectItem value="content"><span className="flex items-center gap-2"><FileCheck className="h-4 w-4" /> {t('admin.contests.verification_content') || 'Contenu'}</span></SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* Restrictions d'âge */}
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <div>
                      <label className="block text-xs font-medium text-amber-700 dark:text-amber-300 mb-2 flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {t('admin.contests.min_age') || 'Âge minimum'}
                      </label>
                      <Input
                        type="number"
                        value={formData.min_age ?? ''}
                        onChange={(e) => setFormData({ ...formData, min_age: e.target.value ? parseInt(e.target.value) : null })}
                        placeholder={t('admin.contests.min_age_placeholder') || 'Ex: 18'}
                        min="0"
                        max="120"
                        className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-amber-700 dark:text-amber-300 mb-2 flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {t('admin.contests.max_age') || 'Âge maximum'}
                      </label>
                      <Input
                        type="number"
                        value={formData.max_age ?? ''}
                        onChange={(e) => setFormData({ ...formData, max_age: e.target.value ? parseInt(e.target.value) : null })}
                        placeholder={t('admin.contests.max_age_placeholder') || 'Ex: 35'}
                        min="0"
                        max="120"
                        className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      />
                    </div>
                  </div>

                  {/* Checkboxes de vérification */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="flex items-center gap-2 p-2 rounded-lg bg-white/50 dark:bg-gray-800/50">
                      <input
                        type="checkbox"
                        id="requires_kyc"
                        checked={formData.requires_kyc}
                        onChange={(e) => setFormData({ ...formData, requires_kyc: e.target.checked })}
                        className="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                      />
                      <label htmlFor="requires_kyc" className="text-xs font-medium cursor-pointer text-amber-800 dark:text-amber-200 flex items-center gap-1.5">
                        <ShieldCheck className="h-3.5 w-3.5" />
                        {t('admin.contests.requires_kyc') || 'KYC obligatoire'}
                      </label>
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded-lg bg-white/50 dark:bg-gray-800/50">
                      <input
                        type="checkbox"
                        id="requires_visual_verification"
                        checked={formData.requires_visual_verification}
                        onChange={(e) => setFormData({ ...formData, requires_visual_verification: e.target.checked })}
                        className="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                      />
                      <label htmlFor="requires_visual_verification" className="text-xs font-medium cursor-pointer text-amber-800 dark:text-amber-200 flex items-center gap-1.5">
                        <Eye className="h-3.5 w-3.5" />
                        {t('admin.contests.requires_visual') || 'Vérif. visuelle'}
                      </label>
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded-lg bg-white/50 dark:bg-gray-800/50">
                      <input
                        type="checkbox"
                        id="requires_voice_verification"
                        checked={formData.requires_voice_verification}
                        onChange={(e) => setFormData({ ...formData, requires_voice_verification: e.target.checked })}
                        className="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                      />
                      <label htmlFor="requires_voice_verification" className="text-xs font-medium cursor-pointer text-amber-800 dark:text-amber-200 flex items-center gap-1.5">
                        <Mic className="h-3.5 w-3.5" />
                        {t('admin.contests.requires_voice') || 'Vérif. vocale'}
                      </label>
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded-lg bg-white/50 dark:bg-gray-800/50">
                      <input
                        type="checkbox"
                        id="requires_brand_verification"
                        checked={formData.requires_brand_verification}
                        onChange={(e) => setFormData({ ...formData, requires_brand_verification: e.target.checked })}
                        className="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                      />
                      <label htmlFor="requires_brand_verification" className="text-xs font-medium cursor-pointer text-amber-800 dark:text-amber-200 flex items-center gap-1.5">
                        <Trophy className="h-3.5 w-3.5" />
                        {t('admin.contests.requires_brand') || 'Vérif. marque'}
                      </label>
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded-lg bg-white/50 dark:bg-gray-800/50 col-span-2">
                      <input
                        type="checkbox"
                        id="requires_content_verification"
                        checked={formData.requires_content_verification}
                        onChange={(e) => setFormData({ ...formData, requires_content_verification: e.target.checked })}
                        className="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                      />
                      <label htmlFor="requires_content_verification" className="text-xs font-medium cursor-pointer text-amber-800 dark:text-amber-200 flex items-center gap-1.5">
                        <FileCheck className="h-3.5 w-3.5" />
                        {t('admin.contests.requires_content') || 'Vérif. propriété du contenu'}
                      </label>
                    </div>
                  </div>
                </div>

                {/* Media Requirements Section */}
                <div className="p-4 rounded-xl bg-gradient-to-br from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 border border-purple-200 dark:border-purple-800">
                  <h4 className="text-sm font-semibold text-purple-900 dark:text-purple-200 mb-4 flex items-center gap-2">
                    <Upload className="h-4 w-4" />
                    {t('admin.contests.media_requirements') || 'Exigences Média'}
                  </h4>
                  
                  {/* Video requirement checkbox */}
                  <div className="flex items-center gap-2 p-2 rounded-lg bg-white/50 dark:bg-gray-800/50 mb-4">
                    <input
                      type="checkbox"
                      id="requires_video"
                      checked={formData.requires_video}
                      onChange={(e) => setFormData({ ...formData, requires_video: e.target.checked })}
                      className="rounded border-purple-300 text-purple-600 focus:ring-purple-500"
                    />
                    <label htmlFor="requires_video" className="text-xs font-medium cursor-pointer text-purple-800 dark:text-purple-200 flex items-center gap-1.5">
                      <Zap className="h-3.5 w-3.5" />
                      {t('admin.contests.requires_video') || 'Vidéo obligatoire'}
                    </label>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3">
                    {/* Max videos */}
                    <div>
                      <label className="block text-xs font-medium text-purple-700 dark:text-purple-300 mb-1">
                        {t('admin.contests.max_videos') || 'Vidéos max'}
                      </label>
                      <Input
                        type="number"
                        value={formData.max_videos}
                        onChange={(e) => setFormData({ ...formData, max_videos: parseInt(e.target.value) || 1 })}
                        min="1"
                        max="10"
                        className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      />
                    </div>
                    
                    {/* Video max duration */}
                    <div>
                      <label className="block text-xs font-medium text-purple-700 dark:text-purple-300 mb-1">
                        {t('admin.contests.video_duration') || 'Durée max (min)'}
                      </label>
                      <Input
                        type="number"
                        value={Math.round(formData.video_max_duration / 60)}
                        onChange={(e) => setFormData({ ...formData, video_max_duration: (parseInt(e.target.value) || 50) * 60 })}
                        min="1"
                        max="60"
                        className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      />
                    </div>
                    
                    {/* Min images */}
                    <div>
                      <label className="block text-xs font-medium text-purple-700 dark:text-purple-300 mb-1">
                        {t('admin.contests.min_images') || 'Images min'}
                      </label>
                      <Input
                        type="number"
                        value={formData.min_images}
                        onChange={(e) => setFormData({ ...formData, min_images: parseInt(e.target.value) || 0 })}
                        min="0"
                        max="10"
                        className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      />
                    </div>
                    
                    {/* Max images */}
                    <div>
                      <label className="block text-xs font-medium text-purple-700 dark:text-purple-300 mb-1">
                        {t('admin.contests.max_images') || 'Images max'}
                      </label>
                      <Input
                        type="number"
                        value={formData.max_images}
                        onChange={(e) => setFormData({ ...formData, max_images: parseInt(e.target.value) || 10 })}
                        min="1"
                        max="20"
                        className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      />
                    </div>
                  </div>
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
                    <strong>ℹ️ {t('admin.contests.auto_dates_title') || 'Dates automatiques'} :</strong> {t('admin.contests.auto_dates_description') || 'Les dates sont générées automatiquement'} :
                  </p>
                  <ul className="text-sm text-blue-900 dark:text-blue-200 mt-2 ml-4 list-disc">
                    <li>{t('admin.contests.auto_date_upload_start') || 'Début des uploads : date de création'}</li>
                    <li>{t('admin.contests.auto_date_upload_end') || 'Fin des uploads : 1 mois après le début'}</li>
                    <li>{t('admin.contests.auto_date_vote_start') || 'Début du vote : 1 jour après la fin des uploads'}</li>
                    <li>{t('admin.contests.auto_date_vote_end') || 'Fin du vote : 1 mois après le début du vote'}</li>
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
                    className="bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary hover:shadow-lg disabled:opacity-70 disabled:cursor-not-allowed"
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

      {/* Category Form Modal */}
      {showCategoryForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-lg dark:bg-gray-800">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4 border-b dark:border-gray-700">
              <CardTitle className="text-xl font-bold text-gray-900 dark:text-white">
                {t('admin.contests.create_category') || 'Créer une catégorie'}
              </CardTitle>
              <button
                onClick={() => {
                  setShowCategoryForm(false)
                  setCategoryFormData({
                    name: '',
                    slug: '',
                    description: '',
                    is_active: true
                  })
                }}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                <X className="h-5 w-5" />
              </button>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="space-y-4">
                {/* Nom */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.name') || 'Nom'} <span className="text-red-500">*</span>
                  </label>
                  <Input
                    value={categoryFormData.name}
                    onChange={(e) => {
                      const name = e.target.value
                      const slug = name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
                      setCategoryFormData({ ...categoryFormData, name, slug })
                    }}
                    placeholder={t('admin.contests.category_name_placeholder') || 'Ex: Pop, Rock, Hip hop'}
                    required
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                </div>

                {/* Slug */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.slug') || 'Slug'} <span className="text-red-500">*</span>
                  </label>
                  <Input
                    value={categoryFormData.slug}
                    onChange={(e) => setCategoryFormData({ ...categoryFormData, slug: e.target.value })}
                    placeholder={t('admin.contests.slug_placeholder') || 'Ex: pop, rock, hip-hop'}
                    required
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {t('admin.contests.slug_help') || 'Le slug est généré automatiquement à partir du nom. Vous pouvez le modifier si nécessaire.'}
                  </p>
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.description') || 'Description'}
                  </label>
                  <textarea
                    value={categoryFormData.description}
                    onChange={(e) => setCategoryFormData({ ...categoryFormData, description: e.target.value })}
                    placeholder={t('admin.contests.category_description_placeholder') || 'Description de la catégorie (optionnel)'}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
                  />
                </div>

                {/* Active */}
                <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-700">
                  <input
                    type="checkbox"
                    id="category_is_active"
                    checked={categoryFormData.is_active}
                    onChange={(e) => setCategoryFormData({ ...categoryFormData, is_active: e.target.checked })}
                    className="rounded"
                  />
                  <label htmlFor="category_is_active" className="text-sm font-medium cursor-pointer text-gray-900 dark:text-white">
                    {t('admin.contests.active') || 'Actif'}
                  </label>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3 justify-end pt-4 border-t dark:border-gray-700 mt-6">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowCategoryForm(false)
                    setCategoryFormData({
                      name: '',
                      slug: '',
                      description: '',
                      is_active: true
                    })
                  }}
                  disabled={isCreatingCategory}
                >
                  {t('admin.contests.cancel') || 'Annuler'}
                </Button>
                <Button
                  type="button"
                  onClick={handleCreateCategory}
                  disabled={isCreatingCategory || !categoryFormData.name || !categoryFormData.slug}
                  className="bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary hover:shadow-lg disabled:opacity-70"
                >
                  {isCreatingCategory ? (
                    <div className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      {t('admin.contests.creating') || 'Création...'}
                    </div>
                  ) : (
                    t('admin.contests.create') || 'Créer'
                  )}
                </Button>
              </div>
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
                <Eye className="h-4 w-4 text-myhigh5-primary" />
                {t('admin.contests.search_placeholder') || 'Rechercher'}
              </label>
              <Input
                type="text"
                placeholder={t('admin.contests.search_input_placeholder') || 'Nom, type, description...'}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="dark:bg-gray-700 dark:border-gray-600 dark:text-white border-gray-300 focus:border-myhigh5-primary focus:ring-myhigh5-primary"
              />
            </div>

            {/* Tri */}
            <div>
              <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <Clock className="h-4 w-4 text-myhigh5-primary" />
                {t('admin.contests.sort') || 'Trier par'}
              </label>
              <Select value={sortBy} onValueChange={(value: any) => setSortBy(value)}>
                <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white border-gray-300 focus:border-myhigh5-primary focus:ring-myhigh5-primary">
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
              {filteredContests.length} {filteredContests.length === 1 ? (t('admin.contests.result') || 'résultat') : (t('admin.contests.results') || 'résultats')} {t('admin.contests.found') || 'trouvé(s)'}
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
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
            <p className="text-gray-600 dark:text-gray-400 text-lg">{t('admin.contests.no_results_for') || 'Aucun résultat pour'} "{searchQuery}"</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-5">
          {filteredContests.map((contest) => (
            <Card key={contest.id} className="group overflow-hidden hover:shadow-2xl transition-all duration-500 dark:bg-gray-800/80 bg-white border-0 shadow-lg hover:scale-[1.01]">
              <CardContent className="p-0">
                <div className="flex flex-col md:flex-row">
                  {/* Image de couverture avec overlay */}
                  <div className="relative w-full md:w-48 h-48 md:h-auto flex-shrink-0 overflow-hidden">
                    {contest.cover_image_url || contest.image_url ? (
                      <img
                        src={contest.cover_image_url || contest.image_url}
                        alt={contest.name}
                        className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary-dark to-purple-600">
                        <Trophy className="h-12 w-12 text-white/80" />
                      </div>
                    )}
                    {/* Overlay avec statut */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
                    <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between">
                      <span className={`px-3 py-1 rounded-full text-xs font-bold shadow-lg ${contest.is_active ? 'bg-emerald-500 text-white' : 'bg-gray-500 text-white'}`}>
                        {contest.is_active ? t('admin.contests.active') || 'Actif' : t('admin.contests.inactive') || 'Inactif'}
                      </span>
                      <div className="flex gap-1">
                        {contest.is_submission_open && (
                          <span className="px-2 py-1 bg-purple-500 text-white rounded-full text-xs font-bold shadow-lg flex items-center gap-1">
                            <Upload className="h-3 w-3" />
                          </span>
                        )}
                        {contest.is_voting_open && (
                          <span className="px-2 py-1 bg-orange-500 text-white rounded-full text-xs font-bold shadow-lg flex items-center gap-1">
                            <Vote className="h-3 w-3" />
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Contenu principal */}
                  <div className="flex-1 p-5 flex flex-col">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-4 mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="px-2 py-0.5 bg-myhigh5-primary/10 text-myhigh5-primary dark:bg-myhigh5-primary/20 dark:text-myhigh5-secondary rounded text-xs font-bold uppercase tracking-wide">
                            {contest.contest_type}
                          </span>
                          <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded text-xs font-medium flex items-center gap-1">
                            <MapPin className="h-3 w-3" />
                            {getLevelLabel(contest.level)}
                          </span>
                        </div>
                        <h3 className="font-bold text-xl text-gray-900 dark:text-white leading-tight">{contest.name}</h3>
                        {contest.description && (
                          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 line-clamp-1">{contest.description}</p>
                        )}
                      </div>
                      
                      {/* Stats rapides */}
                      <div className="flex gap-3 text-center">
                        <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg px-3 py-2">
                          <div className="text-lg font-bold text-blue-600 dark:text-blue-400">{contest.participant_count || 0}</div>
                          <div className="text-xs text-blue-500 dark:text-blue-300">{t('admin.contests.participants') || 'Participants'}</div>
                        </div>
                        {(contest.approved_count || 0) > 0 && (
                          <div className="bg-green-50 dark:bg-green-900/30 rounded-lg px-3 py-2">
                            <div className="text-lg font-bold text-green-600 dark:text-green-400">{contest.approved_count}</div>
                            <div className="text-xs text-green-500 dark:text-green-300">{t('admin.contests.approved') || 'Approuvés'}</div>
                          </div>
                        )}
                        {(contest.pending_count || 0) > 0 && (
                          <div className="bg-amber-50 dark:bg-amber-900/30 rounded-lg px-3 py-2">
                            <div className="text-lg font-bold text-amber-600 dark:text-amber-400">{contest.pending_count}</div>
                            <div className="text-xs text-amber-500 dark:text-amber-300">{t('admin.contests.pending') || 'En attente'}</div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Badges de vérification */}
                    <div className="flex flex-wrap gap-2 mb-4 pb-4 border-b border-gray-100 dark:border-gray-700">
                      {/* Type de participant */}
                      {contest.participant_type && (
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold ${
                          contest.participant_type === 'individual' ? 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300' :
                          contest.participant_type === 'pet' ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300' :
                          contest.participant_type === 'club' ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300' :
                          'bg-pink-100 dark:bg-pink-900/40 text-pink-700 dark:text-pink-300'
                        }`}>
                          {contest.participant_type === 'individual' && <><Users className="h-3.5 w-3.5" /> {t('admin.contests.participant_individual') || 'Individuel'}</>}
                          {contest.participant_type === 'pet' && <><PawPrint className="h-3.5 w-3.5" /> {t('admin.contests.participant_pet') || 'Animal'}</>}
                          {contest.participant_type === 'club' && <><Users2 className="h-3.5 w-3.5" /> {t('admin.contests.participant_club') || 'Club'}</>}
                          {contest.participant_type === 'content' && <><Music className="h-3.5 w-3.5" /> {t('admin.contests.participant_content') || 'Contenu'}</>}
                        </span>
                      )}
                      
                      {/* KYC */}
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold ${
                        contest.requires_kyc 
                          ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300' 
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
                      }`} title={contest.requires_kyc ? t('admin.contests.kyc_required') || 'KYC requis' : t('admin.contests.kyc_not_required') || 'KYC non requis'}>
                        <ShieldCheck className="h-3.5 w-3.5" />
                        {contest.requires_kyc ? t('admin.contests.kyc_required') || 'KYC requis' : t('admin.contests.kyc_not_required') || 'Sans KYC'}
                      </span>
                      
                      {/* Vérifications spécifiques */}
                      {contest.requires_visual_verification && (
                        <span className="inline-flex items-center gap-1.5 bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 px-2.5 py-1 rounded-lg text-xs font-semibold" title={t('admin.contests.requires_visual') || 'Vérification visuelle requise'}>
                          <Eye className="h-3.5 w-3.5" /> {t('admin.contests.verification_visual') || 'Visuel'}
                        </span>
                      )}
                      {contest.requires_voice_verification && (
                        <span className="inline-flex items-center gap-1.5 bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300 px-2.5 py-1 rounded-lg text-xs font-semibold" title={t('admin.contests.requires_voice') || 'Vérification vocale requise'}>
                          <Mic className="h-3.5 w-3.5" /> {t('admin.contests.verification_voice') || 'Vocal'}
                        </span>
                      )}
                      {contest.requires_brand_verification && (
                        <span className="inline-flex items-center gap-1.5 bg-teal-100 dark:bg-teal-900/40 text-teal-700 dark:text-teal-300 px-2.5 py-1 rounded-lg text-xs font-semibold" title={t('admin.contests.requires_brand') || 'Vérification marque requise'}>
                          <Award className="h-3.5 w-3.5" /> {t('admin.contests.verification_brand') || 'Marque'}
                        </span>
                      )}
                      {contest.requires_content_verification && (
                        <span className="inline-flex items-center gap-1.5 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-2.5 py-1 rounded-lg text-xs font-semibold" title={t('admin.contests.requires_content') || 'Vérification de contenu requise'}>
                          <FileCheck className="h-3.5 w-3.5" /> {t('admin.contests.verification_content') || 'Contenu'}
                        </span>
                      )}
                      {(contest.min_age || contest.max_age) && (
                        <span className="inline-flex items-center gap-1.5 bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300 px-2.5 py-1 rounded-lg text-xs font-semibold" title={t('admin.contests.age_restricted') || 'Restriction d\'âge'}>
                          <Calendar className="h-3.5 w-3.5" />
                          {contest.min_age && contest.max_age ? `${contest.min_age}-${contest.max_age} ${t('admin.contests.years') || 'ans'}` : contest.min_age ? `${contest.min_age}+ ${t('admin.contests.years') || 'ans'}` : `<${contest.max_age} ${t('admin.contests.years') || 'ans'}`}
                        </span>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 mt-auto">
                      <Button
                        size="sm"
                        onClick={() => handleEdit(contest)}
                        className="gap-1.5 bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white shadow-md hover:shadow-lg transition-all"
                      >
                        <Edit2 className="h-4 w-4" />
                        {t('admin.contests.edit') || 'Modifier'}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => router.push(`/dashboard/admin/contests/${contest.id}/contestants`)}
                        className="gap-1.5 border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30"
                      >
                        <Users className="h-4 w-4" />
                        {t('admin.contests.candidates') || 'Candidats'}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDeleteClick(contest.id)}
                        className="gap-1.5 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 ml-auto"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
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

      {/* Modal de création de Voting Type */}
      {showVotingTypeForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-lg dark:bg-gray-800">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4 border-b dark:border-gray-700">
              <CardTitle className="text-xl flex items-center gap-2">
                <Settings className="h-5 w-5" />
                {t('admin.contests.create_voting_type') || 'Créer un type de vote'}
              </CardTitle>
              <button
                onClick={() => {
                  setShowVotingTypeForm(false)
                  setVotingTypeFormData({
                    name: '',
                    voting_level: 'city',
                    commission_source: 'advert',
                    commission_rules: {}
                  })
                }}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                <X className="h-5 w-5" />
              </button>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="space-y-4">
                {/* Nom */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.name') || 'Nom'} <span className="text-red-500">*</span>
                  </label>
                  <Input
                    value={votingTypeFormData.name}
                    onChange={(e) => setVotingTypeFormData({ ...votingTypeFormData, name: e.target.value })}
                    placeholder={t('admin.contests.voting_type_name_placeholder') || 'Ex: Vote City - Commission Advert'}
                    required
                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  />
                </div>

                {/* Niveau de vote */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.voting_level') || 'Niveau de vote'} <span className="text-red-500">*</span>
                  </label>
                  <Select 
                    value={votingTypeFormData.voting_level} 
                    onValueChange={(value: any) => setVotingTypeFormData({ ...votingTypeFormData, voting_level: value })}
                  >
                    <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-gray-700">
                      <SelectItem value="city"><span className="flex items-center gap-2"><MapPin className="h-4 w-4" /> {t('admin.contests.level_city') || 'Ville'}</span></SelectItem>
                      <SelectItem value="country"><span className="flex items-center gap-2"><Globe className="h-4 w-4" /> {t('admin.contests.level_country') || 'Pays'}</span></SelectItem>
                      <SelectItem value="regional">{t('admin.contests.level_region') || 'Régional'}</SelectItem>
                      <SelectItem value="continent">{t('admin.contests.level_continent') || 'Continent'}</SelectItem>
                      <SelectItem value="global">{t('admin.contests.level_global') || 'Global'}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Source de commission */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.commission_source') || 'Source de commission'} <span className="text-red-500">*</span>
                  </label>
                  <Select 
                    value={votingTypeFormData.commission_source} 
                    onValueChange={(value: any) => setVotingTypeFormData({ ...votingTypeFormData, commission_source: value })}
                  >
                    <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-gray-700">
                      <SelectItem value="advert">{t('admin.contests.commission_advert') || 'Publicité'}</SelectItem>
                      <SelectItem value="affiliate">{t('admin.contests.commission_affiliate') || 'Affiliation'}</SelectItem>
                      <SelectItem value="kyc">{t('admin.contests.commission_kyc') || 'KYC'}</SelectItem>
                      <SelectItem value="MFM">{t('admin.contests.commission_mfm') || 'MFM'}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Règles de commission (JSON) */}
                <div>
                  <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-white">
                    {t('admin.contests.commission_rules') || 'Règles de commission (JSON)'}
                  </label>
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">L1</label>
                        <Input
                          type="number"
                          placeholder="Ex: 10"
                          onChange={(e) => {
                            const value = e.target.value ? parseFloat(e.target.value) : undefined
                            setVotingTypeFormData({
                              ...votingTypeFormData,
                              commission_rules: { ...votingTypeFormData.commission_rules, L1: value }
                            })
                          }}
                          className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">L2-10</label>
                        <Input
                          type="number"
                          placeholder="Ex: 5"
                          onChange={(e) => {
                            const value = e.target.value ? parseFloat(e.target.value) : undefined
                            setVotingTypeFormData({
                              ...votingTypeFormData,
                              commission_rules: { ...votingTypeFormData.commission_rules, 'L2-10': value }
                            })
                          }}
                          className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                        />
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {t('admin.contests.commission_rules_help') || 'Les règles de commission sont optionnelles. Format: L1 pour le niveau 1, L2-10 pour les niveaux 2 à 10.'}
                    </p>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-3 justify-end pt-4 border-t dark:border-gray-700">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setShowVotingTypeForm(false)
                      setVotingTypeFormData({
                        name: '',
                        voting_level: 'city',
                        commission_source: 'advert',
                        commission_rules: {}
                      })
                    }}
                    disabled={isCreatingVotingType}
                  >
                    {t('admin.contests.cancel') || 'Annuler'}
                  </Button>
                  <Button
                    type="button"
                    onClick={handleCreateVotingType}
                    disabled={isCreatingVotingType || !votingTypeFormData.name}
                    className="bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary hover:shadow-lg disabled:opacity-70"
                  >
                    {isCreatingVotingType ? (
                      <div className="flex items-center gap-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        {t('admin.contests.creating') || 'Création...'}
                      </div>
                    ) : (
                      t('admin.contests.create') || 'Créer'
                    )}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
