import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * The affiliate program is DIRECT referrals only (level 1). These checks keep
 * the member-facing affiliate pages from presenting levels 2-10 again.
 */
const read = (...parts: string[]) => readFileSync(join(__dirname, '..', ...parts), 'utf8')
const dashboard = read('app', 'dashboard', 'affiliates', 'page.tsx')
const list = read('app', 'dashboard', 'affiliates', 'list', 'page.tsx')

describe('affiliates dashboard', () => {
  it('shows one affiliates figure: the direct affiliates', () => {
    expect(dashboard).toMatch(/dashboard\.affiliates\.direct_affiliates/)
    // "Total Affiliates" would now be the same number under a different name.
    expect(dashboard).not.toMatch(/dashboard\.affiliates\.total_affiliates/)
    expect(dashboard).not.toMatch(/totalAffiliates/)
  })

  it('keeps commissions and conversion rate, and loads only direct referrals', () => {
    expect(dashboard).toMatch(/dashboard\.affiliates\.total_commissions/)
    expect(dashboard).toMatch(/dashboard\.affiliates\.conversion_rate/)
    expect(dashboard).toMatch(/\/api\/v1\/affiliates\/referrals\/detailed/)
    expect(dashboard).not.toMatch(/referrals\/all|genealogy/)
  })

  it('keeps the pending, links and invite features', () => {
    expect(dashboard).toMatch(/\/api\/v1\/affiliates\/invitations\/pending/)
    expect(dashboard).toMatch(/dashboard\.affiliates\.invite/)
  })
})

describe('affiliates list', () => {
  it('never asks the API for a level', () => {
    expect(list).toMatch(/\/api\/v1\/affiliates\/referrals\/all/)
    expect(list).not.toMatch(/apiParams\.level/)
    expect(list).not.toMatch(/levelFilter|setLevelFilter/)
  })

  it('offers no level 2-10 filter, card, column or rate', () => {
    expect(list).not.toMatch(/\[1, 2, 3, 4, 5, 6, 7, 8, 9, 10\]/)
    expect(list).not.toMatch(/dashboard\.affiliates\.all_levels/)
    expect(list).not.toMatch(/indirect/i)
    expect(list).not.toMatch(/2-10/)
    expect(list).not.toMatch(/Level \$\{level\} referrals/)
    expect(list).not.toMatch(/dashboard\.affiliates\.total_affiliates/)
  })

  it('does not show how many people an affiliate referred themselves', () => {
    expect(list).not.toMatch(/referrals_count/)
    expect(list).not.toMatch(/col_referrals_hint/)
  })

  it('states the direct-only rule with the approved copy', () => {
    expect(list).toMatch(/business_model\.direct_body/)
    expect(list).toMatch(/dashboard\.affiliates\.direct_referrals/)
  })
})
