import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { userNavSections } from '@/components/dashboard/dashboard-nav-data'

/**
 * The old "Sponsor Leaderboard" (/dashboard/leaderboard) is retired: it is not
 * part of the current business model. It is gone from navigation, from every
 * member-facing link, and the route itself no longer exists (the application's
 * normal not-found page answers a direct URL).
 *
 * It must not be confused with features that stay: MyHigh5 Leaders, Top High5,
 * and each contest's own ranking.
 */
const root = join(__dirname, '..')
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8')

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) sourceFiles(full, out)
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) out.push(full)
  }
  return out
}

const navItems = userNavSections.flatMap((section) => section.items)
const navHrefs = navItems.map((item) => item.href)

describe('retired sponsor leaderboard: navigation', () => {
  it('is not in the member navigation (sidebar and mobile menu share this list)', () => {
    expect(navHrefs).not.toContain('/dashboard/leaderboard')
    expect(navItems.map((item) => item.label)).not.toContain('Leaderboard')
    expect(navItems.map((item) => item.name)).not.toContain('dashboard.nav.leaderboard')
    expect(read('components', 'dashboard', 'dashboard-sidebar.tsx')).toMatch(/userNavSections/)
    expect(read('components', 'dashboard', 'mobile-menu.tsx')).toMatch(/userNavSections/)
  })

  it('keeps MyHigh5 Leaders, Top High5 and the direct affiliate pages in the navigation', () => {
    for (const href of [
      '/dashboard/leaders',
      '/dashboard/top-high5',
      '/dashboard/affiliates',
      '/dashboard/commissions',
      '/dashboard/affiliate-program',
      '/dashboard/contests',
      '/dashboard/wallet',
    ]) {
      expect(navHrefs, href).toContain(href)
    }
    expect(navItems.find((item) => item.href === '/dashboard/leaders')?.label).toBe('MyHigh5 Leaders')
  })
})

describe('retired sponsor leaderboard: links and route', () => {
  const files = [...sourceFiles(join(root, 'app')), ...sourceFiles(join(root, 'components')), ...sourceFiles(join(root, 'lib')), ...sourceFiles(join(root, 'services'))]

  it('no member-facing page or component links to /dashboard/leaderboard or calls its API', () => {
    const offenders = files.filter((file) => {
      const text = readFileSync(file, 'utf8')
      return /\/dashboard\/leaderboard\b/.test(text) || /affiliates\/leaderboard/.test(text)
    })
    expect(offenders.map((f) => f.replace(root, ''))).toEqual([])
  })

  it('the route no longer exists, so a direct URL gets the standard not-found page', () => {
    expect(existsSync(join(root, 'app', 'dashboard', 'leaderboard'))).toBe(false)
    expect(existsSync(join(root, 'app', 'not-found.tsx'))).toBe(true)
    // No redirect sends the old URL into another feature.
    for (const config of ['next.config.js', 'next.config.mjs', 'next.config.ts', 'middleware.ts']) {
      if (existsSync(join(root, config))) expect(read(config), config).not.toMatch(/leaderboard/i)
    }
  })

  it('the retired page copy is gone, and nothing still reads it', () => {
    const en = JSON.parse(read('lib', 'translations', 'en.json'))
    expect(en.dashboard.leaderboard).toBeUndefined()
    expect(JSON.stringify(en)).not.toMatch(/Sponsor Leaderboard|MFM Leaderboard|General Leaderboard/)
    const stillReading = files.filter((file) => /dashboard\.leaderboard\./.test(readFileSync(file, 'utf8')))
    expect(stillReading.map((f) => f.replace(root, ''))).toEqual([])
    expect(en.common.refresh).toBe('Refresh')
  })
})

describe('features that are NOT the retired leaderboard stay in place', () => {
  it('MyHigh5 Leaders page exists and uses its own API', () => {
    const leaders = read('app', 'dashboard', 'leaders', 'page.tsx')
    expect(leaders).toMatch(/\/api\/v1\/leaders\/me/)
    expect(leaders).not.toMatch(/leaderboard/i)
  })

  it('Top High5 page exists', () => {
    expect(existsSync(join(root, 'app', 'dashboard', 'top-high5', 'page.tsx'))).toBe(true)
  })

  it('a contest keeps its own ranking heading and "view all" list', () => {
    const en = JSON.parse(read('lib', 'translations', 'en.json'))
    const sidebar = read('components', 'dashboard', 'contestants-sidebar.tsx')
    expect(sidebar).toMatch(/dashboard\.nav\.leaderboard/)
    expect(en.dashboard.nav.leaderboard).toBe('Leaderboard')
    expect(existsSync(join(root, 'app', 'dashboard', 'contests', '[id]', 'contestants', 'page.tsx'))).toBe(true)
  })

  it('direct affiliate pages are untouched by the retirement', () => {
    for (const page of [
      ['app', 'dashboard', 'affiliates', 'page.tsx'],
      ['app', 'dashboard', 'affiliates', 'list', 'page.tsx'],
      ['app', 'dashboard', 'commissions', 'page.tsx'],
      ['app', 'dashboard', 'affiliate-program', 'page.tsx'],
    ]) {
      expect(existsSync(join(root, ...page)), page.join('/')).toBe(true)
    }
    expect(read('app', 'dashboard', 'commissions', 'page.tsx')).toMatch(/common\.refresh/)
  })
})
