'use client'

import * as React from "react"
import { useState, useEffect } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import { FavoritesSkeleton } from '@/components/ui/skeleton'
import { ContestsGrid } from '@/components/dashboard/contests-grid'
import { contestService, Contest, ContestResponse } from '@/services/contest-service'
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { GripVertical, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function FavoritesPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  
  // Favoris de contests
  const [favoriteContests, setFavoriteContests] = useState<Contest[]>([])
  const [favoriteContestIds, setFavoriteContestIds] = useState<string[]>([])
  
  // Favoris de contestants
  const [favoriteContestants, setFavoriteContestants] = useState<any[]>([])
  const [draggedItem, setDraggedItem] = useState<number | null>(null)
  
  const [pageLoading, setPageLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('contests')

  // Redirection si non authentifié
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  // Charger les favoris
  useEffect(() => {
    const loadFavorites = async () => {
      try {
        setPageLoading(true)
        
        // Charger les contests favoris
        const favContests = await contestService.getFavoritesContests(0, 100)
        // Ensure we have valid contest data before mapping
        const contests: Contest[] = favContests
          .filter((c): c is ContestResponse => c !== null && c !== undefined)
          .map(contestService.mapResponseToContest);
          
        setFavoriteContests(contests)
        // Ensure all IDs are strings
        setFavoriteContestIds(contests.map(c => String(c.id)))
        
        // Charger les contestants favoris
        try {
          const favContestantIds = await contestService.getUserFavorites()
          if (favContestantIds && favContestantIds.length > 0) {
            // Charger les détails des contestants
            const contestants = await Promise.all(
              favContestantIds.map(id => contestService.getContestantById(id))
            )
            if (contestants.length > 0) {
              // Trier par position croissante
              const sorted = contestants
                .filter(c => c !== null)
                .sort((a, b) => {
                  const posA = a.position || 0
                  const posB = b.position || 0
                  return posA - posB
                })
              setFavoriteContestants(sorted)
            }
          }
        } catch (error) {
          console.error('Erreur lors du chargement des contestants favoris:', error)
          setFavoriteContestants([])
        }
        
      } catch (error) {
        console.error('Erreur lors du chargement des favoris:', error)
        setFavoriteContests([])
        setFavoriteContestants([])
      } finally {
        setPageLoading(false)
      }
    }

    if (!isLoading && isAuthenticated && user) {
      loadFavorites()
    }
  }, [isLoading, isAuthenticated, user])

  const handleToggleFavorite = async (contestId: string) => {
    try {
      if (favoriteContestIds.includes(contestId)) {
        // Retirer des favoris
        await contestService.removeContestFavorite(contestId)
        setFavoriteContests(prev => prev.filter(c => c.id !== contestId))
        setFavoriteContestIds(prev => prev.filter(id => id !== contestId))
      } else {
        // Ajouter aux favoris
        if (favoriteContestIds.length >= 5) {
          console.warn('Limite de 5 favoris atteinte')
          return
        }
        await contestService.addContestFavorite(contestId)
        // Recharger le contest pour l'ajouter à la liste
        const contest = await contestService.getContestById(contestId)
        if (contest) {
          // No need to map since getContestById already returns a Contest object
          setFavoriteContests(prev => [...prev, contest])
          setFavoriteContestIds(prev => [...prev, contestId])
        }
      }
    } catch (error) {
      console.error('Erreur lors de la modification des favoris:', error)
    }
  }

  // Drag and drop handlers
  const handleDragStart = (index: number) => {
    setDraggedItem(index);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>, index: number) => {
    e.preventDefault();
    if (draggedItem === null || draggedItem === index) return;
    
    const items = [...favoriteContestants];
    const [movedItem] = items.splice(draggedItem, 1);
    items.splice(index, 0, movedItem);
    
    setFavoriteContestants(items);
    
    // Update order in backend
    const contestantIds = items.map(item => item.id);
    contestService.reorderFavorites(contestantIds)
      .catch(error => {
        console.error('Error reordering favorites:', error);
        // Revert local state on error
        loadFavorites();
      });
      
    setDraggedItem(null);
    
    setDraggedItem(null);
  };

  const loadFavorites = async () => {
    try {
      setPageLoading(true);
      
      // Load favorite contests
      const favContests = await contestService.getFavoritesContests(0, 100);
      const contests = favContests
        .filter((c): c is ContestResponse => {
          // Ensure we have a valid ContestResponse
          if (!c) return false;
          // Check for required ContestResponse properties
          return 'contest_type' in c && 'id' in c;
        })
        .map(contestService.mapResponseToContest);
      
      setFavoriteContests(contests);
      setFavoriteContestIds(contests.map(c => String(c.id)));
      
      // Load favorite contestants
      try {
        const favContestantIds = await contestService.getUserFavorites();
        if (favContestantIds && favContestantIds.length > 0) {
          const contestants = await Promise.all(
            favContestantIds.map(id => contestService.getContestantById(id))
          );
          setFavoriteContestants(contestants.filter(Boolean));
        }
      } catch (error) {
        console.error('Error loading favorite contestants:', error);
        setFavoriteContestants([]);
      }
    } catch (error) {
      console.error('Error loading favorites:', error);
      setFavoriteContests([]);
      setFavoriteContestants([]);
    } finally {
      setPageLoading(false);
    }
  };

  const handleRemoveFavoriteContestant = async (contestantId: number) => {
    try {
      await contestService.removeFromFavorites(contestantId)
      setFavoriteContestants(prev => prev.filter(c => c.id !== contestantId))
    } catch (error) {
      console.error('Erreur lors de la suppression du favori:', error)
    }
  }

  const handleViewContestants = (contestId: string) => {
    router.push(`/dashboard/contests/${contestId}`)
  }

  const handleParticipate = (contestId: string) => {
    router.push(`/dashboard/contests/${contestId}/apply`)
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
          {t('dashboard.favorites.title')}
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          {t('dashboard.favorites.description')}
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="contests">
            {t('dashboard.favorites.contests_tab')}
          </TabsTrigger>
          <TabsTrigger value="contestants">
            {t('dashboard.favorites.contestants_tab')}
          </TabsTrigger>
        </TabsList>

        {/* Contests Favoris */}
        <TabsContent value="contests" className="space-y-4">
          {favoriteContests.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400">
                {t('dashboard.favorites.no_favorite_contests')}
              </p>
            </div>
          ) : (
            <ContestsGrid
              contests={favoriteContests}
              favorites={favoriteContestIds}
              onToggleFavorite={handleToggleFavorite}
              onViewContestants={handleViewContestants}
              onParticipate={handleParticipate}
            />
          )}
        </TabsContent>

        {/* Contestants Favoris */}
        <TabsContent value="contestants" className="space-y-4">
          {favoriteContestants.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600 dark:text-gray-400">
                {t('dashboard.favorites.no_favorite_contestants')}
              </p>
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
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-4xl sm:text-6xl font-bold text-white opacity-20">
                        {contestant.author_name?.charAt(0).toUpperCase() || '?'}
                      </div>
                    )}
                    
                    {/* Overlay */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent" />
                  </div>

                  {/* Content */}
                  <div className="absolute bottom-0 left-0 right-0 p-2 sm:p-4 text-white">
                    {/* Author Name */}
                    <h3 className="font-bold text-xs sm:text-lg line-clamp-1">
                      {contestant.author_name || 'Contestant'}
                    </h3>
                    
                    {/* Contestant Title */}
                    <p className="text-xs sm:text-sm text-gray-200 line-clamp-1 hidden sm:block">
                      {contestant.title}
                    </p>

                    {/* Stats */}
                    <div className="flex items-center gap-1 sm:gap-3 mt-1 sm:mt-2 text-xs text-gray-300">
                      <span className="hidden sm:inline">⭐ {contestant.votes_count || 0}</span>
                      <span className="hidden sm:inline">📸 {contestant.images_count || 0}</span>
                      <span className="hidden sm:inline">🎬 {contestant.videos_count || 0}</span>
                      <span className="sm:hidden">⭐{contestant.votes_count || 0}</span>
                    </div>
                  </div>

                  {/* Position Badge - Top Left */}
                  <div className="absolute top-1 left-1 sm:top-2 sm:left-2 bg-myhigh5-primary text-white rounded-full w-6 h-6 sm:w-8 sm:h-8 flex items-center justify-center font-bold text-xs sm:text-sm shadow-lg">
                    {index + 1}
                  </div>

                  {/* Drag Handle - Bottom Left */}
                  <div className="absolute bottom-1 left-1 sm:bottom-2 sm:left-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <GripVertical className="w-4 h-4 sm:w-5 sm:h-5 text-white drop-shadow-lg" />
                  </div>

                  {/* Remove Button - Top Right */}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRemoveFavoriteContestant(contestant.id)}
                    className="absolute top-1 right-1 sm:top-2 sm:right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-red-500/80 hover:bg-red-600 text-white rounded-full p-1 sm:p-2 h-auto w-auto"
                  >
                    <Trash2 className="w-3 h-3 sm:w-4 sm:h-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
