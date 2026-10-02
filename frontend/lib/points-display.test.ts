import { describe, expect, it } from 'vitest'

import { formatPoints, pointsBreakdown } from './points-display'

describe('cumulative voting score display', () => {
  it('shows only the total while no earlier stage contributes', () => {
    expect(formatPoints(20, 0, 20)).toBe('20 pts')
    expect(formatPoints(0, 0, 0)).toBe('0 pts')
  })

  it('shows carried + current stage once points are carried forward', () => {
    // Country 120, Regional +40 -> ranked on 160.
    expect(formatPoints(160, 120, 40)).toBe('160 pts (120 + 40)')
    // Carried only: the previous score still stands in a stage with no new vote.
    expect(formatPoints(20, 20, 0)).toBe('20 pts (20 + 0)')
  })

  it('never restarts the displayed score from zero at a new stage', () => {
    const b = pointsBreakdown(17, 5, 12)
    expect(b).toEqual({ total: 17, carried: 5, stage: 12 })
    expect(b.carried + b.stage).toBe(b.total)
  })

  it('stays correct with an older response that has no breakdown', () => {
    expect(pointsBreakdown(9)).toEqual({ total: 9, carried: 0, stage: 9 })
    expect(formatPoints(9)).toBe('9 pts')
    expect(formatPoints(undefined)).toBe('0 pts')
    expect(formatPoints(null, null, null)).toBe('0 pts')
  })

  it('ignores malformed numbers instead of rendering NaN', () => {
    expect(formatPoints('abc', 'x', 'y')).toBe('0 pts')
    expect(formatPoints(10, 99, 1)).toBe('10 pts (10 + 1)')
    expect(formatPoints(12, 2, 10, 'points')).toBe('12 points (2 + 10)')
  })
})
