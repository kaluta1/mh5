import { describe, expect, it } from 'vitest'
import {
  pooledNominationRosterCount,
  rosterMatchesRequestedPooledLevel,
} from './nomination-pooled-level'

describe('nomination-pooled-level', () => {
  it('accepts matching regional season', () => {
    const rows = [{ season: { level: 'regional' } }]
    expect(rosterMatchesRequestedPooledLevel(rows, 'regional')).toBe(true)
    expect(pooledNominationRosterCount(rows, 'regional')).toBe(1)
  })

  it('rejects country season on continental tab', () => {
    const rows = [{ season: { level: 'country' } }, { season: { level: 'country' } }]
    expect(rosterMatchesRequestedPooledLevel(rows, 'continental')).toBe(false)
    expect(pooledNominationRosterCount(rows, 'continental')).toBe(0)
  })

  it('returns zero for empty rows', () => {
    expect(pooledNominationRosterCount([], 'regional')).toBe(0)
  })

  it('accepts rows when season level is missing (legacy API rows)', () => {
    const rows = [{ season: {} }, { season: {} }]
    expect(rosterMatchesRequestedPooledLevel(rows, 'continental')).toBe(true)
  })
})
