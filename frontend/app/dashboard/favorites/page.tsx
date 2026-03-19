'use client'

import * as React from "react"
import { useState, useEffect } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import { FavoritesSkeleton } from '@/components/ui/skeleton'
import { contestService } from '@/services/contest-service'
import { GripVertical, Trash2, Star, Heart } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function FavoritesPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()

  const [favoriteContestants, setFavoriteContestants] = useState<any[]>([])
  const [draggedItem, setDraggedItem] = useState<number | null>(null)
  const [pageLoading, setPageLoading] = useState(true)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  const loadFavorites = async () => {
    try {
      setPageLoading(true)
      const favContestantIds = await contestService.getUserFavorites()
      if (favContestantIds && favContestantIds.length > 0) {
        const contestants = await Promise.all(
          favContestantIds.map(id => contestService.getContestantById(id))
        )
        const sorted = contestants
          .filter(Boolean)
          .sort((a, b) => (a.position || 0) - (b.position || 0))
        setFavoriteContestants(sorted)
      } else {
        setFavoriteContestants([])
      }
    } catch (error) {
      console.error('Erreur lors du chargement des favoris:', error)
      setFavoriteContestants([])
    } finally {
      setPageLoading(false)
    }
  }

  useEffect(() => {
    if (!isLoading && isAuthenticated && user) {
      loadFavorites()
    }
  }, [isLoading, isAuthenticated, user])

  // Drag and drop
  const handleDragStart = (index: number) => {
    setDraggedItem(index)
  }

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>, index: number) => {
    e.preventDefault()
    if (draggedItem === null || draggedItem === index) return

    const items = [...favoriteContestants]
    const [movedItem] = items.splice(draggedItem, 1)
    items.splice(index, 0, movedItem)

    setFavoriteContestants(items)
    setDraggedItem(null)

    const contestantIds = items.map(item => item.id)
    contestService.reorderFavorites(contestantIds).catch(() => {
      loadFavorites()
    })
  }

  const handleRemoveFavorite = async (contestantId: number) => {
    try {
      await contestService.removeFromFavorites(contestantId)
      setFavoriteContestants(prev => prev.filter(c => c.id !== contestantId))
    } catch (error) {
      console.error('Erreur lors de la suppression du favori:', error)
    }
  }

  if (isLoading || pageLoading) {
    return <FavoritesSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          <Heart className="inline w-8 h-8 mr-2 text-red-500" />
          {t('dashboard.favorites.title') || 'Mes Favoris'}
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          {t('dashboard.favorites.description_contestants') || 'Organisez vos contestants favoris par glisser-déposer'}
        </p>
      </div>

      {/* Contestants Favoris */}
      {favoriteContestants.length === 0 ? (
        <div className="text-center py-16">
          <div className="w-20 h-20 mx-auto mb-4 bg-gray-800 rounded-full flex items-center justify-center">
            <Star className="w-10 h-10 text-gray-600" />
          </div>
          <h2 className="text-xl font-semibold text-gray-300 mb-2">
            {t('dashboard.favorites.no_favorites_yet') || 'Aucun favori pour le moment'}
          </h2>
          <p className="text-gray-500 max-w-md mx-auto">
            {t('dashboard.favorites.no_favorites_hint') || 'Ajoutez des contestants à vos favoris depuis la page d\'un concours en cliquant sur l\'étoile.'}
          </p>
          <Button
            onClick={() => router.push('/dashboard/contests')}
            className="mt-6 bg-myhigh5-primary hover:bg-myhigh5-blue-700"
          >
            {t('dashboard.favorites.browse_contests') || 'Parcourir les concours'}
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 sm:gap-4 md:gap-6">
          {favoriteContestants.map((contestant, index) => (
            <div
              key={contestant.id}
              draggable
              onDragStart={() => handleDragStart(index)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, index)}
              onClick={() => {
                if (contestant.season_id) {
                  router.push(`/dashboard/contests/${contestant.season_id}/contestant/${contestant.id}`)
                }
              }}
              className={`relative group rounded-xl sm:rounded-2xl overflow-hidden transition-all cursor-move ${
                draggedItem === index
                  ? 'opacity-50 scale-95'
                  : 'hover:shadow-xl hover:-translate-y-1'
              }`}
            >
              {/* Background Image */}
              <div className="relative w-full h-32 sm:h-48 md:h-64 bg-gradient-to-br from-myhigh5-primary to-myhigh5-primary-dark flex items-center justify-center overflow-hidden">
                {contestant.author_avatar_url ? (
                  <img
                    src={contestant.author_avatar_url}
                    alt={contestant.author_name}
                    className="w-full h-full object-cover"
                  />
                ) : contestant.image_media_ids ? (() => {
                  try {
                    const images = typeof contestant.image_media_ids === 'string'
                      ? JSON.parse(contestant.image_media_ids)
                      : contestant.image_media_ids
                    const firstImage = Array.isArray(images) && images.length > 0 ? images[0] : null
                    if (firstImage) {
                      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
                      const imgUrl = firstImage.startsWith('http') ? firstImage : `${API_BASE}${firstImage.startsWith('/') ? '' : '/'}${firstImage}`
                      return <img src={imgUrl} alt={contestant.title} className="w-full h-full object-cover" />
                    }
                    return null
                  } catch { return null }
                })() : (
                  <div className="w-full h-full flex items-center justify-center text-4xl sm:text-6xl font-bold text-white opacity-20">
                    {(contestant.author_name || contestant.title || '?').charAt(0).toUpperCase()}
                  </div>
                )}

                {/* Overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent" />
              </div>

              {/* Content */}
              <div className="absolute bottom-0 left-0 right-0 p-2 sm:p-4 text-white">
                <h3 className="font-bold text-xs sm:text-lg line-clamp-1">
                  {contestant.author_name || 'Contestant'}
                </h3>
                <p className="text-xs sm:text-sm text-gray-200 line-clamp-1 hidden sm:block">
                  {contestant.title}
                </p>
                <div className="flex items-center gap-1 sm:gap-3 mt-1 sm:mt-2 text-xs text-gray-300">
                  <span>⭐ {contestant.votes_count || 0}</span>
                  <span className="hidden sm:inline">📸 {contestant.images_count || 0}</span>
                  <span className="hidden sm:inline">🎬 {contestant.videos_count || 0}</span>
                </div>
              </div>

              {/* Position Badge */}
              <div className="absolute top-1 left-1 sm:top-2 sm:left-2 bg-myhigh5-primary text-white rounded-full w-6 h-6 sm:w-8 sm:h-8 flex items-center justify-center font-bold text-xs sm:text-sm shadow-lg">
                {index + 1}
              </div>

              {/* Drag Handle */}
              <div className="absolute bottom-1 left-1 sm:bottom-2 sm:left-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <GripVertical className="w-4 h-4 sm:w-5 sm:h-5 text-white drop-shadow-lg" />
              </div>

              {/* Remove Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  handleRemoveFavorite(contestant.id)
                }}
                className="absolute top-1 right-1 sm:top-2 sm:right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-red-500/80 hover:bg-red-600 text-white rounded-full p-1 sm:p-2 h-auto w-auto"
              >
                <Trash2 className="w-3 h-3 sm:w-4 sm:h-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
