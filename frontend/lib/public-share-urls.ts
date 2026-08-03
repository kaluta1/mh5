/** Map dashboard / share preview paths to public viewer routes (no login required). */
export function toPublicSharePath(pathname: string): string {
  const feedMatch = pathname.match(/^\/dashboard\/feed\/(\d+)$/)
  if (feedMatch) return `/feed/${feedMatch[1]}`

  const feedShareMatch = pathname.match(/^\/s\/f\/(\d+)$/)
  if (feedShareMatch) return `/feed/${feedShareMatch[1]}`

  const contestantDashboardMatch = pathname.match(/^\/dashboard\/contests\/\d+\/contestant\/(\d+)$/)
  if (contestantDashboardMatch) return `/contestants/${contestantDashboardMatch[1]}`

  const contestantShareMatch = pathname.match(/^\/s\/c\/(\d+)$/)
  if (contestantShareMatch) return `/contestants/${contestantShareMatch[1]}`

  const contestantShortMatch = pathname.match(/^\/c\/(\d+)$/)
  if (contestantShortMatch) return `/contestants/${contestantShortMatch[1]}`

  return pathname
}

export function publicFeedPostPath(postId: number | string): string {
  return `/feed/${postId}`
}

export function publicContestantPath(contestantId: number | string): string {
  return `/contestants/${contestantId}`
}
