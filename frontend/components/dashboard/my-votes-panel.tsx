'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { Trophy, GripVertical, X, ChevronDown, ChevronUp } from 'lucide-react'
import { contestService } from '@/services/contest-service'
import { useLanguage } from '@/contexts/language-context'
import Image from 'next/image'

const POINTS_BY_POSITION = [5, 4, 3, 2, 1]

interface MyVote {
  position: number
  points: number | null
  contestant_id: number
  contestant_title: string
  author_name: string | null
  author_avatar_url: string | null
  votes_count: number
  season_id: number
  contest_id: number
}

interface MyVotesPanelProps {
  contestId: number
  onVoteChanged?: () => void
}

export default function MyVotesPanel({ contestId, onVoteChanged }: MyVotesPanelProps) {
  const { t } = useLanguage()
  const [votes, setVotes] = useState<MyVote[]>([])
  const [seasonId, setSeasonId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [collapsed, setCollapsed] = useState(false)
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  const fetchVotes = useCallback(async () => {
    try {
      const data = await contestService.getMyVotesForContest(contestId)
      if (data.seasons && data.seasons.length > 0) {
        const season = data.seasons[0]
        setVotes(season.votes || [])
        setSeasonId(season.season_id)
      } else {
        setVotes([])
      }
    } catch (error) {
      console.error('Error fetching votes:', error)
    } finally {
      setLoading(false)
    }
  }, [contestId])

  useEffect(() => {
    fetchVotes()
  }, [fetchVotes])

  // Écouter les événements de vote pour rafraîchir
  useEffect(() => {
    const handler = () => fetchVotes()
    window.addEventListener('vote-changed', handler)
    return () => window.removeEventListener('vote-changed', handler)
  }, [fetchVotes])

  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDraggedIndex(index)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(index))
  }

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverIndex(index)
  }

  const handleDragLeave = () => {
    setDragOverIndex(null)
  }

  const handleDrop = async (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault()
    setDragOverIndex(null)

    if (draggedIndex === null || draggedIndex === dropIndex) {
      setDraggedIndex(null)
      return
    }

    // Réordonner localement
    const newVotes = [...votes]
    const [movedVote] = newVotes.splice(draggedIndex, 1)
    newVotes.splice(dropIndex, 0, movedVote)

    // Mettre à jour les positions et points
    const updatedVotes = newVotes.map((vote, idx) => ({
      ...vote,
      position: idx + 1,
      points: POINTS_BY_POSITION[idx] || 1
    }))

    setVotes(updatedVotes)
    setDraggedIndex(null)

    // Sauvegarder au backend
    if (seasonId) {
      try {
        setSaving(true)
        await contestService.reorderMyHigh5Votes(
          updatedVotes.map(v => ({
            contestant_id: v.contestant_id,
            position: v.position
          })),
          seasonId,
          contestId
        )
        onVoteChanged?.()
        // Émettre un événement global pour synchroniser
        window.dispatchEvent(new Event('vote-changed'))
      } catch (error) {
        console.error('Error reordering votes:', error)
        // Recharger en cas d'erreur
        fetchVotes()
      } finally {
        setSaving(false)
      }
    }
  }

  const handleDragEnd = () => {
    setDraggedIndex(null)
    setDragOverIndex(null)
  }

  if (loading) {
    return (
      <div className="rounded-xl bg-white dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700/50 p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded w-32" />
          <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded" />
        </div>
      </div>
    )
  }

  if (votes.length === 0) {
    return (
      <div className="rounded-xl bg-gradient-to-br from-blue-50 to-cyan-50 dark:from-blue-950/30 dark:to-cyan-950/30 border border-blue-200/50 dark:border-blue-800/30 p-4">
        <div className="flex items-center gap-2 mb-2">
          <Trophy className="w-4 h-4 text-myhigh5-primary dark:text-white" />
          <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            {t('dashboard.contests.my_votes') || 'Mes votes'} (0/5)
          </span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {t('dashboard.contests.no_votes_yet') || 'Votez pour vos contestants préférés !'}
        </p>
      </div>
    )
  }

  return (
    <div
      ref={panelRef}
      className="rounded-xl bg-white dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700/50 shadow-sm overflow-hidden"
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gradient-to-r from-myhigh5-primary/10 to-myhigh5-secondary/10 dark:from-myhigh5-primary/20 dark:to-myhigh5-secondary/20 hover:from-myhigh5-primary/15 hover:to-myhigh5-secondary/15 transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-2">
          <Trophy className="w-4 h-4 text-myhigh5-primary dark:text-white" />
          <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            {t('dashboard.contests.my_votes') || 'Mes votes'} ({votes.length}/5)
          </span>
          {saving && (
            <span className="text-[10px] text-myhigh5-primary dark:text-white animate-pulse">
              ...
            </span>
          )}
        </div>
        {collapsed ? (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        )}
      </button>

      {/* Vote list */}
      {!collapsed && (
        <div className="p-2 space-y-1">
          {votes.map((vote, index) => (
            <div
              key={vote.contestant_id}
              draggable
              onDragStart={(e) => handleDragStart(e, index)}
              onDragOver={(e) => handleDragOver(e, index)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, index)}
              onDragEnd={handleDragEnd}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-grab active:cursor-grabbing transition-all ${
                draggedIndex === index
                  ? 'opacity-50 scale-95'
                  : dragOverIndex === index
                  ? 'bg-myhigh5-primary/10 border border-myhigh5-primary/30 border-dashed'
                  : 'bg-gray-50 dark:bg-gray-700/30 hover:bg-gray-100 dark:hover:bg-gray-700/50'
              }`}
            >
              {/* Drag handle */}
              <GripVertical className="w-3.5 h-3.5 text-gray-300 dark:text-gray-600 flex-shrink-0" />

              {/* Position badge */}
              <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold ${
                index === 0
                  ? 'bg-yellow-400 text-yellow-900'
                  : index === 1
                  ? 'bg-gray-300 dark:bg-gray-500 text-gray-700 dark:text-gray-200'
                  : index === 2
                  ? 'bg-amber-600 text-white'
                  : 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300'
              }`}>
                {index + 1}
              </div>

              {/* Avatar */}
              <div className="w-6 h-6 rounded-full overflow-hidden flex-shrink-0 bg-gray-200 dark:bg-gray-600">
                {vote.author_avatar_url ? (
                  <Image
                    src={vote.author_avatar_url}
                    alt=""
                    width={24}
                    height={24}
                    className="object-cover w-full h-full"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-[8px] text-gray-400">
                    {(vote.author_name || '?')[0]}
                  </div>
                )}
              </div>

              {/* Name */}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">
                  {vote.contestant_title || vote.author_name || 'Contestant'}
                </p>
              </div>

              {/* Points */}
              <span className={`text-xs font-bold flex-shrink-0 ${
                index === 0
                  ? 'text-yellow-600 dark:text-yellow-400'
                  : 'text-myhigh5-primary dark:text-white'
              }`}>
                {POINTS_BY_POSITION[index] || 1}pt{POINTS_BY_POSITION[index] !== 1 ? 's' : ''}
              </span>
            </div>
          ))}

          {/* Empty slots */}
          {Array.from({ length: 5 - votes.length }).map((_, i) => (
            <div
              key={`empty-${i}`}
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg border border-dashed border-gray-200 dark:border-gray-700"
            >
              <div className="w-3.5 h-3.5" />
              <div className="w-5 h-5 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-[10px] text-gray-400">
                {votes.length + i + 1}
              </div>
              <span className="text-xs text-gray-400 dark:text-gray-500 italic">
                {t('dashboard.contests.empty_slot') || 'Emplacement vide'}
              </span>
            </div>
          ))}

          {/* Info */}
          {votes.length < 5 && (
            <p className="text-[10px] text-gray-400 dark:text-gray-500 text-center pt-1">
              {t('dashboard.contests.votes_remaining')?.replace('{n}', String(5 - votes.length)) || `${5 - votes.length} vote(s) restant(s)`}
            </p>
          )}
          {votes.length > 1 && (
            <p className="text-[10px] text-gray-400 dark:text-gray-500 text-center pt-1">
              {t('dashboard.contests.drag_to_reorder') || 'Glissez pour réordonner'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
