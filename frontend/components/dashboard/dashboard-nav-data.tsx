/**
 * Single source for dashboard user + admin link nav. Every item has a `label` (English default)
 * so the UI never shows raw keys like "dashboard.nav.founding_member" when a translation is missing.
 */
import type { LucideIcon } from "lucide-react"
import {
  Award,
  BookOpen,
  DollarSign,
  FileText,
  Hand,
  LayoutDashboard,
  Network,
  Percent,
  Rss,
  Shield,
  Star,
  Trophy,
  UserPlus,
  Users,
  Wallet,
} from "lucide-react"

export type DashboardNavItem = {
  name: string
  /** Shown when translation for `name` is missing or empty */
  label: string
  href: string
  icon: LucideIcon
}

export type DashboardNavSection = {
  title: string
  titleLabel: string
  items: DashboardNavItem[]
}

export const userNavSections: DashboardNavSection[] = [
  {
    title: "dashboard.nav.main",
    titleLabel: "Main",
    items: [
      { name: "dashboard.nav.overview", label: "Overview", href: "/dashboard", icon: LayoutDashboard },
      { name: "dashboard.nav.contests", label: "Contests", href: "/dashboard/contests", icon: Trophy },
      { name: "dashboard.nav.myhigh5", label: "MyHigh5", href: "/dashboard/myhigh5", icon: Hand },
      { name: "Top High5", label: "Top High5", href: "/dashboard/top-high5", icon: Trophy },
      { name: "dashboard.nav.favorites", label: "Favorites", href: "/dashboard/favorites", icon: Star },
      { name: "dashboard.nav.my_applications", label: "My Applications", href: "/dashboard/my-applications", icon: FileText },
    ],
  },
  {
    title: "dashboard.nav.social",
    titleLabel: "Social",
    items: [
      { name: "dashboard.nav.feed", label: "Feed", href: "/dashboard/feed", icon: Rss },
      { name: "dashboard.nav.groups", label: "Groups", href: "/dashboard/groups", icon: Users },
    ],
  },
  {
    title: "dashboard.nav.business",
    titleLabel: "Business",
    items: [
      { name: "dashboard.nav.wallet", label: "Wallet", href: "/dashboard/wallet", icon: Wallet },
      { name: "dashboard.nav.affiliates", label: "Affiliates", href: "/dashboard/affiliates", icon: UserPlus },
      { name: "dashboard.nav.commissions", label: "Commissions", href: "/dashboard/commissions", icon: DollarSign },
      { name: "dashboard.nav.leaderboard", label: "Leaderboard", href: "/dashboard/leaderboard", icon: Award },
    ],
  },
  {
    title: "dashboard.nav.resources",
    titleLabel: "Resources",
    items: [
      { name: "dashboard.nav.founding_member", label: "Founding Membership", href: "/dashboard/founding-member", icon: BookOpen },
      { name: "dashboard.nav.fmr", label: "FMP & FMR", href: "/dashboard/founding-member/fmr", icon: Percent },
      { name: "dashboard.nav.affiliate_program", label: "Affiliate Program", href: "/dashboard/affiliate-program", icon: Network },
      { name: "dashboard.nav.affiliate_agreement", label: "Affiliate Agreement", href: "/dashboard/affiliate-agreement", icon: FileText },
    ],
  },
]

export const userAdminLinkSection: DashboardNavSection = {
  title: "dashboard.nav.admin",
  titleLabel: "Administration",
  items: [
    { name: "dashboard.nav.admin_panel", label: "Admin Panel", href: "/dashboard/admin", icon: Shield },
  ],
}
