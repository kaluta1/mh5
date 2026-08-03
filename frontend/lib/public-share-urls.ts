/** Map dashboard / share preview paths to public viewer routes (no login required). */
export type ContestantShareContext = {
  contestId: string | number
  roundId?: string | number
  contestLevel?: string | null
  country?: string | null
  region?: string | null
  continent?: string | null
  entryType?: string | null
  rosterOnly?: string | boolean | null
}

export function buildPublicContestantEntryUrl(
  origin: string,
  contestantId: string | number,
  ctx: ContestantShareContext,
  ref?: string | null
): string {
  const params = new URLSearchParams()
  if (ctx.roundId != null && String(ctx.roundId) !== '') params.set('roundId', String(ctx.roundId))
  if (ctx.contestLevel) params.set('contestLevel', ctx.contestLevel)
  if (ctx.country && ctx.country !== 'all') params.set('country', ctx.country)
  if (ctx.region && ctx.region !== 'all') params.set('region', ctx.region)
  if (ctx.continent && ctx.continent !== 'all') params.set('continent', ctx.continent)
  if (ctx.entryType) params.set('entryType', ctx.entryType)
  if (ctx.rosterOnly === false || ctx.rosterOnly === 'false') params.set('rosterOnly', 'false')
  else if (ctx.rosterOnly === true || ctx.rosterOnly === 'true') params.set('rosterOnly', 'true')
  if (ref) params.set('ref', ref)
  const qs = params.toString()
  return `${origin.replace(/\/+$/, '')}/contests/${ctx.contestId}/entry/${contestantId}${qs ? `?${qs}` : ''}`
}

export function toPublicSharePath(pathname: string): string {
  const entryMatch = pathname.match(/^\/dashboard\/contests\/(\d+)\/contestant\/(\d+)$/)
  if (entryMatch) {
    return `/contests/${entryMatch[1]}/entry/${entryMatch[2]}`
  }

  const feedMatch = pathname.match(/^\/dashboard\/feed\/(\d+)$/)
  if (feedMatch) return `/feed/${feedMatch[1]}`

  const feedShareMatch = pathname.match(/^\/s\/f\/(\d+)$/)
  if (feedShareMatch) return `/feed/${feedShareMatch[1]}`

  const contestantShareMatch = pathname.match(/^\/s\/c\/(\d+)$/)
  if (contestantShareMatch) return `/contestants/${contestantShareMatch[1]}`

  const contestantShortMatch = pathname.match(/^\/c\/(\d+)$/)
  if (contestantShortMatch) return `/contestants/${contestantShortMatch[1]}`

  const legacyContestantMatch = pathname.match(/^\/contestants\/(\d+)$/)
  if (legacyContestantMatch) return pathname

  return pathname
}

export function publicFeedPostPath(postId: number | string): string {
  return `/feed/${postId}`
}

export function publicContestantEntryPath(
  contestId: number | string,
  contestantId: number | string,
  query?: string
): string {
  const qs = query ? (query.startsWith('?') ? query : `?${query}`) : ''
  return `/contests/${contestId}/entry/${contestantId}${qs}`
}

/** @deprecated Use buildPublicContestantEntryUrl with contest context instead. */
export function publicContestantPath(contestantId: number | string): string {
  return `/contestants/${contestantId}`
}
