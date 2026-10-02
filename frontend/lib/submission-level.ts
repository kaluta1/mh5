/**
 * Initial competition level of a NEW submission (management rule, 2026-10-02):
 *
 *   nomination     -> Country
 *   participation  -> City
 *
 * The submitter never chooses it; Regional / Continental / Global are reached
 * only through voting. The backend is authoritative (it rejects a submission
 * that names another level); this module only decides what the dashboard shows.
 */
export type ContestsTabKind = 'nominate' | 'vote'
export type ContestsCategoryTab = 'nomination' | 'participations'
export type SubmissionLevel = 'country' | 'city'

export function initialSubmissionLevel(mode: unknown): SubmissionLevel {
  return String(mode ?? '').trim().toLowerCase() === 'nomination' ? 'country' : 'city'
}

/**
 * Whether the competition-stage chips (City / Country / Regional / Continental /
 * Global) belong on the contests dashboard right now.
 *
 * They are a VOTE control: each chip is a stage whose cohort is being voted on.
 * In the Submit view (`kind === 'nominate'`, for both the Nominate and the
 * Participations category) there is no stage to pick, so they are never shown.
 */
export function showCompetitionStageSelector(opts: {
  kind: ContestsTabKind | undefined
  categoryTab: ContestsCategoryTab
  /** Nomination vote chips also need a live voting-round context. */
  showVoteGeographyLevels: boolean
}): boolean {
  if (opts.kind !== 'vote') return false
  if (opts.categoryTab === 'nomination') return opts.showVoteGeographyLevels
  return true
}

/**
 * The stage filter a view may keep. Submit always shows every contest of the
 * selected month, so a stage picked earlier in Vote must not keep filtering it.
 */
export function stageFilterForView<T extends string>(
  kind: ContestsTabKind | undefined,
  current: T | 'all',
): T | 'all' {
  return kind === 'vote' ? current : 'all'
}
