'use client'

import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import api from '@/lib/api'

export interface SeasonContestOption {
  id: number
  name: string
  contest_mode?: string | null
}

export interface EntryContestResolution {
  /** contest_id to send with POST /admin/contestants (null = none can be sent yet). */
  contestId: number | null
  /** The admin has to pick one (the season is shared by several contests). */
  selectionRequired: boolean
  /** Creation may be submitted with this resolution. */
  ready: boolean
}

/**
 * Which contest a new admin-created entry belongs to. One valid contest is
 * used automatically; several require an explicit choice among THEM only (a
 * stale or foreign choice is never sent); none cannot be created. The backend
 * re-validates the pair and remains authoritative.
 */
export function resolveEntryContest(
  contests: SeasonContestOption[] | null,
  selected: string,
): EntryContestResolution {
  if (!contests || contests.length === 0) return { contestId: null, selectionRequired: false, ready: false }
  if (contests.length === 1) return { contestId: contests[0].id, selectionRequired: false, ready: true }
  const chosen = contests.find((c) => String(c.id) === selected)
  return { contestId: chosen ? chosen.id : null, selectionRequired: true, ready: Boolean(chosen) }
}

interface Props {
  seasonId: string
  value: string
  onChange: (contestId: string) => void
  onResolved: (resolution: EntryContestResolution) => void
}

/** Contest selector for admin contestant creation, shown only when needed. */
export function AdminEntryContestField({ seasonId, value, onChange, onResolved }: Props) {
  const [contests, setContests] = useState<SeasonContestOption[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  // A season change always drops the previous contest choice and reloads the
  // contests valid for the new season.
  useEffect(() => {
    let cancelled = false
    onChange('')
    setContests(null)
    setError(false)
    if (!seasonId) return
    setLoading(true)
    api
      .get<SeasonContestOption[]>(`/api/v1/admin/seasons/${seasonId}/contests`)
      .then((response) => {
        if (!cancelled) setContests(Array.isArray(response.data) ? response.data : [])
      })
      .catch(() => {
        if (!cancelled) {
          setContests([])
          setError(true)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seasonId])

  const resolution = resolveEntryContest(contests, value)
  useEffect(() => {
    onResolved(resolution)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolution.contestId, resolution.selectionRequired, resolution.ready])

  if (!seasonId) return null
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading contests...
      </div>
    )
  }
  if (!contests) return null
  if (contests.length === 0) {
    return (
      <p role="alert" className="text-sm text-red-600 dark:text-red-400">
        {error
          ? 'Could not load the contests for this season.'
          : 'This season is not linked to any contest, so an entry cannot be created in it.'}
      </p>
    )
  }
  if (contests.length === 1) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-400" data-testid="entry-contest-auto">
        Contest: {contests[0].name}
      </p>
    )
  }
  return (
    <div>
      <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
        Contest <span className="text-red-500">*</span>
      </label>
      <Select value={value} onValueChange={onChange} required>
        <SelectTrigger aria-label="Contest" className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
          <SelectValue placeholder="Select the contest for this entry" />
        </SelectTrigger>
        <SelectContent>
          {contests.map((c) => (
            <SelectItem key={c.id} value={String(c.id)}>
              {c.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        This season is shared by several contests. Choose the one this entry belongs to.
      </p>
    </div>
  )
}
