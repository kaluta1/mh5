import type { LucideIcon } from "lucide-react"
import {
  Calendar,
  CreditCard,
  FileCheck,
  Flag,
  LayoutDashboard,
  Lightbulb,
  Banknote,
  Percent,
  Server,
  Settings,
  Tag,
  Users,
  Zap,
} from "lucide-react"
import type { DashboardNavSection } from "./dashboard-nav-data"

export const adminNavSections: DashboardNavSection[] = [
  {
    title: "admin.nav.main",
    titleLabel: "Main",
    items: [
      { name: "admin.nav.dashboard", label: "Dashboard", href: "/dashboard/admin", icon: LayoutDashboard },
    ],
  },
  {
    title: "admin.nav.management",
    titleLabel: "Management",
    items: [
      { name: "admin.nav.seasons", label: "Seasons", href: "/dashboard/admin/seasons", icon: Calendar },
      { name: "admin.nav.contests", label: "Contests", href: "/dashboard/admin/contests", icon: Zap },
      { name: "admin.nav.contestants", label: "Contestants", href: "/dashboard/admin/contestants", icon: Users },
      { name: "admin.nav.users", label: "Users", href: "/dashboard/admin/users", icon: Settings },
      { name: "admin.nav.accounting", label: "Accounting", href: "/dashboard/admin/accounting", icon: Banknote },
      { name: "admin.nav.kyc", label: "KYC", href: "/dashboard/admin/kyc", icon: FileCheck },
      { name: "admin.nav.reports", label: "Reports", href: "/dashboard/admin/reports", icon: Flag },
    ],
  },
  {
    title: "admin.nav.configuration",
    titleLabel: "Configuration",
    items: [
      { name: "admin.nav.categories", label: "Categories", href: "/dashboard/admin/categories", icon: Tag },
      { name: "admin.nav.commission_settings", label: "Commission settings", href: "/dashboard/admin/commission-settings", icon: Percent },
      { name: "admin.nav.suggested_contests", label: "Suggested contests", href: "/dashboard/admin/suggested-contests", icon: Lightbulb },
      { name: "admin.nav.transactions", label: "Transactions", href: "/dashboard/admin/transactions", icon: CreditCard },
      { name: "admin.nav.microservices", label: "Microservices", href: "/dashboard/admin/microservices", icon: Server },
    ],
  },
]
