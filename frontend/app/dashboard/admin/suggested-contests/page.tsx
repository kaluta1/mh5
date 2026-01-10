'use client'

import { useLanguage } from '@/contexts/language-context'
import { Lightbulb, Search, User, Calendar, CheckCircle2, Clock, XCircle, Tag, Eye } from 'lucide-react'
import { useState, useEffect } from 'react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/toast'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface SuggestedContest {
  id: number
  name: string
  description: string | null
  category: string
  status: string
  created_at: string | null
  updated_at: string | null
  author: {
    id: number
    username: string | null
    full_name: string | null
    email: string
    avatar_url: string | null
    city: string | null
    country: string | null
    is_verified: boolean
  } | null
}

export default function SuggestedContestsPage() {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [suggestions, setSuggestions] = useState<SuggestedContest[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [selectedSuggestion, setSelectedSuggestion] = useState<SuggestedContest | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  useEffect(() => {
    fetchSuggestions()
  }, [statusFilter])

  const fetchSuggestions = async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams()
      if (statusFilter !== 'all') {
        params.append('status', statusFilter)
      }
      const response = await api.get(`/api/v1/admin/suggested-contests?${params.toString()}`)
      setSuggestions(response.data || [])
    } catch (error: any) {
      console.error('Erreur lors du chargement des suggestions:', error)
      addToast(error.response?.data?.detail || t('admin.suggested_contests.load_error') || 'Erreur lors du chargement des suggestions', 'error')
    } finally {
      setLoading(false)
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-400"><Clock className="h-3 w-3 mr-1" />{t('admin.suggested_contests.pending') || 'En attente'}</Badge>
      case 'approved':
        return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-400"><CheckCircle2 className="h-3 w-3 mr-1" />{t('admin.suggested_contests.approved') || 'Approuvé'}</Badge>
      case 'rejected':
        return <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400"><XCircle className="h-3 w-3 mr-1" />{t('admin.suggested_contests.rejected') || 'Rejeté'}</Badge>
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  const filteredSuggestions = suggestions.filter((suggestion) => {
    const matchesSearch = 
      suggestion.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      suggestion.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      suggestion.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
      suggestion.author?.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      suggestion.author?.username?.toLowerCase().includes(searchTerm.toLowerCase())
    return matchesSearch
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex items-center gap-3">
          <Lightbulb className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
          <div>
            <h1 className="text-4xl font-bold text-white dark:text-white">
              {t('admin.suggested_contests.title') || 'Suggestions de Concours'}
            </h1>
            <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium mt-1">
              {t('admin.suggested_contests.description') || 'Gérez les suggestions de concours proposées par les utilisateurs'}
            </p>
          </div>
        </div>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder={t('admin.suggested_contests.search_placeholder') || 'Rechercher une suggestion...'}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant={statusFilter === 'all' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('all')}
              >
                {t('admin.suggested_contests.all') || 'Tous'}
              </Button>
              <Button
                variant={statusFilter === 'pending' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('pending')}
              >
                {t('admin.suggested_contests.pending') || 'En attente'}
              </Button>
              <Button
                variant={statusFilter === 'approved' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('approved')}
              >
                {t('admin.suggested_contests.approved') || 'Approuvés'}
              </Button>
              <Button
                variant={statusFilter === 'rejected' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('rejected')}
              >
                {t('admin.suggested_contests.rejected') || 'Rejetés'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Suggestions List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
        </div>
      ) : filteredSuggestions.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Lightbulb className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">
              {searchTerm 
                ? (t('admin.suggested_contests.no_suggestions_found') || 'Aucune suggestion trouvée')
                : (t('admin.suggested_contests.no_suggestions') || 'Aucune suggestion pour le moment')}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredSuggestions.map((suggestion) => (
            <Card key={suggestion.id} className="hover:shadow-lg transition-shadow">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <CardTitle className="text-lg">{suggestion.name}</CardTitle>
                      {getStatusBadge(suggestion.status)}
                    </div>
                    <div className="flex items-center gap-2 mb-2">
                      <Tag className="h-4 w-4 text-gray-400" />
                      <span className="text-sm text-gray-600 dark:text-gray-400">{suggestion.category}</span>
                    </div>
                    {suggestion.description && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                        {suggestion.description}
                      </p>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {/* Auteur */}
                {suggestion.author ? (
                  <div className="mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
                    <h4 className="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-2">{t('admin.suggested_contests.author') || 'Auteur'}</h4>
                    <div className="flex items-center gap-2">
                      <Avatar className="h-8 w-8">
                        <AvatarImage src={suggestion.author.avatar_url || undefined} />
                        <AvatarFallback>
                          {suggestion.author.full_name?.[0] || suggestion.author.username?.[0] || 'U'}
                        </AvatarFallback>
                      </Avatar>
                      <div className="text-sm">
                        <p className="font-medium">{suggestion.author.full_name || suggestion.author.username}</p>
                        <p className="text-gray-500 dark:text-gray-400 text-xs">
                          {suggestion.author.city && suggestion.author.country 
                            ? `${suggestion.author.city}, ${suggestion.author.country}`
                            : suggestion.author.email}
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
                    <p className="text-sm text-gray-500 dark:text-gray-400">{t('admin.suggested_contests.author_not_available') || 'Auteur non disponible'}</p>
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                    <Calendar className="h-3 w-3" />
                    <span>
                      {suggestion.created_at 
                        ? new Date(suggestion.created_at).toLocaleDateString('fr-FR')
                        : (t('admin.suggested_contests.unknown_date') || 'Date inconnue')}
                    </span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSelectedSuggestion(suggestion)
                      setIsDialogOpen(true)
                    }}
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    {t('admin.suggested_contests.details') || 'Détails'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialog pour les détails */}
      {selectedSuggestion && (
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{selectedSuggestion.name}</DialogTitle>
              <DialogDescription>
                {t('admin.suggested_contests.contest_suggestion_details') || 'Détails de la suggestion de concours'}
              </DialogDescription>
            </DialogHeader>
            
            <div className="space-y-4">
              <div>
                <h4 className="font-semibold mb-2">{t('admin.suggested_contests.status') || 'Statut'}</h4>
                {getStatusBadge(selectedSuggestion.status)}
              </div>

              <div>
                <h4 className="font-semibold mb-2">{t('admin.suggested_contests.category') || 'Catégorie'}</h4>
                <p className="text-sm">{selectedSuggestion.category}</p>
              </div>

              {selectedSuggestion.description && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.suggested_contests.description') || 'Description'}</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedSuggestion.description}</p>
                </div>
              )}

              {selectedSuggestion.author && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.suggested_contests.author') || 'Auteur'}</h4>
                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Avatar>
                        <AvatarImage src={selectedSuggestion.author.avatar_url || undefined} />
                        <AvatarFallback>
                          {selectedSuggestion.author.full_name?.[0] || selectedSuggestion.author.username?.[0] || 'U'}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-medium">{selectedSuggestion.author.full_name || selectedSuggestion.author.username}</p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{selectedSuggestion.author.email}</p>
                        {selectedSuggestion.author.city && selectedSuggestion.author.country && (
                          <p className="text-sm text-gray-600 dark:text-gray-400">
                            {selectedSuggestion.author.city}, {selectedSuggestion.author.country}
                          </p>
                        )}
                        {selectedSuggestion.author.is_verified && (
                          <Badge variant="outline" className="mt-1 bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-400">
                            {t('admin.suggested_contests.verified') || 'Vérifié'}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div>
                <h4 className="font-semibold mb-2">{t('admin.suggested_contests.dates') || 'Dates'}</h4>
                <div className="text-sm space-y-1">
                  <p className="text-gray-600 dark:text-gray-400">
                    <span className="font-medium">{t('admin.suggested_contests.created_at') || 'Créé le'}:</span>{' '}
                    {selectedSuggestion.created_at 
                      ? new Date(selectedSuggestion.created_at).toLocaleDateString('fr-FR', {
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })
                      : (t('admin.suggested_contests.unknown_date') || 'Date inconnue')}
                  </p>
                  {selectedSuggestion.updated_at && (
                    <p className="text-gray-600 dark:text-gray-400">
                      <span className="font-medium">{t('admin.suggested_contests.updated_at') || 'Modifié le'}:</span>{' '}
                      {new Date(selectedSuggestion.updated_at).toLocaleDateString('fr-FR', {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
