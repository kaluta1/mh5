import { describe, expect, it } from 'vitest'
import type { Round } from '@/lib/api-service'
import {
  cohortMonthForVoteGeographyLevel,
  cohortRoundForVoteGeographyLevel,
  computeDisplayRounds,
  isVoteGeographyLevelAvailable,
  OFFICIAL_NOMINATION_START,
  resolveVoteCalendarAnchorRound,
} from './contest-round-tabs'

function round(id: number, name: string): Round {
  return {
    id,
    name,
    submission_start_date: `${name.includes('March') ? '2026-03' : name.includes('April') ? '2026-04' : name.includes('May') ? '2026-05' : name.includes('June') ? '2026-06' : '2026-02'}-01`,
    is_submission_open: false,
    is_voting_open: name.includes('May'),
    participants_count: 0,
  } as Round
}

const rounds: Round[] = [
  round(1, 'Round January 2026'),
  round(2, 'Round February 2026'),
  round(3, 'Round March 2026'),
  round(4, 'Round April 2026'),
  round(21, 'Round May 2026'),
  round(26, 'Round June 2026'),
]

const mayVote = round(21, 'Round May 2026')
const juneVote = { ...round(26, 'Round June 2026'), is_voting_open: true } as Round

describe('contest-round-tabs March-start calendar', () => {
  it('official start is March 2026', () => {
    expect(OFFICIAL_NOMINATION_START.getFullYear()).toBe(2026)
    expect(OFFICIAL_NOMINATION_START.getMonth()).toBe(2)
  })

  it('May vote maps Country→April and Regional→March', () => {
    expect(cohortMonthForVoteGeographyLevel(mayVote, 'country')?.getMonth()).toBe(3)
    expect(cohortMonthForVoteGeographyLevel(mayVote, 'regional')?.getMonth()).toBe(2)
    expect(cohortRoundForVoteGeographyLevel(mayVote, 'country', rounds)?.id).toBe(4)
    expect(cohortRoundForVoteGeographyLevel(mayVote, 'regional', rounds)?.id).toBe(3)
  })

  it('May vote hides Continental and Global (Feb/Jan cohorts)', () => {
    expect(isVoteGeographyLevelAvailable(mayVote, 'continental', rounds)).toBe(false)
    expect(isVoteGeographyLevelAvailable(mayVote, 'global', rounds)).toBe(false)
    expect(cohortRoundForVoteGeographyLevel(mayVote, 'global', rounds)).toBeUndefined()
  })

  it('June vote enables Continental for March cohort, not Global', () => {
    expect(isVoteGeographyLevelAvailable(juneVote, 'continental', rounds)).toBe(true)
    expect(cohortRoundForVoteGeographyLevel(juneVote, 'continental', rounds)?.id).toBe(3)
    expect(isVoteGeographyLevelAvailable(juneVote, 'global', rounds)).toBe(false)
  })

  it('June calendar anchor resolves to June round and all three vote chips', () => {
    const juneNow = new Date(2026, 5, 21)
    const anchor = resolveVoteCalendarAnchorRound(rounds, juneNow)
    expect(anchor?.id).toBe(26)
    expect(isVoteGeographyLevelAvailable(anchor, 'country', rounds)).toBe(true)
    expect(isVoteGeographyLevelAvailable(anchor, 'regional', rounds)).toBe(true)
    expect(isVoteGeographyLevelAvailable(anchor, 'continental', rounds)).toBe(true)
    expect(isVoteGeographyLevelAvailable(anchor, 'global', rounds)).toBe(false)
    expect(cohortRoundForVoteGeographyLevel(anchor, 'country', rounds)?.id).toBe(21)
    expect(cohortRoundForVoteGeographyLevel(anchor, 'regional', rounds)?.id).toBe(4)
    expect(cohortRoundForVoteGeographyLevel(anchor, 'continental', rounds)?.id).toBe(3)
  })

  it('June display pills: separate Submit and Vote on same round id', () => {
    const juneNow = new Date(2026, 5, 21)
    const juneRound = { ...round(26, 'Round June 2026'), is_submission_open: true } as Round
    const mayRound = { ...round(21, 'Round May 2026'), is_voting_open: true } as Round
    const all = [...rounds.slice(0, 4), mayRound, juneRound]
    const tabs = computeDisplayRounds(all)
    expect(tabs.map((t) => t.tabKey)).toEqual(['nominate:26', 'vote:26'])
  })
})
