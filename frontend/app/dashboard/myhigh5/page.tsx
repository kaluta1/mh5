'use client'

import * as React from "react"
import { useState, useEffect } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import { useToast } from '@/components/ui/toast'
import { contestService } from '@/services/contest-service'
import { Hand, Trophy, MapPin, Calendar, GripVertical, ExternalLink, Star, History } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

interface MyHigh5Vote {
  position: number
  points: number | null
  contestant_id: number
  contestant_title: string
  contestant_description: string
  author_id: number
  author_name: string
  author_avatar_url: string | null
  author_country: string | null
  author_city: string | null
  votes_count: number
  vote_date: string
  season_id: number
  contest_id: number
  season_level: string | null
}

interface SeasonVotes {
  season_id: number
  season_level: string | null
  contest_id: number
  contest_name: string | null
  votes: MyHigh5Vote[]
  votes_count: number
  remaining_slots: number
}

interface MyHigh5Response {
  seasons: SeasonVotes[]
}

interface HistoryContest {
  contest_id: number
  contest_name: string | null
  seasons: Array<{
    season_id: number
    season_level: string | null
    is_active: boolean
    votes: MyHigh5Vote[]
    votes_count: number
  }>
}

interface HistoryResponse {
  history: HistoryContest[]
}

// Points attribués selon la position (1er = 5 points, 2ème = 4 points, etc.)
const POINTS_BY_POSITION = [5, 4, 3, 2, 1]

function MyHigh5Skeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-96" />
      </div>
      <div className="space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-16 w-full rounded-lg" />
        ))}
      </div>
    </div>
  )
}

