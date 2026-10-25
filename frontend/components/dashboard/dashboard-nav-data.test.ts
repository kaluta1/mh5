import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { trOr } from '@/lib/nav-display'
import { userAdminLinkSection, userNavSections } from './dashboard-nav-data'

/**
 * The member Referral Pool page (/dashboard/referral-pool) is reachable from the member navigation,
 * which the desktop sidebar and the mobile menu both render. It stays listed while sales and
 * allocation are off: the page itself shows the "purchases unavailable" message.
 */
const root = join(__dirname, '..', '..')
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8')
const navItems = userNavSections.flatMap((section) => section.items)

describe('member navigation: Referral Pool', () => {
  it('lists exactly one Referral Pool item, in Business, linking to the member page', () => {
    const pool = navItems.filter((item) => item.href.includes('referral-pool'))
    expect(pool).toHaveLength(1)
    expect(pool[0]).toMatchObject({ label: 'Referral Pool', href: '/dashboard/referral-pool' })
    const business = userNavSections.find((section) => section.title === 'dashboard.nav.business')
    expect(business?.items.map((item) => item.href)).toContain('/dashboard/referral-pool')
  })

  it('shows a readable label when the translation is missing', () => {
    const item = navItems.find((i) => i.href === '/dashboard/referral-pool')!
    expect(trOr((key) => key, item.name, item.label)).toBe('Referral Pool')
  })

  it('never links members to the Super Admin console', () => {
    const hrefs = [...navItems, ...userAdminLinkSection.items].map((item) => item.href)
    expect(hrefs).not.toContain('/dashboard/admin/referral-pool')
  })

  it('keeps every nav href unique and the member page in place', () => {
    const hrefs = navItems.map((item) => item.href)
    expect(new Set(hrefs).size).toBe(hrefs.length)
    expect(read('app', 'dashboard', 'referral-pool', 'page.tsx')).toMatch(/ReferralPoolUnitsCard/)
    expect(read('components', 'dashboard', 'dashboard-sidebar.tsx')).toMatch(/userNavSections/)
    expect(read('components', 'dashboard', 'mobile-menu.tsx')).toMatch(/userNavSections/)
  })
})
