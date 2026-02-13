"use client"

import * as React from "react"
import { useRouter, usePathname } from "next/navigation"
import { 
  Home, 
  Trophy, 
  Heart, 
  Star,
  FileText, 
  Wallet, 
  UserPlus, 
  DollarSign, 
  Shield,
  X,
  Settings,
  LogOut,
  BookOpen,
  Network,
  Users,
  Hand,
  Globe,
  Award,
  LayoutDashboard,
  Calendar,
  Zap,
  Flag,
  Tag,
  Percent,
  Lightbulb,
  CreditCard,
  FileCheck,
  Rss,
  Server
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { ThemeToggle } from "@/components/theme-toggle"
import { LanguageSelector } from "@/components/ui/language-selector"

// Menu sections - identique au sidebar desktop
const baseMenuSections = [
  {
    title: "dashboard.nav.main",
    items: [
      { name: "dashboard.nav.overview", href: "/dashboard", icon: LayoutDashboard },
      { name: "dashboard.nav.contests", href: "/dashboard/contests", icon: Trophy },
      { name: "dashboard.nav.myhigh5", href: "/dashboard/myhigh5", icon: Hand },
      { name: "dashboard.nav.favorites", href: "/dashboard/favorites", icon: Star },
      { name: "dashboard.nav.my_applications", href: "/dashboard/my-applications", icon: FileText },
    ]
  },
  {
    title: "dashboard.nav.social",
    items: [
      { name: "dashboard.nav.feed", href: "/dashboard/feed", icon: Rss },
      { name: "dashboard.nav.groups", href: "/dashboard/groups", icon: Users },
    ]
  },
  {
    title: "dashboard.nav.business",
    items: [
      { name: "dashboard.nav.wallet", href: "/dashboard/wallet", icon: Wallet },
      { name: "dashboard.nav.affiliates", href: "/dashboard/affiliates", icon: UserPlus },
      { name: "dashboard.nav.commissions", href: "/dashboard/commissions", icon: DollarSign },
      { name: "dashboard.nav.leaderboard", href: "/dashboard/leaderboard", icon: Award },
    ]
  },
  {
    title: "dashboard.nav.resources",
    items: [
      { name: "dashboard.nav.founding_member", href: "/dashboard/founding-member", icon: BookOpen },
      { name: "dashboard.nav.affiliate_program", href: "/dashboard/affiliate-program", icon: Network },
      { name: "dashboard.nav.affiliate_agreement", href: "/dashboard/affiliate-agreement", icon: FileText },
    ]
  },
]

const adminMenuSections = [
  {
    title: "admin.nav.main",
    items: [
      { name: "admin.nav.dashboard", href: "/dashboard/admin", icon: LayoutDashboard },
    ]
  },
  {
    title: "admin.nav.management",
    items: [
      { name: "admin.nav.seasons", href: "/dashboard/admin/seasons", icon: Calendar },
      { name: "admin.nav.contests", href: "/dashboard/admin/contests", icon: Zap },
      { name: "admin.nav.contestants", href: "/dashboard/admin/contestants", icon: Users },
      { name: "admin.nav.users", href: "/dashboard/admin/users", icon: Settings },
      { name: "admin.nav.kyc", href: "/dashboard/admin/kyc", icon: FileCheck },
      { name: "admin.nav.reports", href: "/dashboard/admin/reports", icon: Flag },
    ]
  },
  {
    title: "admin.nav.configuration",
  items: [
      { name: "admin.nav.categories", href: "/dashboard/admin/categories", icon: Tag },
      { name: "admin.nav.commission_settings", href: "/dashboard/admin/commission-settings", icon: Percent },
      { name: "admin.nav.microservices", href: "/dashboard/admin/microservices", icon: Server },
      { name: "admin.nav.suggested_contests", href: "/dashboard/admin/suggested-contests", icon: Lightbulb },
      { name: "admin.nav.transactions", href: "/dashboard/admin/transactions", icon: CreditCard },
  ]
  },
]

interface MobileMenuProps {
  isOpen: boolean
  onClose: () => void
}

export function MobileMenu({ isOpen, onClose }: MobileMenuProps) {
  const { t } = useLanguage()
  const { user, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  // Détecter si on est sur une page admin
  const isAdminPage = pathname?.startsWith('/dashboard/admin') ?? false
  
  // Utiliser le menu admin si on est sur une page admin, sinon le menu normal
  const displayMenuSections = isAdminPage 
    ? adminMenuSections
    : (user?.is_admin 
        ? [...baseMenuSections, { title: "dashboard.nav.admin", items: [{ name: "dashboard.nav.admin_panel", href: "/dashboard/admin", icon: Shield }] }]
        : baseMenuSections)

  const handleLogout = async () => {
    await logout()
    onClose()
    window.location.href = '/'
  }

  const handleItemClick = (href: string) => {
    router.push(href)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      {/* Overlay */}
      <div 
        className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200" 
        onClick={onClose}
      />
      
      {/* Menu Panel */}
      <div className="fixed inset-y-0 left-0 w-72 bg-white dark:bg-gray-950 border-r border-gray-100 dark:border-gray-800 animate-in slide-in-from-left duration-300">
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between h-16 px-4 border-b border-gray-100 dark:border-gray-800">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
                {isAdminPage ? (
                  <Shield className="w-5 h-5 text-white fill-white" />
                ) : (
                <Heart className="w-5 h-5 text-white fill-white" />
                )}
              </div>
              <span className="text-lg font-bold text-gray-900 dark:text-white">
                {isAdminPage ? 'Admin' : 'MyHigh5'}
              </span>
            </div>
            <button 
              onClick={onClose}
              className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <X className="h-5 w-5 text-gray-500" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-4 px-3">
            <div className="space-y-6">
              {/* Bouton retour au dashboard utilisateur si on est en admin */}
              {isAdminPage && (
                <div>
                  <button
                    onClick={() => handleItemClick('/dashboard')}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                      "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
                    )}
                  >
                    <Home className="h-5 w-5" />
                    <span className="text-sm font-medium">
                      {t('navigation.dashboard') || 'Dashboard'}
                    </span>
                  </button>
                </div>
              )}
              
              {displayMenuSections.map((section, idx) => (
                <div key={idx}>
                  <p className="px-3 mb-2 text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                    {t(section.title)}
                  </p>
                  
                  <div className="space-y-1">
                    {section.items.map((item) => {
                      const Icon = item.icon
                      const isActive = item.href === "/dashboard"
                        ? pathname === "/dashboard"
                        : pathname.startsWith(item.href)

                      return (
                        <button
                          key={item.href}
                          onClick={() => handleItemClick(item.href)}
                          className={cn(
                            "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                            isActive
                              ? "bg-myhigh5-primary text-white shadow-lg shadow-myhigh5-primary/30"
                              : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
                          )}
                        >
                          <Icon className="h-5 w-5 flex-shrink-0" />
                          <span className="text-sm font-medium">
                            {t(item.name)}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </nav>

          {/* Footer */}
          <div className="border-t border-gray-100 dark:border-gray-800 p-3 space-y-2">
            {/* Theme & Language */}
            <div className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
              <ThemeToggle />
              <LanguageSelector />
            </div>

            {/* Landing Page */}
            <button
              onClick={() => handleItemClick('/')}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
              )}
            >
              <Globe className="h-5 w-5" />
              <span className="text-sm font-medium">{t('navigation.home') || 'Accueil'}</span>
            </button>

            {/* Settings */}
            <button
              onClick={() => handleItemClick('/dashboard/settings')}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                pathname === '/dashboard/settings'
                  ? "bg-myhigh5-primary text-white shadow-lg shadow-myhigh5-primary/30"
                  : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
              )}
            >
              <Settings className="h-5 w-5" />
              <span className="text-sm font-medium">{t('user.settings') || 'Paramètres'}</span>
            </button>
            
            {/* Logout */}
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors"
            >
              <LogOut className="h-5 w-5" />
              <span className="text-sm font-medium">{t('user.logout') || 'Déconnexion'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
