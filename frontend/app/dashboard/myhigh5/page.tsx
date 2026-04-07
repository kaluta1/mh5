'use client'

import * as React from "react"
import { useState, useEffect, useSyncExternalStore } from "react"
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import { useToast } from '@/components/ui/toast'
import { contestService } from '@/services/contest-service'
import { Hand, Trophy, MapPin, Calendar, ExternalLink, Star, History, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
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
  /** Contest title for this vote row (if several contests share one MyHigh5 bucket) */
  voted_contest_name?: string | null
  season_level: string | null
}

interface SeasonVotes {
  season_id: number
  season_level: string | null
  contest_id: number
  contest_name: string | null
  category_id?: number | null
  category_name?: string | null
  /** When category FK is missing on contests, backend scopes MyHigh5 by this + contest_mode */
  contest_type?: string | null
  /** Backend bucket key; stable id for expand/collapse when multiple contests share a category */
  vote_bucket_key?: string | null
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
  category_id?: number | null
  category_name?: string | null
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

function subscribeCoarsePointer(cb: () => void) {
  if (typeof window === "undefined") return () => {}
  const mq = window.matchMedia("(pointer: coarse)")
  mq.addEventListener("change", cb)
  return () => mq.removeEventListener("change", cb)
}

function getCoarsePointerSnapshot() {
  return typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches
}

function getServerCoarsePointerSnapshot() {
  return false
}

function useCoarsePointer() {
  return useSyncExternalStore(subscribeCoarsePointer, getCoarsePointerSnapshot, getServerCoarsePointerSnapshot)
}

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
  /** Touch / coarse pointer: first tap selects row, second tap on another row moves there (same as drag-drop). */
  const [touchReorderSource, setTouchReorderSource] = useState<{
    seasonIndex: number
    voteIndex: number
  } | null>(null)
  const isCoarsePointer = useCoarsePointer()
  const [isSaving, setIsSaving] = useState(false)
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())

  const sectionKey = (season: SeasonVotes) =>
    `${season.season_id}-${season.vote_bucket_key ?? `c${season.contest_id}`}`

  const toggleSection = (key: string) => {
    setOpenSections((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

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

  // Rafraîchir la liste quand un vote / remplacement est fait ailleurs (même flux que My votes)
  useEffect(() => {
    const handler = async () => {
      try {
        const response = await contestService.getMyHigh5Votes() as MyHigh5Response
        setSeasonsData(response.seasons || [])
      } catch (error) {
        console.error('Erreur lors du rafraîchissement des votes:', error)
      }
    }
    window.addEventListener('vote-changed', handler)
    return () => window.removeEventListener('vote-changed', handler)
  }, [])

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
  const applyReorder = async (seasonIndex: number, fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex) return

    const newSeasonsData = [...seasonsData]
    const season = newSeasonsData[seasonIndex]
    const newVotes = [...season.votes]
    const moved = newVotes[fromIndex]
    newVotes.splice(fromIndex, 1)
    newVotes.splice(toIndex, 0, moved)

    const reorderedVotes = newVotes.map((vote, index) => ({
      ...vote,
      position: index + 1,
      points: POINTS_BY_POSITION[index] ?? 1,
    }))

    season.votes = reorderedVotes
    setSeasonsData(newSeasonsData)

    try {
      setIsSaving(true)
      const votesToReorder = reorderedVotes.map((vote, index) => ({
        contestant_id: vote.contestant_id,
        position: index + 1,
      }))
      await contestService.reorderMyHigh5Votes(votesToReorder, season.season_id, season.contest_id)
      addToast(t('dashboard.myhigh5.order_saved') || 'Ordre sauvegardé !', 'success')
    } catch (error) {
      console.error('Erreur lors de la sauvegarde de l\'ordre:', error)
      addToast(t('dashboard.myhigh5.order_error') || 'Erreur lors de la sauvegarde', 'error')
      const response = await contestService.getMyHigh5Votes() as MyHigh5Response
      setSeasonsData(response.seasons || [])
    } finally {
      setIsSaving(false)
    }
  }

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

    const from = draggedItem.voteIndex
    setDraggedItem(null)
    await applyReorder(seasonIndex, from, dropIndex)
  }

  const handleDragEnd = () => {
    setDraggedItem(null)
  }

  const handleAvatarTapReorder = (
    e: React.MouseEvent,
    seasonIndex: number,
    voteIndex: number
  ) => {
    e.preventDefault()
    e.stopPropagation()
    if (isSaving) return

    if (!touchReorderSource) {
      setTouchReorderSource({ seasonIndex, voteIndex })
      return
    }
    if (touchReorderSource.seasonIndex !== seasonIndex) {
      setTouchReorderSource({ seasonIndex, voteIndex })
      return
    }
    if (touchReorderSource.voteIndex === voteIndex) {
      setTouchReorderSource(null)
      return
    }

    const from = touchReorderSource.voteIndex
    setTouchReorderSource(null)
    void applyReorder(seasonIndex, from, voteIndex)
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
  ) => {
    const dragEnabled = enableDragDrop && !isCoarsePointer
    const touchReorderEnabled = enableDragDrop && isCoarsePointer

    return (
    <Table>
      <TableHeader>
        <TableRow className="bg-gray-50 dark:bg-gray-800/50">
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
            onDragOver={dragEnabled ? handleDragOver : undefined}
            onDrop={dragEnabled ? (e) => handleDrop(e, seasonIndex, voteIndex) : undefined}
            className={cn(
              'transition-all',
              draggedItem?.seasonIndex === seasonIndex && draggedItem?.voteIndex === voteIndex
                ? 'opacity-50 bg-blue-50 dark:bg-blue-900/20'
                : 'hover:bg-gray-50 dark:hover:bg-gray-700/50',
              touchReorderSource?.seasonIndex === seasonIndex &&
                touchReorderSource?.voteIndex === voteIndex &&
                'bg-myhigh5-primary/10 ring-2 ring-inset ring-myhigh5-primary/50 dark:bg-myhigh5-primary/20',
              isSaving && 'pointer-events-none opacity-70'
            )}
          >
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

            {/* Contestant Info — drag: grab avatar only; High5 hand shows on hover */}
            <TableCell className="py-3">
              <div className="flex items-center gap-3">
                <div
                  role={touchReorderEnabled ? 'button' : undefined}
                  tabIndex={touchReorderEnabled ? 0 : undefined}
                  onKeyDown={
                    touchReorderEnabled
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            handleAvatarTapReorder(e as unknown as React.MouseEvent, seasonIndex, voteIndex)
                          }
                        }
                      : undefined
                  }
                  className={cn(
                    'group relative h-12 w-12 flex-shrink-0 overflow-hidden rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary',
                    dragEnabled && 'cursor-grab active:cursor-grabbing',
                    touchReorderEnabled && 'cursor-pointer touch-manipulation',
                    enableDragDrop && isSaving && 'pointer-events-none opacity-60'
                  )}
                  draggable={dragEnabled}
                  onDragStart={
                    dragEnabled
                      ? (e) => {
                          handleDragStart(e, seasonIndex, voteIndex)
                        }
                      : undefined
                  }
                  onDragEnd={dragEnabled ? handleDragEnd : undefined}
                  onClick={
                    touchReorderEnabled
                      ? (e) => handleAvatarTapReorder(e, seasonIndex, voteIndex)
                      : undefined
                  }
                  title={
                    enableDragDrop
                      ? touchReorderEnabled
                        ? t('dashboard.myhigh5.tap_reorder') ||
                          'Tap to select, then tap another photo to reorder'
                        : t('dashboard.myhigh5.drag_reorder') || 'Drag on the photo to reorder your High5'
                      : undefined
                  }
                  aria-label={
                    enableDragDrop
                      ? touchReorderEnabled
                        ? `${t('dashboard.myhigh5.tap_reorder') || 'Tap to select, then tap another photo to reorder'} — ${vote.author_name || 'Contestant'}`
                        : t('dashboard.myhigh5.drag_reorder') || 'Drag profile photo to reorder your High5'
                      : vote.author_name || 'Contestant'
                  }
                >
                  {vote.author_avatar_url ? (
                    <img
                      src={vote.author_avatar_url}
                      alt=""
                      draggable={false}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-lg font-bold text-white">
                      {vote.author_name?.charAt(0).toUpperCase() || '?'}
                    </div>
                  )}
                  {enableDragDrop && (
                    <div
                      className={cn(
                        'pointer-events-none absolute inset-0 flex items-center justify-center rounded-full bg-gradient-to-br from-myhigh5-primary/90 to-myhigh5-secondary/90 transition-opacity duration-150',
                        isCoarsePointer
                          ? 'opacity-50'
                          : 'opacity-0 group-hover:opacity-100'
                      )}
                      aria-hidden
                    >
                      <Hand className="h-6 w-6 text-white drop-shadow-sm" strokeWidth={2.25} />
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
                  {vote.voted_contest_name && (
                    <p className="text-xs text-gray-500 dark:text-gray-500 truncate" title={vote.voted_contest_name}>
                      {vote.voted_contest_name}
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
  }

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
            {t('dashboard.myhigh5.description') || 'Vos 5 votes par concours et par saison — chaque catégorie apparaît dans sa propre section.'}
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
          <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700/50 rounded-lg space-y-1">
            <p className="text-sm text-blue-700 dark:text-blue-300">
              {t('dashboard.myhigh5.hint_categories') || 'Only categories where you have cast at least one vote are listed. Click a section to expand your votes.'}
            </p>
            <p className="text-sm text-blue-700 dark:text-blue-300">
              {isCoarsePointer
                ? t('dashboard.myhigh5.hint_tap') ||
                  'Tap a contestant’s profile photo to select them, then tap another photo to move them to that rank. Tap the same photo again to cancel.'
                : t('dashboard.myhigh5.hint_dnd') ||
                  'Hover a contestant’s profile photo to see the High5 hand, then drag from the photo to reorder. 1st place = 5 points … 5th = 1. Max 5 votes per category.'}
            </p>
            {isCoarsePointer && touchReorderSource && (
              <p className="text-sm font-medium text-amber-800 dark:text-amber-200 pt-1">
                {(t('dashboard.myhigh5.tap_reorder_second') ||
                  'Tap another contestant’s photo to move {name} to that position.').replace(
                  '{name}',
                  seasonsData[touchReorderSource.seasonIndex]?.votes[touchReorderSource.voteIndex]?.author_name ||
                    '…'
                )}
              </p>
            )}
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
        <div className="space-y-3">
          {seasonsData.map((season, seasonIndex) => {
            const sk = sectionKey(season)
            const isOpen = openSections.has(sk)
            return (
              <div
                key={sk}
                className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/40 overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => toggleSection(sk)}
                  aria-expanded={isOpen}
                  className="w-full flex items-center justify-between gap-3 text-left p-4 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100/80 dark:hover:bg-gray-800 transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    {season.category_name && (
                      <p className="text-sm font-semibold text-myhigh5-primary dark:text-myhigh5-secondary mb-0.5">
                        {season.category_name}
                      </p>
                    )}
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white truncate">
                      {season.contest_name || `Contest #${season.contest_id}`}
                    </h2>
                    <div className="flex flex-wrap items-center gap-2 mt-1">
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
                  <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
                    {season.remaining_slots > 0 && (
                      <p className="text-xs sm:text-sm text-gray-600 dark:text-gray-400 text-right max-w-[min(100%,14rem)]">
                        {(t('dashboard.myhigh5.remaining_votes') || 'Vous pouvez encore voter pour {count} contestant(s)').replace('{count}', season.remaining_slots.toString())}
                      </p>
                    )}
                    <ChevronDown
                      className={cn(
                        'w-5 h-5 text-gray-500 flex-shrink-0 transition-transform',
                        isOpen && 'rotate-180'
                      )}
                      aria-hidden
                    />
                  </div>
                </button>
                {isOpen && (
                  <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-4">
                    {season.votes.length === 0 ? (
                      <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-8">
                        {t('dashboard.myhigh5.no_votes_in_category') || 'You have not voted in this category yet.'}
                      </p>
                    ) : (
                      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg overflow-hidden border border-gray-200 dark:border-gray-700">
                        {renderVotesTable(season.votes, seasonIndex, true)}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

          {/* Points Legend — only when at least one category has votes */}
          {seasonsData.some((s) => s.votes_count > 0) && (
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
                    {contest.category_name && (
                      <p className="text-sm font-semibold text-myhigh5-primary dark:text-myhigh5-secondary mb-0.5">
                        {contest.category_name}
                      </p>
                    )}
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {contest.contest_name || `Contest #${contest.contest_id}`}
                    </h2>
                  </div>

                  {/* Seasons for this contest */}
                  {contest.seasons.map((season, seasonIndex) => {
                    // Créer un index unique pour cette season dans l'historique
                    const uniqueIndex = contest.contest_id * 1000 + season.season_id
                    return (
                      <div key={`${contest.contest_id}-${season.season_id}`} className="space-y-3">
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
