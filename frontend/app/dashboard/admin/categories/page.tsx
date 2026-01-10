'use client'

import { useLanguage } from '@/contexts/language-context'
import { Tag, Plus, Edit, Trash2, Search, CheckCircle2, XCircle } from 'lucide-react'
import { useState, useEffect } from 'react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { useToast } from '@/components/ui/toast'
import { cacheService } from '@/lib/cache-service'

interface Category {
  id: number
  name: string
  slug: string
  description: string | null
  is_active: boolean
  created_at: string
}

export default function CategoriesPage() {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingCategory, setEditingCategory] = useState<Category | null>(null)
  const [formData, setFormData] = useState({
    name: '',
    slug: '',
    description: '',
    is_active: true,
  })
  const [formErrors, setFormErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    fetchCategories()
  }, [])

  const fetchCategories = async () => {
    try {
      setLoading(true)
      const endpoint = '/api/v1/categories'
      const params = { active_only: false }
      
      // Vérifier le cache
      const cachedData = cacheService.get<any[]>(endpoint, params)
      if (cachedData) {
        setCategories(cachedData)
        setLoading(false)
        return
      }
      
      // Si pas de cache, faire l'appel API
      const response = await api.get(`${endpoint}?active_only=false`)
      const data = response.data || []
      setCategories(data)
      
      // Mettre en cache (TTL de 5 minutes)
      cacheService.set(endpoint, data, params, 5 * 60 * 1000)
    } catch (error: any) {
      console.error('Erreur lors du chargement des catégories:', error)
      addToast(error.response?.data?.detail || t('admin.categories.categories_load_error') || 'Error loading categories', 'error')
    } finally {
      setLoading(false)
    }
  }

  const generateSlug = (name: string) => {
    return name
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '')
  }

  const handleOpenDialog = (category?: Category) => {
    if (category) {
      setEditingCategory(category)
      setFormData({
        name: category.name,
        slug: category.slug,
        description: category.description || '',
        is_active: category.is_active,
      })
    } else {
      setEditingCategory(null)
      setFormData({
        name: '',
        slug: '',
        description: '',
        is_active: true,
      })
    }
    setFormErrors({})
    setIsDialogOpen(true)
  }

  const handleCloseDialog = () => {
    setIsDialogOpen(false)
    setEditingCategory(null)
    setFormData({
      name: '',
      slug: '',
      description: '',
      is_active: true,
    })
    setFormErrors({})
  }

  const handleNameChange = (name: string) => {
    setFormData({
      ...formData,
      name,
      slug: editingCategory ? formData.slug : generateSlug(name),
    })
    if (formErrors.name) {
      setFormErrors({ ...formErrors, name: '' })
    }
  }

  const validateForm = () => {
    const errors: Record<string, string> = {}
    
    if (!formData.name.trim()) {
      errors.name = t('admin.categories.category_name_required') || 'Name is required'
    } else if (formData.name.length > 100) {
      errors.name = t('admin.categories.category_name_max_length') || 'Name cannot exceed 100 characters'
    }
    
    if (!formData.slug.trim()) {
      errors.slug = t('admin.categories.slug_required') || 'Slug is required'
    } else if (formData.slug.length > 100) {
      errors.slug = t('admin.categories.slug_max_length') || 'Slug cannot exceed 100 characters'
    } else if (!/^[a-z0-9-]+$/.test(formData.slug)) {
      errors.slug = t('admin.categories.slug_invalid') || 'Slug can only contain lowercase letters, numbers and hyphens'
    }
    
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = async () => {
    if (!validateForm()) {
      return
    }

    try {
      setSubmitting(true)
      
      if (editingCategory) {
        // Mise à jour
        await api.put(`/api/v1/categories/${editingCategory.id}`, {
          name: formData.name.trim(),
          slug: formData.slug.trim(),
          description: formData.description.trim() || null,
          is_active: formData.is_active,
        })
        addToast(t('admin.categories.category_updated') || 'Category updated successfully', 'success')
      } else {
        // Création
        await api.post('/api/v1/categories', {
          name: formData.name.trim(),
          slug: formData.slug.trim(),
          description: formData.description.trim() || null,
          is_active: formData.is_active,
        })
        addToast(t('admin.categories.category_created') || 'Category created successfully', 'success')
      }
      
      // Invalider le cache des catégories
      cacheService.invalidate('/api/v1/categories')
      
      handleCloseDialog()
      fetchCategories()
    } catch (error: any) {
      console.error('Erreur lors de la sauvegarde:', error)
      const errorMessage = error.response?.data?.detail || t('admin.categories.category_update_error') || 'Error saving'
      addToast(errorMessage, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (category: Category) => {
    if (!confirm(`${t('admin.categories.delete_confirm') || 'Are you sure you want to delete the category'} "${category.name}"?`)) {
      return
    }

    try {
      await api.delete(`/api/v1/categories/${category.id}`)
      
      // Invalider le cache des catégories
      cacheService.invalidate('/api/v1/categories')
      
      addToast(t('admin.categories.category_deleted') || 'Category deleted successfully', 'success')
      fetchCategories()
    } catch (error: any) {
      console.error('Erreur lors de la suppression:', error)
      const errorMessage = error.response?.data?.detail || t('admin.categories.category_delete_error') || 'Error deleting'
      addToast(errorMessage, 'error')
    }
  }

  const filteredCategories = categories.filter((category) =>
    category.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    category.slug.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Tag className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
            <div>
              <h1 className="text-4xl font-bold text-white dark:text-white">
                {t('admin.categories.title') || 'Category Management'}
              </h1>
              <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium mt-1">
                {t('admin.categories.description') || 'Create and manage contest categories'}
              </p>
            </div>
          </div>
          <Button
            onClick={() => handleOpenDialog()}
            className="bg-white text-myhigh5-primary hover:bg-gray-100 dark:bg-gray-800 dark:text-myhigh5-secondary dark:hover:bg-gray-700"
          >
            <Plus className="h-4 w-4 mr-2" />
            {t('admin.categories.add_category') || 'Add category'}
          </Button>
        </div>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder={t('admin.categories.search_placeholder') || 'Search for a category...'}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Categories List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
        </div>
      ) : filteredCategories.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Tag className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">
              {searchTerm ? (t('admin.categories.no_categories_found') || 'No categories found') : (t('admin.categories.no_categories') || 'No categories yet')}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredCategories.map((category) => (
            <Card key={category.id} className="hover:shadow-lg transition-shadow">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <CardTitle className="text-lg font-semibold">{category.name}</CardTitle>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                      {category.slug}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {category.is_active ? (
                      <CheckCircle2 className="h-5 w-5 text-green-500" />
                    ) : (
                      <XCircle className="h-5 w-5 text-gray-400" />
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {category.description && (
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-4 line-clamp-2">
                    {category.description}
                  </p>
                )}
                <div className="flex items-center justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {`${t('admin.categories.created_at') || 'Created on'} ${new Date(category.created_at).toLocaleDateString('en-US')}`}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleOpenDialog(category)}
                    >
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDelete(category)}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialog pour créer/modifier une catégorie */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>
              {editingCategory ? (t('admin.categories.edit_category') || 'Edit category') : (t('admin.categories.create_category') || 'Create a new category')}
            </DialogTitle>
            <DialogDescription>
              {editingCategory
                ? (t('admin.categories.edit_category_description') || 'Edit category information')
                : (t('admin.categories.create_category_description') || 'Fill in the information to create a new category')}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">
                {t('admin.categories.category_name') || 'Name'} <span className="text-red-500">*</span>
              </Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder={t('admin.categories.category_name_placeholder') || 'Ex: Beauty'}
                className={formErrors.name ? 'border-red-500' : ''}
              />
              {formErrors.name && (
                <p className="text-sm text-red-500">{formErrors.name}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="slug">
                {t('admin.categories.slug') || 'Slug'} <span className="text-red-500">*</span>
              </Label>
              <Input
                id="slug"
                value={formData.slug}
                onChange={(e) => {
                  setFormData({ ...formData, slug: e.target.value })
                  if (formErrors.slug) {
                    setFormErrors({ ...formErrors, slug: '' })
                  }
                }}
                placeholder={t('admin.categories.slug_placeholder') || 'Ex: beauty'}
                className={formErrors.slug ? 'border-red-500' : ''}
                disabled={!!editingCategory}
              />
              {formErrors.slug && (
                <p className="text-sm text-red-500">{formErrors.slug}</p>
              )}
              {!editingCategory && (
                <p className="text-xs text-gray-500">
                  {t('admin.categories.slug_auto_generated') || 'The slug is automatically generated from the name'}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">{t('admin.categories.description_label') || 'Description'}</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder={t('admin.categories.description_placeholder') || 'Category description (optional)'}
                rows={3}
              />
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="is_active">{t('admin.categories.is_active') || 'Active category'}</Label>
              <Switch
                id="is_active"
                checked={formData.is_active}
                onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={handleCloseDialog} disabled={submitting}>
              {t('admin.categories.cancel') || 'Cancel'}
            </Button>
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting ? (t('admin.categories.saving') || 'Saving...') : editingCategory ? (t('admin.categories.edit') || 'Edit') : (t('admin.categories.create') || 'Create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
