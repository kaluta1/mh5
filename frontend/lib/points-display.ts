/**
 * Voting points are cumulative across the phases of a contest: the score an
 * entry is ranked on is the points carried from the stages it already passed
 * plus the points earned in the current stage. The API sends the three numbers
 * (total_points / carried_points / stage_points); nothing is computed here
 * beyond presentation.
 */
export interface PointsBreakdown {
  total: number
  carried: number
  stage: number
}

const toCount = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
}

export function pointsBreakdown(
  total: unknown,
  carried?: unknown,
  stage?: unknown,
): PointsBreakdown {
  const totalPoints = toCount(total)
  const carriedPoints = Math.min(toCount(carried), totalPoints)
  // Older API responses carry no breakdown: the whole score is the stage score.
  const stagePoints = stage === undefined || stage === null ? totalPoints - carriedPoints : toCount(stage)
  return { total: totalPoints, carried: carriedPoints, stage: stagePoints }
}

/**
 * "17 pts" while nothing is carried, "17 pts (5 + 12)" once an earlier stage
 * contributes: carried points first, then the points of the current stage.
 */
export function formatPoints(
  total: unknown,
  carried?: unknown,
  stage?: unknown,
  unit = 'pts',
): string {
  const b = pointsBreakdown(total, carried, stage)
  const base = `${b.total} ${unit}`
  return b.carried > 0 ? `${base} (${b.carried} + ${b.stage})` : base
}
