/**
 * Align with backend `_normalize_contest_mode`: nomination vs participation for tabs and CTAs.
 */
export type ContestModeTab = 'nomination' | 'participation'

export function normalizeContestMode(mode: unknown): ContestModeTab {
  if (mode == null || mode === '') return 'participation'
  const value = typeof mode === 'object' && mode !== null && 'value' in mode ? (mode as { value: unknown }).value : mode
  const text = String(value).trim().replace(/^['"]|['"]$/g, '')
  if (!text) return 'participation'
  const low = text.toLowerCase()
  const token = low.includes('.') ? low.split('.').pop()!.trim() : low
  if (token === 'nomination' || token === 'nominate') return 'nomination'
  if (token === 'participation' || token === 'participant') return 'participation'
  if (low.includes('nomination') && !low.includes('participation')) return 'nomination'
  return 'participation'
}

/** Align with backend `_normalize_entry_type_query` for ?entryType= URL params. */
export function normalizeEntryTypeQueryParam(raw: string | null | undefined): string | undefined {
  if (raw == null || raw === '') return undefined
  const s = String(raw).trim().toLowerCase()
  if (!s || s === 'all') return undefined
  if (s === 'nominations' || s === 'nomination' || s === 'nominate') return 'nomination'
  if (
    s === 'participations' ||
    s === 'participation' ||
    s === 'participate' ||
    s === 'participant'
  ) {
    return 'participation'
  }
  return undefined
}