export default function MyHigh5Page() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const { addToast } = useToast()
  
  const [seasonsData, setSeasonsData] = useState<SeasonVotes[]>([])
  const [historyData, setHistoryData] = useState<HistoryContest[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('active')
  const [draggedItem, setDraggedItem] = useState<{ seasonIndex: number; voteIndex: number } | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  // Redirection si non authentifié
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  // Charger les votes MyHigh5 actifs
  useEffect(() => {
    const loadVotes = async () => {
      try {
        setPageLoading(true)
        const response = await contestService.getMyHigh5Votes() as MyHigh5Response
        setSeasonsData(response.seasons || [])
      } catch (error) {
        console.error('Erreur lors du chargement des votes:', error)
        setSeasonsData([])
      } finally {
        setPageLoading(false)
      }
    }

    if (!isLoading && isAuthenticated && user) {
      loadVotes()
    }
  }, [isLoading, isAuthenticated, user])

  // Charger l'historique quand on change d'onglet
  useEffect(() => {
    const loadHistory = async () => {
      if (activeTab === 'history' && historyData.length === 0 && !historyLoading) {
        try {
          setHistoryLoading(true)
          const response = await contestService.getMyHigh5VotesHistory() as HistoryResponse
          setHistoryData(response.history || [])
        } catch (error) {
          console.error('Erreur lors du chargement de l\'historique:', error)
          setHistoryData([])
        } finally {
          setHistoryLoading(false)
        }
      }
    }

    if (!isLoading && isAuthenticated && user) {
      loadHistory()
    }
  }, [activeTab, isLoading, isAuthenticated, user])

  const handleViewContestant = (contestantId: number) => {
    router.push(`/dashboard/contestants/${contestantId}`)
  }

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString)
      return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    } catch {
      return dateString
    }
  }

  // Drag and drop handlers
  const handleDragStart = (e: React.DragEvent, seasonIndex: number, voteIndex: number) => {
    setDraggedItem({ seasonIndex, voteIndex })
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const handleDrop = async (e: React.DragEvent, seasonIndex: number, dropIndex: number) => {
    e.preventDefault()
    if (!draggedItem || draggedItem.seasonIndex !== seasonIndex) {
      setDraggedItem(null)
      return
    }

    if (draggedItem.voteIndex === dropIndex) {
      setDraggedItem(null)
      return
    }

    // Réorganiser les votes dans cette season
    const newSeasonsData = [...seasonsData]
    const season = newSeasonsData[seasonIndex]
    const newVotes = [...season.votes]
    const draggedVote = newVotes[draggedItem.voteIndex]
    newVotes.splice(draggedItem.voteIndex, 1)
    newVotes.splice(dropIndex, 0, draggedVote)
    
    // Mettre à jour positions et points (1er = 5 pts … 5e = 1 pt) — même logique que le backend
    const reorderedVotes = newVotes.map((vote, index) => ({
      ...vote,
      position: index + 1,
      points: POINTS_BY_POSITION[index] ?? 1
    }))
    
    season.votes = reorderedVotes
    setSeasonsData(newSeasonsData)
    setDraggedItem(null)

    // Sauvegarder l'ordre au backend
    try {
      setIsSaving(true)
      const votesToReorder = reorderedVotes.map((vote, index) => ({
        contestant_id: vote.contestant_id,
        position: index + 1
      }))
      await contestService.reorderMyHigh5Votes(votesToReorder, season.season_id)
      addToast(t('dashboard.myhigh5.order_saved') || 'Ordre sauvegardé !', 'success')
    } catch (error) {
      console.error('Erreur lors de la sauvegarde de l\'ordre:', error)
      addToast(t('dashboard.myhigh5.order_error') || 'Erreur lors de la sauvegarde', 'error')
      // Recharger les votes en cas d'erreur
      const response = await contestService.getMyHigh5Votes() as MyHigh5Response
      setSeasonsData(response.seasons || [])
    } finally {
      setIsSaving(false)
    }
  }

  const handleDragEnd = () => {
    setDraggedItem(null)
  }

  if (isLoading || pageLoading) {
    return <MyHigh5Skeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  // Fonction helper pour rendre un tableau de votes
  const renderVotesTable = (
    votes: MyHigh5Vote[], 
    seasonIndex: number, 
    enableDragDrop: boolean = true
  ) => (
    <Table>
      <TableHeader>
        <TableRow className="bg-gray-50 dark:bg-gray-800/50">
          {enableDragDrop && <TableHead className="w-12"></TableHead>}
          <TableHead className="w-16 text-center">
            {t('dashboard.myhigh5.rank') || 'Rang'}
          </TableHead>
          <TableHead className="w-20 text-center">
            {t('dashboard.myhigh5.points') || 'Points'}
          </TableHead>
          <TableHead>
            {t('dashboard.myhigh5.contestant') || 'Contestant'}
          </TableHead>
          <TableHead className="hidden md:table-cell">
            {t('dashboard.myhigh5.location') || 'Localisation'}
          </TableHead>
          <TableHead className="hidden sm:table-cell text-center">
            {t('dashboard.myhigh5.total_votes') || 'Votes totaux'}
          </TableHead>
          <TableHead className="hidden lg:table-cell">
            {t('dashboard.myhigh5.vote_date') || 'Date du vote'}
          </TableHead>
          <TableHead className="w-12"></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {votes.map((vote, voteIndex) => (
          <TableRow
            key={vote.contestant_id}
            draggable={enableDragDrop}
            onDragStart={enableDragDrop ? (e) => handleDragStart(e, seasonIndex, voteIndex) : undefined}
            onDragOver={enableDragDrop ? handleDragOver : undefined}
            onDrop={enableDragDrop ? (e) => handleDrop(e, seasonIndex, voteIndex) : undefined}
            onDragEnd={enableDragDrop ? handleDragEnd : undefined}
            className={`
              transition-all
              ${enableDragDrop ? 'cursor-move' : ''}
              ${draggedItem?.seasonIndex === seasonIndex && draggedItem?.voteIndex === voteIndex 
                ? 'opacity-50 bg-blue-50 dark:bg-blue-900/20' 
                : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'}
              ${isSaving ? 'pointer-events-none opacity-70' : ''}
            `}
          >
            {/* Drag Handle */}
            {enableDragDrop && (
              <TableCell className="py-3">
                <div className="flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                  <GripVertical className="w-5 h-5" />
                </div>
              </TableCell>
            )}

            {/* Rank Badge */}
            <TableCell className="py-3">
              <div className="flex justify-center">
                <div className={`
                  w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg shadow-md
                  ${voteIndex === 0 ? 'bg-gradient-to-br from-yellow-400 to-yellow-600 text-white' :
                    voteIndex === 1 ? 'bg-gradient-to-br from-gray-300 to-gray-500 text-white' :
                    voteIndex === 2 ? 'bg-gradient-to-br from-amber-600 to-amber-800 text-white' :
                    'bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary text-white'}
                `}>
                  {voteIndex + 1}
                </div>
              </div>
            </TableCell>

            {/* Points: same as row rank (badge = voteIndex + 1); do not use stale vote.points */}
            <TableCell className="py-3">
              <div className="flex items-center justify-center gap-1">
                <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                <span className="font-bold text-lg text-gray-900 dark:text-white">
                  {POINTS_BY_POSITION[voteIndex] ?? 1}
                </span>
              </div>
            </TableCell>

            {/* Contestant Info */}
            <TableCell className="py-3">
              <div className="flex items-center gap-3">
                {/* Avatar */}
                <div className="w-12 h-12 rounded-full overflow-hidden bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex-shrink-0">
                  {vote.author_avatar_url ? (
                    <img
                      src={vote.author_avatar_url}
                      alt={vote.author_name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-white font-bold text-lg">
                      {vote.author_name?.charAt(0).toUpperCase() || '?'}
                    </div>
                  )}
                </div>
                {/* Name & Title */}
                <div className="min-w-0">
                  <p className="font-semibold text-gray-900 dark:text-white truncate">
                    {vote.author_name || 'Contestant'}
                  </p>
                  {vote.contestant_title && (
                    <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                      {vote.contestant_title}
                    </p>
                  )}
                </div>
              </div>
            </TableCell>

            {/* Location */}
            <TableCell className="py-3 hidden md:table-cell">
              {(vote.author_city || vote.author_country) ? (
                <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">
                  <MapPin className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">
                    {[vote.author_city, vote.author_country].filter(Boolean).join(', ')}
                  </span>
                </div>
              ) : (
                <span className="text-gray-400">-</span>
              )}
            </TableCell>

            {/* Total Votes */}
            <TableCell className="py-3 hidden sm:table-cell text-center">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                {vote.votes_count}
              </span>
            </TableCell>

            {/* Vote Date */}
            <TableCell className="py-3 hidden lg:table-cell">
              <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">
                <Calendar className="w-4 h-4" />
                <span>{formatDate(vote.vote_date)}</span>
              </div>
            </TableCell>

            {/* View Button */}
            <TableCell className="py-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  handleViewContestant(vote.contestant_id)
                }}
                className="p-2 h-auto"
              >
                <ExternalLink className="w-4 h-4" />
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
          <Hand className="w-7 h-7 text-white" />
        </div>
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            {t('dashboard.myhigh5.title') || 'MyHigh5'}
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            {t('dashboard.myhigh5.description') || 'Les 5 contestants pour lesquels vous avez voté par season'}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="active">
            <Hand className="w-4 h-4 mr-2" />
            {t('dashboard.myhigh5.active_tab') || 'Actifs'}
          </TabsTrigger>
          <TabsTrigger value="history">
            <History className="w-4 h-4 mr-2" />
            {t('dashboard.myhigh5.history_tab') || 'Historique'}
          </TabsTrigger>
        </TabsList>

        {/* Active Votes Tab */}
        <TabsContent value="active" className="space-y-6">
          {/* Hint explicatif */}
          <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700/50 rounded-lg">
            <p className="text-sm text-blue-700 dark:text-blue-300">
              {t('dashboard.myhigh5.hint_dnd') || 'Glissez-déposez pour réorganiser vos votes. Le 1er reçoit 5 points, le 2ème 4 points, le 3ème 3 points, le 4ème 2 points et le 5ème 1 point. Les votes sont limités à 5 par season.'}
            </p>
          </div>

          {/* Votes by Season */}
          {seasonsData.length === 0 ? (
        <div className="text-center py-16 bg-gray-50 dark:bg-gray-800/50 rounded-2xl">
          <Hand className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
          <h3 className="text-xl font-semibold text-gray-700 dark:text-gray-300 mb-2">
            {t('dashboard.myhigh5.no_votes') || 'Aucun vote'}
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-6">
            {t('dashboard.myhigh5.no_votes_description') || "Vous n'avez pas encore voté pour des contestants. Explorez les concours pour voter!"}
          </p>
          <Button
            onClick={() => router.push('/dashboard/contests')}
            className="bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary hover:opacity-90 text-white"
          >
            <Trophy className="w-4 h-4 mr-2" />
            {t('dashboard.myhigh5.explore_contests') || 'Explorer les concours'}
          </Button>
        </div>
      ) : (
        <div className="space-y-8">
          {seasonsData.map((season, seasonIndex) => (
            <div key={season.season_id} className="space-y-4">
              {/* Season Header */}
              <div className="flex items-center justify-between bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                    {season.contest_name || `Contest #${season.contest_id}`}
                  </h2>
                  <div className="flex items-center gap-3 mt-1">
                    {season.season_level && (
                      <span className="inline-block px-2 py-1 text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full capitalize">
                        {season.season_level}
                      </span>
                    )}
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      {season.votes_count} / 5 {t('dashboard.myhigh5.votes_label') || 'votes'}
                    </span>
                  </div>
                </div>
                {season.remaining_slots > 0 && (
                  <div className="text-right">
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {(t('dashboard.myhigh5.remaining_votes') || 'Vous pouvez encore voter pour {count} contestant(s)').replace('{count}', season.remaining_slots.toString())}
                    </p>
                  </div>
                )}
              </div>

              {/* Votes Table */}
              <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg overflow-hidden border border-gray-200 dark:border-gray-700">
                {renderVotesTable(season.votes, seasonIndex, true)}
              </div>
            </div>
          ))}
        </div>
      )}

          {/* Points Legend */}
          {seasonsData.length > 0 && (
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                {t('dashboard.myhigh5.points_legend') || 'Système de points'}
              </h3>
              <div className="flex flex-wrap gap-4">
                {[1, 2, 3, 4, 5].map((rank) => (
                  <div key={rank} className="flex items-center gap-2">
                    <div className={`
                      w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold
                      ${rank === 1 ? 'bg-gradient-to-br from-yellow-400 to-yellow-600 text-white' :
                        rank === 2 ? 'bg-gradient-to-br from-gray-300 to-gray-500 text-white' :
                        rank === 3 ? 'bg-gradient-to-br from-amber-600 to-amber-800 text-white' :
                        'bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary text-white'}
                    `}>
                      {rank}
                    </div>
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      = {POINTS_BY_POSITION[rank - 1]} {t('dashboard.myhigh5.points_label') || 'points'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="space-y-6">
          {historyLoading ? (
            <MyHigh5Skeleton />
          ) : historyData.length === 0 ? (
            <div className="text-center py-16 bg-gray-50 dark:bg-gray-800/50 rounded-2xl">
              <History className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
              <h3 className="text-xl font-semibold text-gray-700 dark:text-gray-300 mb-2">
                {t('dashboard.myhigh5.no_history') || 'Aucun historique'}
              </h3>
              <p className="text-gray-500 dark:text-gray-400">
                {t('dashboard.myhigh5.no_history_description') || "Vous n'avez pas encore d'historique de votes."}
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {historyData.map((contest) => (
                <div key={contest.contest_id} className="space-y-4">
                  {/* Contest Header */}
                  <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {contest.contest_name || `Contest #${contest.contest_id}`}
                    </h2>
                  </div>

                  {/* Seasons for this contest */}
                  {contest.seasons.map((season, seasonIndex) => {
                    // Créer un index unique pour cette season dans l'historique
                    const uniqueIndex = contest.contest_id * 1000 + season.season_id
                    return (
                      <div key={season.season_id} className="space-y-3">
                        {/* Season Header */}
                        <div className="flex items-center justify-between bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                          <div className="flex items-center gap-3">
                            {season.season_level && (
                              <span className="inline-block px-2 py-1 text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full capitalize">
                                {season.season_level}
                              </span>
                            )}
                            <span className="text-sm text-gray-500 dark:text-gray-400">
                              {season.votes_count} {t('dashboard.myhigh5.votes_label') || 'votes'}
                            </span>
                            {!season.is_active && (
                              <span className="inline-block px-2 py-1 text-xs font-medium bg-gray-300 dark:bg-gray-600 text-gray-600 dark:text-gray-300 rounded-full">
                                {t('dashboard.myhigh5.inactive') || 'Terminé'}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Votes Table */}
                        {season.votes.length > 0 && (
                          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg overflow-hidden border border-gray-200 dark:border-gray-700">
                            {renderVotesTable(season.votes, uniqueIndex, false)}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
