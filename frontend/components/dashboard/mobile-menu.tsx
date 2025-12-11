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
  Network
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
      { name: "dashboard.nav.overview", href: "/dashboard", icon: Home },
      { name: "dashboard.nav.contests", href: "/dashboard/contests", icon: Trophy },
      { name: "dashboard.nav.favorites", href: "/dashboard/favorites", icon: Star },
      { name: "dashboard.nav.my_applications", href: "/dashboard/my-applications", icon: FileText },
    ]
  },
  {
    title: "dashboard.nav.business",
    items: [
      { name: "dashboard.nav.wallet", href: "/dashboard/wallet", icon: Wallet },
      { name: "dashboard.nav.affiliates", href: "/dashboard/affiliates", icon: UserPlus },
      { name: "dashboard.nav.commissions", href: "/dashboard/commissions", icon: DollarSign },
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

const adminMenuSection = {
  title: "dashboard.nav.admin",
  items: [
    { name: "dashboard.nav.admin_panel", href: "/dashboard/admin", icon: Shield },
  ]
}

interface MobileMenuProps {
  isOpen: boolean
  onClose: () => void
}

export function MobileMenu({ isOpen, onClose }: MobileMenuProps) {
  const { t } = useLanguage()
  const { user, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  const displayMenuSections = user?.is_admin 
    ? [...baseMenuSections, adminMenuSection]
    : baseMenuSections

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
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center shadow-lg shadow-myfav-primary/25">
                <Heart className="w-5 h-5 text-white fill-white" />
              </div>
              <span className="text-lg font-bold text-gray-900 dark:text-white">
                MyHigh5
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
                              ? "bg-myfav-primary text-white shadow-lg shadow-myfav-primary/30"
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

            {/* Settings */}
            <button
              onClick={() => handleItemClick('/dashboard/settings')}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                pathname === '/dashboard/settings'
                  ? "bg-myfav-primary text-white shadow-lg shadow-myfav-primary/30"
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
