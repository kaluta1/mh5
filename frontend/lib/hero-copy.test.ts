import { describe, expect, it } from 'vitest'
import { HERO_COPY } from './hero-copy'

describe('HERO_COPY', () => {
  it('includes all labels required on mobile home', () => {
    expect(HERO_COPY.cta.length).toBeGreaterThan(0)
    expect(HERO_COPY.contests.length).toBeGreaterThan(0)
    expect(HERO_COPY.titleLine1.length).toBeGreaterThan(0)
    expect(HERO_COPY.subtitle.length).toBeGreaterThan(0)
    expect(HERO_COPY.support.length).toBeGreaterThan(0)
    expect(HERO_COPY.free.length).toBeGreaterThan(0)
  })
})
