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
