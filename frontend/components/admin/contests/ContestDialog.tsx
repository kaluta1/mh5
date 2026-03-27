'use client'

import { useState, useEffect, useRef } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { X, ImagePlus, Loader2 } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { generateReactHelpers } from '@uploadthing/react'
import type { OurFileRouter } from '@/app/api/uploadthing/core'

const { useUploadThing } = generateReactHelpers<OurFileRouter>({ url: "/ut" })

interface ContestDialogProps {
    isOpen: boolean
    onClose: () => void
    onSave: (data: any) => Promise<void>
    initialData?: any
    seasons: any[]
      categories: any[]
  }

export function ContestDialog({
    isOpen,
    onClose,
    onSave,
    initialData,
    seasons,
    categories,
}: ContestDialogProps) {
    const { t } = useLanguage()
    const [activeTab, setActiveTab] = useState('general')
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        contest_type: '',
        season_id: '',
        is_active: true,
        image_url: '',
        cover_image_url: '',
        voting_restriction: 'none',
        participant_count: 0,

        requires_kyc: false,
        verification_type: 'none',
        participant_type: 'individual',
        requires_visual_verification: false,
        requires_voice_verification: false,
        requires_brand_verification: false,
        requires_content_verification: false,
        min_age: '',
        max_age: '',
        requires_video: false,
        max_videos: 1,
        video_max_duration: 3000,
        video_max_size_mb: 500,
        min_images: 0,
        max_images: 10,
        verification_video_max_duration: 30,
        verification_max_size_mb: 50,
        contest_mode: "participation",
        category_id: null
    })
    const [uploadedImage, setUploadedImage] = useState<string>('')
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [isUploading, setIsUploading] = useState(false)
    const [uploadError, setUploadError] = useState<string>('')
    const [errors, setErrors] = useState<Record<string, string>>({})
    const [accessToken, setAccessToken] = useState<string>('')
    const fileInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') || '' : ''
        setAccessToken(token)
    }, [])

    const { startUpload } = useUploadThing('imageUploader', {
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
        onClientUploadComplete: (res) => {
            if (res?.[0]) {
                const url = res[0].url
                setUploadedImage(url)
                setFormData(prev => ({ ...prev, image_url: url, cover_image_url: url }))
                setErrors(prev => ({ ...prev, image: '' }))
            }
            setIsUploading(false)
        },
        onUploadError: (error) => {
            setUploadError(error.message || 'Upload failed')
            setIsUploading(false)
        },
    })

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return
        setUploadError('')

        // Show instant local preview
        const reader = new FileReader()
        reader.onloadend = () => setUploadedImage(reader.result as string)
        reader.readAsDataURL(file)

        // Upload to UploadThing
        setIsUploading(true)
        await startUpload([file])
    }

    // Determine contest mode from initialData
    const contestMode = initialData?.type || 'participation'
    const isNomination = contestMode === 'nomination'
    const isEditing = initialData && !initialData.isNew

    useEffect(() => {
        if (initialData) {
            setFormData({
                name: initialData.name || '',
                description: initialData.description || '',
                contest_type: initialData.contest_type || '',
                category_id: initialData.category_id || null,
                season_id: initialData.season_id?.toString() || '',
                is_active: initialData.is_active ?? true,
                image_url: initialData.image_url || '',
                cover_image_url: initialData.cover_image_url || '',
                voting_restriction: initialData.voting_restriction || 'none',
                participant_count: initialData.participant_count || 0,

                requires_kyc: initialData.requires_kyc ?? false,
                verification_type: initialData.verification_type || 'none',
                participant_type: initialData.participant_type || 'individual',
                requires_visual_verification: initialData.requires_visual_verification ?? false,
                requires_voice_verification: initialData.requires_voice_verification ?? false,
                requires_brand_verification: initialData.requires_brand_verification ?? false,
                requires_content_verification: initialData.requires_content_verification ?? false,
                min_age: initialData.min_age?.toString() || '',
                max_age: initialData.max_age?.toString() || '',

                requires_video: initialData.requires_video ?? false,
                max_videos: initialData.max_videos ?? 1,
                video_max_duration: initialData.video_max_duration ?? 3000,
                video_max_size_mb: initialData.video_max_size_mb ?? 500,
                min_images: initialData.min_images ?? 0,
                max_images: initialData.max_images ?? 10,
                verification_video_max_duration: initialData.verification_video_max_duration ?? 30,
                verification_max_size_mb: initialData.verification_max_size_mb ?? 50,
                contest_mode: initialData.contest_mode || "participation"
            })
            if (initialData.cover_image_url || initialData.image_url) {
                setUploadedImage(initialData.cover_image_url || initialData.image_url || '')
            }
        } else {
            // Reset form
            setFormData({
                name: '',
                description: '',
                contest_type: '',
                season_id: '',
                is_active: true,
                image_url: '',
                cover_image_url: '',
                voting_restriction: 'none',
                participant_count: 0,
                requires_kyc: false,
                verification_type: 'none',
                participant_type: 'individual',
                requires_visual_verification: false,
                requires_voice_verification: false,
                requires_brand_verification: false,
                requires_content_verification: false,
                min_age: '',
                max_age: '',
                requires_video: false,
                max_videos: 1,
                video_max_duration: 3000,
                video_max_size_mb: 500,
                min_images: 0,
                max_images: 10,
                verification_video_max_duration: 30,
                verification_max_size_mb: 50,
                contest_mode: "participation",
                category_id: null
            })
            setUploadedImage('')
            setActiveTab('general')
        }
    }, [initialData])

    const validateForm = () => {
        const newErrors: Record<string, string> = {}

        if (!formData.name.trim()) {
            newErrors.name = t('admin.contests.error_name_required') || 'Le nom est obligatoire'
        }
        if (!formData.category_id) {
            newErrors.category_id = t('admin.contests.error_category_required') || 'La catégorie est obligatoire'
        }
        if (!formData.description.trim()) {
            newErrors.description = t('admin.contests.error_description_required') || 'La description est obligatoire'
        }
        if (!uploadedImage && !formData.image_url) {
            newErrors.image = t('admin.contests.error_image_required') || "L'image est obligatoire"
        }
        // Contest type is required for nomination contests
        if (false) { // contest_mode is always set
            newErrors.contest_mode = t('admin.contests.error_contest_type_required') || 'Le type de compétition est obligatoire pour les nominations'
        }

        console.log('Validation errors:', newErrors)
        setErrors(newErrors)

        const isValid = Object.keys(newErrors).length === 0
        console.log('Form is valid:', isValid)
        return isValid
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()

        if (!validateForm()) {
            return
        }

        setIsSubmitting(true)
        try {
            const dataToSave: any = { ...formData }

            // Clean up season_id
            if (dataToSave.season_id === '') {
                dataToSave.season_id = null
            } else {
                dataToSave.season_id = parseInt(dataToSave.season_id)
            }

            // Clean up numbers
            if (dataToSave.min_age === '') dataToSave.min_age = null
            else dataToSave.min_age = parseInt(dataToSave.min_age as string)

            if (dataToSave.max_age === '') dataToSave.max_age = null
            else dataToSave.max_age = parseInt(dataToSave.max_age as string)

            await onSave(dataToSave)
            onClose()
        } catch (error) {
            console.error(error)
        } finally {
            setIsSubmitting(false)
        }
    }

    if (!isOpen) return null

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto dark:bg-gray-800 flex flex-col">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4 border-b dark:border-gray-700 shrink-0">
                    <CardTitle className="text-xl">
                        {isEditing
                            ? t('admin.contests.edit_contest')
                            : isNomination
                                ? (t('admin.contests.create_nomination_contest') || 'Create a new (Nomination Contest)')
                                : (t('admin.contests.create_participation_contest') || 'Create a new (Participation Contest)')
                        }
                    </CardTitle>
                    <button
                        onClick={onClose}
                        className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </CardHeader>
                <CardContent className="pt-6 grow overflow-y-auto">
                    <form onSubmit={handleSubmit} className="space-y-6">

                        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                            <TabsList className="grid w-full grid-cols-3 mb-6">
                                <TabsTrigger value="general">{t('admin.contests.tab_contests') || 'Général'}</TabsTrigger>
                                <TabsTrigger value="requirements">{t('admin.contests.verification_requirements') || 'Requis'}</TabsTrigger>
                                <TabsTrigger value="media">{t('admin.contests.media_requirements') || 'Médias'}</TabsTrigger>
                            </TabsList>

                            <TabsContent value="general" className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                        {t('admin.contests.name') || 'Nom du concours'} <span className="text-red-500">*</span>
                                    </label>
                                    <Input
                                        value={formData.name}
                                        onChange={(e) => {
                                            setFormData({ ...formData, name: e.target.value })
                                            if (e.target.value.trim()) {
                                                setErrors(prev => ({ ...prev, name: '' }))
                                            }
                                        }}
                                        className={`dark:bg-gray-700 dark:border-gray-600 dark:text-white ${errors.name ? 'border-red-500' : ''}`}
                                    />
                                    {errors.name && <p className="text-red-500 text-xs mt-1">{errors.name}</p>}
                                </div>

                                <div className={isNomination ? 'grid grid-cols-2 gap-4' : ''}>
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.category') || 'Catégorie'} <span className="text-red-500">*</span>
                                        </label>
                                        <Select
                                            value={formData.category_id?.toString() || ''}
                                            onValueChange={(value) => {
                                                const category = categories.find(c => c.id.toString() === value)
                                                setFormData({
                                                    ...formData,
                                                    category_id: parseInt(value),
                                                    contest_type: category ? category.slug : formData.contest_type
                                                })
                                                setErrors(prev => ({ ...prev, category_id: '' }))
                                            }}
                                        >
                                            <SelectTrigger className={`dark:bg-gray-700 dark:border-gray-600 dark:text-white ${errors.category_id ? 'border-red-500' : ''}`}>
                                                <SelectValue placeholder={t('admin.contests.select_category') || 'Sélectionner une catégorie'} />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {categories.map((category) => (
                                                    <SelectItem key={category.id} value={category.id.toString()}>
                                                        {category.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                        {errors.category_id && <p className="text-red-500 text-xs mt-1">{errors.category_id}</p>}
                                    </div>
                                    {/* contest_mode est déterminé par le type: nomination ou participation */}
                                    <div className="mb-2">
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            Mode du concours
                                        </label>
                                        <Select
                                            value={formData.contest_mode || "participation"}
                                            onValueChange={(value) => setFormData({ ...formData, contest_mode: value })}
                                        >
                                            <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="participation">Participation</SelectItem>
                                                <SelectItem value="nomination">Nomination</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.season') || 'Saison'}
                                        </label>
                                        <Select
                                            value={formData.season_id}
                                            onValueChange={(value) => setFormData({ ...formData, season_id: value })}
                                        >
                                            <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                                <SelectValue placeholder={t('admin.contests.select_season') || 'Sélectionner une saison'} />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {seasons.map((season) => (
                                                    <SelectItem key={season.id} value={season.id.toString()}>
                                                        {season.level}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.voting_restriction') || 'Qui peut participer'}
                                        </label>
                                        <Select
                                            value={formData.voting_restriction}
                                            onValueChange={(value) => setFormData({ ...formData, voting_restriction: value })}
                                        >
                                            <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="none">{t('admin.contests.none') || 'Tous'}</SelectItem>
                                                <SelectItem value="male_only">{t('admin.contests.male_only') || 'Hommes uniquement'}</SelectItem>
                                                <SelectItem value="female_only">{t('admin.contests.female_only') || 'Femmes uniquement'}</SelectItem>
                                                <SelectItem value="geographic">{t('admin.contests.geographic') || 'Géographique'}</SelectItem>
                                                <SelectItem value="age_restricted">{t('admin.contests.age_restricted') || 'Restreint par âge'}</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                        {t('admin.contests.contest_description') || 'Description'} <span className="text-red-500">*</span>
                                    </label>
                                    <textarea
                                        value={formData.description}
                                        onChange={(e) => {
                                            setFormData({ ...formData, description: e.target.value })
                                            if (e.target.value.trim()) {
                                                setErrors(prev => ({ ...prev, description: '' }))
                                            }
                                        }}
                                        className={`w-full min-h-[100px] p-2 rounded-md border text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white ${errors.description ? 'border-red-500' : ''}`}
                                    />
                                    {errors.description && <p className="text-red-500 text-xs mt-1">{errors.description}</p>}
                                </div>

                                {/* Image Upload */}
                                <div>
                                    <label className="block text-sm font-medium mb-3 text-gray-900 dark:text-white">
                                        📸 {t('admin.contests.image') || 'Contest Image'} <span className="text-red-500">*</span>
                                    </label>

                                    {/* Hidden file input */}
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept="image/*"
                                        className="hidden"
                                        onChange={handleFileChange}
                                    />

                                    {/* Preview + change button */}
                                    {uploadedImage ? (
                                        <div className="flex items-start gap-4">
                                            <img
                                                src={uploadedImage}
                                                alt="Preview"
                                                className="h-40 w-40 object-cover rounded-lg border-2 border-myhigh5-primary/30 shadow"
                                            />
                                            <div className="flex flex-col gap-2 mt-2">
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => fileInputRef.current?.click()}
                                                    disabled={isUploading}
                                                    className="dark:bg-gray-700 dark:text-white"
                                                >
                                                    {isUploading ? (
                                                        <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Uploading...</>
                                                    ) : (
                                                        <><ImagePlus className="w-4 h-4 mr-2" /> Change Image</>
                                                    )}
                                                </Button>
                                                <Button
                                                    type="button"
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => {
                                                        setUploadedImage('')
                                                        setFormData(prev => ({ ...prev, image_url: '', cover_image_url: '' }))
                                                        if (fileInputRef.current) fileInputRef.current.value = ''
                                                    }}
                                                    className="text-red-500 hover:text-red-600 hover:bg-red-50"
                                                >
                                                    <X className="w-4 h-4 mr-1" /> Remove
                                                </Button>
                                            </div>
                                        </div>
                                    ) : (
                                        <button
                                            type="button"
                                            onClick={() => fileInputRef.current?.click()}
                                            disabled={isUploading}
                                            className="flex flex-col items-center justify-center w-full h-36 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl hover:border-myhigh5-primary hover:bg-myhigh5-primary/5 transition-colors cursor-pointer disabled:opacity-50"
                                        >
                                            {isUploading ? (
                                                <>
                                                    <Loader2 className="w-8 h-8 text-myhigh5-primary animate-spin mb-2" />
                                                    <span className="text-sm text-gray-500">Uploading...</span>
                                                </>
                                            ) : (
                                                <>
                                                    <ImagePlus className="w-8 h-8 text-gray-400 mb-2" />
                                                    <span className="text-sm font-medium text-gray-600 dark:text-gray-300">Click to upload image</span>
                                                    <span className="text-xs text-gray-400 mt-1">PNG, JPG up to 8MB</span>
                                                </>
                                            )}
                                        </button>
                                    )}

                                    {uploadError && <p className="text-red-500 text-xs mt-2">{uploadError}</p>}
                                    {errors.image && <p className="text-red-500 text-xs mt-1">{errors.image}</p>}
                                </div>
                            </TabsContent>

                            <TabsContent value="requirements" className="space-y-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.verification_type') || 'Type de vérification'}
                                        </label>
                                        <Select
                                            value={formData.verification_type}
                                            onValueChange={(value) => setFormData({ ...formData, verification_type: value })}
                                        >
                                            <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="none">{t('admin.contests.none') || 'Aucune'}</SelectItem>
                                                <SelectItem value="visual">{t('admin.contests.verification_visual') || 'Visuelle'}</SelectItem>
                                                <SelectItem value="voice">{t('admin.contests.verification_voice') || 'Vocale'}</SelectItem>
                                                <SelectItem value="brand">{t('admin.contests.verification_brand') || 'Marque'}</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.participant_type') || 'Type de participant'}
                                        </label>
                                        <Select
                                            value={formData.participant_type}
                                            onValueChange={(value) => setFormData({ ...formData, participant_type: value })}
                                        >
                                            <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="individual">{t('admin.contests.participant_individual') || 'Individu'}</SelectItem>
                                                <SelectItem value="pet">{t('admin.contests.participant_pet') || 'Animal'}</SelectItem>
                                                <SelectItem value="club">{t('admin.contests.participant_club') || 'Club'}</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <label className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={formData.requires_kyc}
                                            onChange={(e) => setFormData({ ...formData, requires_kyc: e.target.checked })}
                                            className="rounded border-gray-300"
                                        />
                                        <span className="text-sm dark:text-gray-200">{t('admin.contests.kyc_required') || 'KYC Requis'}</span>
                                    </label>
                                    <label className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={formData.requires_visual_verification}
                                            onChange={(e) => setFormData({ ...formData, requires_visual_verification: e.target.checked })}
                                            className="rounded border-gray-300"
                                        />
                                        <span className="text-sm dark:text-gray-200">{t('admin.contests.verification_visual') || 'Vérification Visuelle'}</span>
                                    </label>
                                    <label className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={formData.requires_voice_verification}
                                            onChange={(e) => setFormData({ ...formData, requires_voice_verification: e.target.checked })}
                                            className="rounded border-gray-300"
                                        />
                                        <span className="text-sm dark:text-gray-200">{t('admin.contests.verification_voice') || 'Vérification Vocale'}</span>
                                    </label>
                                    <label className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={formData.requires_brand_verification}
                                            onChange={(e) => setFormData({ ...formData, requires_brand_verification: e.target.checked })}
                                            className="rounded border-gray-300"
                                        />
                                        <span className="text-sm dark:text-gray-200">{t('admin.contests.verification_brand') || 'Vérification de Marque'}</span>
                                    </label>
                                    <label className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={formData.requires_content_verification}
                                            onChange={(e) => setFormData({ ...formData, requires_content_verification: e.target.checked })}
                                            className="rounded border-gray-300"
                                        />
                                        <span className="text-sm dark:text-gray-200">{t('admin.contests.verification_content') || 'Vérification de Contenu'}</span>
                                    </label>
                                </div>

                                <div className="grid grid-cols-2 gap-4 pt-2">
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.min_age') || 'Age Minimum'}
                                        </label>
                                        <Input
                                            type="number"
                                            value={formData.min_age}
                                            onChange={(e) => setFormData({ ...formData, min_age: e.target.value })}
                                            className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.max_age') || 'Age Maximum'}
                                        </label>
                                        <Input
                                            type="number"
                                            value={formData.max_age}
                                            onChange={(e) => setFormData({ ...formData, max_age: e.target.value })}
                                            className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                        />
                                    </div>
                                </div>
                            </TabsContent>

                            <TabsContent value="media" className="space-y-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.min_images') || 'Min Images'}
                                        </label>
                                        <Input
                                            type="number"
                                            value={formData.min_images}
                                            onChange={(e) => setFormData({ ...formData, min_images: parseInt(e.target.value) || 0 })}
                                            className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                            {t('admin.contests.max_images') || 'Max Images'}
                                        </label>
                                        <Input
                                            type="number"
                                            value={formData.max_images}
                                            onChange={(e) => setFormData({ ...formData, max_images: parseInt(e.target.value) || 0 })}
                                            className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                        />
                                    </div>
                                </div>

                                <div className="space-y-2 pt-2">
                                    <label className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={formData.requires_video}
                                            onChange={(e) => setFormData({ ...formData, requires_video: e.target.checked })}
                                            className="rounded border-gray-300"
                                        />
                                        <span className="text-sm dark:text-gray-200">{t('admin.contests.requires_video') || 'Vidéo Requise'}</span>
                                    </label>
                                </div>

                                {formData.requires_video && (
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                                {t('admin.contests.video_max_duration') || 'Durée max vidéo (sec)'}
                                            </label>
                                            <Input
                                                type="number"
                                                value={formData.video_max_duration}
                                                onChange={(e) => setFormData({ ...formData, video_max_duration: parseInt(e.target.value) || 0 })}
                                                className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                                {t('admin.contests.video_max_size_mb') || 'Taille max vidéo (MB)'}
                                            </label>
                                            <Input
                                                type="number"
                                                value={formData.video_max_size_mb}
                                                onChange={(e) => setFormData({ ...formData, video_max_size_mb: parseInt(e.target.value) || 0 })}
                                                className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                            />
                                        </div>
                                    </div>
                                )}
                            </TabsContent>
                        </Tabs>

                        <div className="flex justify-end gap-3 pt-4 border-t dark:border-gray-700">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={onClose}
                                className="dark:bg-gray-700 dark:text-white dark:hover:bg-gray-600"
                            >
                                {t('common.cancel') || 'Annuler'}
                            </Button>
                            <Button
                                type="submit"
                                className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                                disabled={isSubmitting}
                            >
                                {isSubmitting ? (t('common.saving') || 'Enregistrement...') : (t('common.save') || 'Enregistrer')}
                            </Button>
                        </div>
                    </form>
                </CardContent>
            </Card>
        </div>
    )
}
