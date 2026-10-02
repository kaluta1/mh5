import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { commissionRatePercent, formatCommissionRate } from './commission-rate'

/**
 * The affiliate program is DIRECT referrals only (level 1). Nothing a member
 * reads, in any language, may describe an active multi-level program, and no
 * frontend constant may state a commission rate as if it were the policy.
 */
const root = join(__dirname, '..')
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8')

const MULTI_LEVEL = new RegExp(
  [
    '\\b10[- ]?levels?\\b',
    'levels? deep',
    'levels?\\s*2\\s*(?:-|–|to)\\s*10',
    'L2\\s*[-–]\\s*L?10',
    '\\bindirect (?:referral|commission)',
    '1\\s?%\\s*(?:on )?(?:each )?levels?',
    'niveaux?\\s*2\\s*(?:-|–|à)\\s*10',
    '10 niveaux',
    'niveles\\s*2\\s*(?:-|–|a|al)\\s*10',
    '10 niveles',
    'downline',
    'upline',
  ].join('|'),
  'i',
)

/** Wording that truthfully says the multi-level program is gone. */
const NEGATION = /no (?:multi-level|level 2 to 10)|there are no|no longer|retired|plus de|n'existe plus|ya no|retir/i

function leaves(node: unknown, path: string[] = []): Array<[string, string]> {
  if (typeof node === 'string') return [[path.join('.'), node]]
  if (node && typeof node === 'object') {
    return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) => leaves(v, [...path, k]))
  }
  return []
}

describe('translations', () => {
  const dir = join(root, 'lib', 'translations')
  const files = readdirSync(dir).filter((f) => f.endsWith('.json'))

  it('covers every language file', () => {
    expect(files.length).toBeGreaterThanOrEqual(45)
  })

  it('no language describes an active multi-level affiliate program', () => {
    const offenders: string[] = []
    for (const file of files) {
      const data = JSON.parse(readFileSync(join(dir, file), 'utf8'))
      for (const [key, value] of leaves(data)) {
        if (key.startsWith('features.items.multi_level')) continue // contest stages (city ... global), not affiliates
        if (MULTI_LEVEL.test(value) && !NEGATION.test(value)) offenders.push(`${file}: ${key} = ${value.slice(0, 90)}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('keeps the approved direct-only explanation', () => {
    const en = JSON.parse(readFileSync(join(dir, 'en.json'), 'utf8'))
    expect(en.business_model.direct_body).toMatch(/directly/i)
    expect(en.business_model.direct_body).toMatch(/there are no level 2 to 10 commissions/i)
    expect(en.dashboard.affiliates.indirect_description).toBeUndefined()
    expect(en.dashboard.affiliates.max_commission).toBeUndefined()
    expect(en.hero.affiliate.description).toBeUndefined()
  })
})

describe('frontend configuration', () => {
  it('has no constant that states 10% direct / 1% indirect as the policy', () => {
    expect(existsSync(join(root, 'lib', 'commission-config.ts'))).toBe(false)
  })

  it('marks the old level 1 / levels 2-10 accounting helpers as legacy and leaves them unused', () => {
    expect(read('lib', 'accounting', 'coa.ts')).toMatch(/LEGACY/)
    for (const page of [
      ['app', 'dashboard', 'affiliates', 'page.tsx'],
      ['app', 'dashboard', 'affiliates', 'list', 'page.tsx'],
      ['app', 'dashboard', 'commissions', 'page.tsx'],
    ]) {
      expect(read(...page)).not.toMatch(/accounting\/coa|commission-config/)
    }
  })
})

describe('member-facing affiliate pages', () => {
  const pages = {
    dashboard: read('app', 'dashboard', 'affiliates', 'page.tsx'),
    list: read('app', 'dashboard', 'affiliates', 'list', 'page.tsx'),
    commissions: read('app', 'dashboard', 'commissions', 'page.tsx'),
    invite: read('components', 'dashboard', 'invite-dialog.tsx'),
  }

  it('state no hard-coded commission percentage', () => {
    for (const [name, source] of Object.entries(pages)) {
      expect(source, name).not.toMatch(/['"`>]\s*(?:10|1|2)\s?%\s*['"`<]/)
      expect(source, name).not.toMatch(/10% de commission/)
    }
  })

  it('explain the current program with the direct-only copy', () => {
    expect(pages.dashboard).toMatch(/business_model\.direct_body/)
    expect(pages.list).toMatch(/business_model\.direct_body/)
    expect(pages.list).not.toMatch(/direct_tooltip_desc/)
  })

  it('show each commission at the rate it was really paid', () => {
    expect(pages.commissions).toMatch(/formatCommissionRate\(commission\.amount, commission\.baseAmount\)/)
    // A historical row still shows its real level.
    expect(pages.commissions).toMatch(/N\$\{commission\.level\}/)
  })
})

describe('commission rate display', () => {
  it('derives the rate from the row itself', () => {
    expect(formatCommissionRate(10, 50)).toBe('20%') // current direct commission
    expect(formatCommissionRate(2, 10)).toBe('20%')
    expect(formatCommissionRate(1, 10)).toBe('10%') // historical level 1 row
    expect(formatCommissionRate(0.1, 10)).toBe('1%') // historical level 2-10 row
    expect(formatCommissionRate(4, 16)).toBe('25%')
    expect(formatCommissionRate(1, 40)).toBe('2.5%')
  })

  it('shows nothing rather than a guessed rate', () => {
    expect(formatCommissionRate(5, undefined)).toBe('')
    expect(formatCommissionRate(5, 0)).toBe('')
    expect(formatCommissionRate('x', 10)).toBe('')
    expect(commissionRatePercent(-1, 10)).toBeNull()
  })
})
