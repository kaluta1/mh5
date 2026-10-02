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
    const tabs = computeDisplayRounds(all, juneNow)
    expect(tabs.map((t) => t.tabKey)).toEqual(['nominate:26', 'vote:26'])
  })
})

// ---------------------------------------------------------------------------
// Round dropdown (Nominate view): the previous month must stay selectable while
// it is the live vote round. Shapes below mirror the production selector payload
// of October 2026.
// ---------------------------------------------------------------------------
import { roundSelectorOptions } from './contest-round-tabs'
import { isRoundVotingLive } from './is-round-voting-live'

function monthRound(id: number, month: string, start: string, extra: Partial<Round> = {}): Round {
  const [y, m] = start.split('-').map(Number)
  const lastDay = new Date(y, m, 0).getDate()
  const voteStart = new Date(y, m, 1)
  const voteEnd = new Date(y, m + 5, 0)
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return {
    id,
    name: `Round ${month} 2026`,
    status: 'active',
    is_submission_open: false,
    is_voting_open: false,
    submission_start_date: `${start}-01`,
    submission_end_date: `${start}-${String(lastDay).padStart(2, '0')}`,
    voting_start_date: iso(voteStart),
    voting_end_date: iso(voteEnd),
    participants_count: 0,
    ...extra,
  } as Round
}

const october2026: Round[] = [
  monthRound(33, 'October', '2026-10', { is_submission_open: true }),
  monthRound(29, 'September', '2026-09', { is_voting_open: true }), // live vote round
  monthRound(28, 'August', '2026-08'),
  monthRound(27, 'July', '2026-07'),
  monthRound(26, 'June', '2026-06'),
  monthRound(21, 'May', '2026-05'),
  monthRound(4, 'April', '2026-04', { status: 'completed' }),
  monthRound(3, 'March', '2026-03', { status: 'completed' }),
]

describe('round dropdown options', () => {
  const names = (rs: Round[]) => rs.map((r) => r.name)

  it('September is the live vote round in this fixture (the case that used to be dropped)', () => {
    expect(isRoundVotingLive(october2026[1], october2026)).toBe(true)
  })

  it('keeps September between October and August, newest month first', () => {
    expect(names(roundSelectorOptions(october2026))).toEqual([
      'Round October 2026',
      'Round September 2026',
      'Round August 2026',
      'Round July 2026',
      'Round June 2026',
      'Round May 2026',
      'Round April 2026',
      'Round March 2026',
    ])
  })

  it('October stays the open round and older/completed rounds stay visible', () => {
    const options = roundSelectorOptions(october2026)
    expect(options[0].id).toBe(33)
    expect(options[0].is_submission_open).toBe(true)
    expect(options.filter((r) => r.is_submission_open).map((r) => r.id)).toEqual([33])
    expect(options.map((r) => r.id)).toEqual(expect.arrayContaining([28, 27, 26, 21, 4, 3]))
  })

  it('orders by cohort month, not by id or input order', () => {
    const shuffled = [october2026[4], october2026[0], october2026[7], october2026[1], october2026[2]]
    expect(roundSelectorOptions(shuffled).map((r) => r.id)).toEqual([33, 29, 28, 26, 3])
  })

  it('does not mutate the rounds list it is given', () => {
    const input = [october2026[2], october2026[0], october2026[1]]
    const before = input.map((r) => r.id)
    roundSelectorOptions(input)
    expect(input.map((r) => r.id)).toEqual(before)
  })

  it('never lists cancelled rounds, including cancelled duplicates of a month', () => {
    const withCancelled = [
      ...october2026,
      monthRound(23, 'June', '2026-06', { status: 'cancelled' }),
      monthRound(24, 'June', '2026-06', { status: 'CANCELLED' as Round['status'] }),
      monthRound(30, 'September', '2026-09', { status: 'cancelled' }),
    ]
    const ids = roundSelectorOptions(withCancelled).map((r) => r.id)
    expect(ids).not.toContain(23)
    expect(ids).not.toContain(24)
    expect(ids).not.toContain(30)
    expect(ids.filter((id) => id === 26)).toHaveLength(1)
    expect(ids).toContain(29)
  })

  it('a missing month is simply absent (no placeholder is invented)', () => {
    const withoutSeptember = october2026.filter((r) => r.id !== 29)
    expect(names(roundSelectorOptions(withoutSeptember))).toEqual([
      'Round October 2026',
      'Round August 2026',
      'Round July 2026',
      'Round June 2026',
      'Round May 2026',
      'Round April 2026',
      'Round March 2026',
    ])
  })

  it('handles an empty list', () => {
    expect(roundSelectorOptions([])).toEqual([])
  })

  it('top pills are unchanged: Submit = October, Vote = October anchor', () => {
    const tabs = computeDisplayRounds(october2026, new Date(2026, 9, 2))
    expect(tabs.map((t) => `${t.kind}:${t.round.id}`)).toEqual(['nominate:33', 'vote:33'])
  })
})
