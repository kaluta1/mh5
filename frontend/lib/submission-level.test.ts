import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  initialSubmissionLevel,
  showCompetitionStageSelector,
  stageFilterForView,
} from './submission-level'

describe('initial submission level', () => {
  it('nominations start at Country, participations at City', () => {
    expect(initialSubmissionLevel('nomination')).toBe('country')
    expect(initialSubmissionLevel(' Nomination ')).toBe('country')
    expect(initialSubmissionLevel('participation')).toBe('city')
    expect(initialSubmissionLevel(undefined)).toBe('city')
  })
})

describe('competition-stage selector visibility', () => {
  it('Submit -> Nominate shows no stage selector', () => {
    for (const showVoteGeographyLevels of [true, false]) {
      expect(
        showCompetitionStageSelector({ kind: 'nominate', categoryTab: 'nomination', showVoteGeographyLevels }),
      ).toBe(false)
    }
  })

  it('Submit -> Participations shows no stage selector', () => {
    // The reported bug: Country / Regional / Continental chips under Participations in Submit.
    for (const showVoteGeographyLevels of [true, false]) {
      expect(
        showCompetitionStageSelector({ kind: 'nominate', categoryTab: 'participations', showVoteGeographyLevels }),
      ).toBe(false)
    }
  })

  it('Vote keeps the stage selector', () => {
    expect(
      showCompetitionStageSelector({ kind: 'vote', categoryTab: 'nomination', showVoteGeographyLevels: true }),
    ).toBe(true)
    expect(
      showCompetitionStageSelector({ kind: 'vote', categoryTab: 'participations', showVoteGeographyLevels: true }),
    ).toBe(true)
    expect(
      showCompetitionStageSelector({ kind: 'vote', categoryTab: 'participations', showVoteGeographyLevels: false }),
    ).toBe(true)
  })

  it('nothing is shown before a tab is resolved', () => {
    expect(
      showCompetitionStageSelector({ kind: undefined, categoryTab: 'participations', showVoteGeographyLevels: true }),
    ).toBe(false)
  })
})

describe('stage filter carried between views', () => {
  it('a stage picked in Vote never filters the Submit list', () => {
    expect(stageFilterForView('nominate', 'regional')).toBe('all')
    expect(stageFilterForView('nominate', 'city')).toBe('all')
    expect(stageFilterForView(undefined, 'global')).toBe('all')
  })

  it('Vote keeps the chosen stage', () => {
    expect(stageFilterForView('vote', 'regional')).toBe('regional')
    expect(stageFilterForView('vote', 'all')).toBe('all')
  })
})

describe('contests dashboard wiring', () => {
  const page = readFileSync(join(__dirname, '..', 'app', 'dashboard', 'contests', 'page.tsx'), 'utf8')

  it('both chip rows are gated by the shared rule', () => {
    const gates = page.match(/showCompetitionStageSelector\(\{/g) ?? []
    expect(gates.length).toBe(2)
    // The old unconditional Participations gate must be gone.
    expect(page).not.toMatch(/\{categoryTab === 'participations' && \(\s*<div className="mb-6 flex items-center gap-2 flex-wrap">/)
  })

  it('the submit request never carries a competition level', () => {
    const service = readFileSync(join(__dirname, '..', 'services', 'contest-service.ts'), 'utf8')
    const start = service.indexOf('payload.round_id = roundId')
    expect(start).toBeGreaterThan(0)
    const submitBlock = service.slice(Math.max(0, start - 1500), start + 600)
    expect(submitBlock).not.toMatch(/payload\.(level|contest_level|season_level|stage)\b/)
  })

  it('location filters stay available in Submit', () => {
    expect(page).toMatch(/setFilterCountry\(/)
    expect(page).toMatch(/filterContinent/)
  })
})
