import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * Member navigation by role, as rendered: an ordinary member and a Super Admin see the same member
 * items (Super Admin adds privileges, never removes member access), on the desktop sidebar and the
 * mobile menu. Only administrators get the extra "Admin Panel" link; the admin Referral Pool console
 * is never linked from the member navigation.
 */
const { nav, auth, push } = vi.hoisted(() => ({
  nav: { pathname: '/dashboard' },
  auth: { user: null as null | { id: number; is_admin?: boolean }, logout: async () => {} },
  push: vi.fn(),
}))

vi.mock('next/navigation', () => ({ usePathname: () => nav.pathname, useRouter: () => ({ push }) }))
vi.mock('@/hooks/use-auth', () => ({ useAuth: () => auth }))
vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: () => '', language: 'en' }) }))
vi.mock('@/components/theme-toggle', () => ({ ThemeToggle: () => null }))
vi.mock('@/components/ui/language-selector', () => ({ LanguageSelector: () => null }))

import { DashboardSidebar } from './dashboard-sidebar'
import { MobileMenu } from './mobile-menu'

const MEMBER = { id: 10, is_admin: false }
const SUPER_ADMIN = { id: 2636, is_admin: true }
const BUSINESS = ['Wallet', 'MyHigh5 Sponsors', 'Affiliates', 'Commissions', 'Referral Pool', 'MyHigh5 Leaders']

function sidebarLinks() {
  render(<DashboardSidebar />)
  return screen.getAllByRole('link').map((a) => ({ text: a.textContent?.trim() ?? '', href: a.getAttribute('href') ?? '' }))
}

function mobileItems() {
  render(<MobileMenu isOpen onClose={() => {}} />)
  return screen.getAllByRole('button').map((b) => b.textContent?.trim() ?? '')
}

describe('member navigation by role', () => {
  beforeEach(() => {
    nav.pathname = '/dashboard'
    push.mockReset()
  })

  for (const [role, user] of [['member', MEMBER], ['Super Admin', SUPER_ADMIN]] as const) {
    it(`desktop: a ${role} sees every Business item in order, Referral Pool once after Commissions`, () => {
      auth.user = user
      const links = sidebarLinks()
      const texts = links.map((l) => l.text)
      expect(texts.filter((t) => BUSINESS.includes(t))).toEqual(BUSINESS)
      expect(links.filter((l) => l.href === '/dashboard/referral-pool')).toHaveLength(1)
      expect(links.map((l) => l.href)).not.toContain('/dashboard/admin/referral-pool')
    })

    it(`mobile: a ${role} sees Referral Pool and it opens the member page`, () => {
      auth.user = user
      const items = mobileItems()
      expect(items.filter((t) => BUSINESS.includes(t))).toEqual(BUSINESS)
      fireEvent.click(screen.getByRole('button', { name: 'Referral Pool' }))
      expect(push).toHaveBeenCalledWith('/dashboard/referral-pool')
    })
  }

  it('only an administrator gets the Admin Panel link; the member list is otherwise identical', () => {
    auth.user = MEMBER
    const member = sidebarLinks()
    document.body.innerHTML = ''
    auth.user = SUPER_ADMIN
    const admin = sidebarLinks()
    expect(member.map((l) => l.href)).not.toContain('/dashboard/admin')
    expect(admin.map((l) => l.href)).toContain('/dashboard/admin')
    expect(admin.filter((l) => l.href !== '/dashboard/admin')).toEqual(member)
  })

  it('highlights Referral Pool as active on its page', () => {
    auth.user = MEMBER
    nav.pathname = '/dashboard/referral-pool'
    render(<DashboardSidebar />)
    const active = screen.getByRole('link', { name: 'Referral Pool' })
    expect(active.className).toMatch(/bg-myhigh5-primary/)
    expect(screen.getByRole('link', { name: 'Commissions' }).className).not.toMatch(/bg-myhigh5-primary text-white/)
  })
})
