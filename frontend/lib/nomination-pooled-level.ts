/** Client-side guard when backend returns wrong season for pooled vote levels. */
export function rosterMatchesRequestedPooledLevel(
  rows: { season?: { level?: string } }[],
  requestedLevel: string,
): boolean {
  const req = requestedLevel.toLowerCase()
  if (req === 'regional' || req === 'region' || req === 'continental' || req === 'continent' || req === 'global') {
    if (!rows.length) return true
    const seasonLevel = String(rows[0]?.season?.level || '').toLowerCase()
    if (!seasonLevel) return false
    if (req === 'regional' || req === 'region') {
      return seasonLevel === 'regional' || seasonLevel === 'region'
    }
    if (req === 'continental' || req === 'continent') {
      return seasonLevel === 'continental' || seasonLevel === 'continent'
    }
    if (req === 'global') return seasonLevel === 'global'
  }
  return true
}

export function pooledNominationRosterCount(
  rows: { season?: { level?: string } }[],
  requestedLevel: string,
): number {
  if (!rows.length) return 0
  if (!rosterMatchesRequestedPooledLevel(rows, requestedLevel)) return 0
  return rows.length
}
