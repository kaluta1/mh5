"use client"

import * as React from "react"
import { useRouter, usePathname } from "next/navigation"
import { 
  Home, 
  Trophy, 
  Users, 
  Heart, 
  Star,
  FileText, 
  Wallet, 
  UserPlus, 
  DollarSign, 
  Gift,
  ShoppingBag,
  X,
  Settings,
  LogOut
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { ThemeToggle } from "@/components/theme-toggle"
import { LanguageSelector } from "@/components/ui/language-selector"

interface MobileMenuProps {
  isOpen: boolean
  onClose: () => void
}

export function MobileMenu({ isOpen, onClose }: MobileMenuProps) {
  const { t } = useLanguage()
  const { logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  const handleLogout = async () => {
    await logout()
    onClose()
    window.location.href = '/'
  }

  // Quick access items (same as navbar)
  const quickAccessItems = [
    { 
      name: t('dashboard.nav.overview') || 'Overview', 
      href: "/dashboard", 
      icon: Home,
      isDefault: true 
    },
    { 
      name: t('dashboard.nav.contests') || 'Contests', 
      href: "/dashboard/contests", 
      icon: Trophy 
    },
    { 
      name: t('dashboard.nav.favorites') || 'Favorites', 
      href: "/dashboard/favorites", 
      icon: Star 
    },
  ]

  // Competition items
  const competitionItems = [
    { 
      name: t('dashboard.nav.my_applications') || 'My Applications', 
      href: "/dashboard/my-applications", 
      icon: FileText 
    },
    { 
      name: t('dashboard.nav.clubs') || 'Clubs', 
      href: "/dashboard/clubs", 
      icon: Users 
    },
  ]

  // Business items
  const businessItems = [
    { 
      name: t('dashboard.nav.wallet') || 'Wallet', 
      href: "/dashboard/wallet", 
      icon: Wallet 
    },
    { 
      name: t('dashboard.nav.affiliates') || 'Affiliates', 
      href: "/dashboard/affiliates", 
      icon: UserPlus 
    },
    { 
      name: t('dashboard.nav.commissions') || 'Commissions', 
      href: "/dashboard/commissions", 
      icon: DollarSign 
    },
    { 
      name: t('dashboard.nav.prize') || 'Prize', 
      href: "/dashboard/prize", 
      icon: Gift 
    },
    { 
      name: t('dashboard.nav.shop') || 'Shop', 
      href: "/dashboard/shop", 
      icon: ShoppingBag 
    },
  ]

  const handleItemClick = (href: string) => {
    router.push(href)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 md:hidden">
      {/* Overlay */}
      <div 
        className="fixed inset-0 bg-black/20 backdrop-blur-sm" 
        onClick={onClose}
      />
      
      {/* Menu Panel */}
      <div className="fixed inset-y-0 left-0 w-80 max-w-[85vw] bg-white dark:bg-gray-900 shadow-xl">
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-gradient-to-br from-myfav-primary to-myfav-secondary">
                <Heart className="w-5 h-5 text-white fill-current" />
              </div>
              <span className="text-xl font-black text-myfav-primary dark:text-myfav-blue-400">
                MyHigh5
              </span>
            </div>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={onClose}
              className="p-2"
            >
              <X className="h-5 w-5" />
            </Button>
          </div>

          {/* Menu Items */}
          <div className="flex-1 overflow-y-auto py-4">
            <div className="px-4 space-y-4">
              {/* Quick Access - Overview, Contests, Favorites */}
              <div className="space-y-1">
                <p className="px-3 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                  {t('dashboard.nav.main') || 'Main'}
                </p>
                {quickAccessItems.map((item) => {
                  const isActive = pathname === item.href || (item.isDefault && pathname === '/dashboard')
                  return (
                    <button
                      key={item.href}
                      onClick={() => handleItemClick(item.href)}
                      className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-left transition-all ${
                        isActive
                          ? 'bg-gradient-to-r from-myfav-primary to-purple-600 text-white shadow-lg shadow-myfav-primary/25'
                          : 'text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
                      }`}
                    >
                      <item.icon className="h-5 w-5" />
                      <span className="font-medium">{item.name}</span>
                    </button>
                  )
                })}
              </div>

              {/* Competition Items */}
              <div className="space-y-1">
                <p className="px-3 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                  {t('dashboard.nav.competitions') || 'Competitions'}
                </p>
                {competitionItems.map((item) => {
                  const isActive = pathname === item.href
                  return (
                    <button
                      key={item.href}
                      onClick={() => handleItemClick(item.href)}
                      className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-left transition-all ${
                        isActive
                          ? 'bg-gradient-to-r from-myfav-primary to-purple-600 text-white shadow-lg shadow-myfav-primary/25'
                          : 'text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
                      }`}
                    >
                      <item.icon className="h-5 w-5" />
                      <span className="font-medium">{item.name}</span>
                    </button>
                  )
                })}
              </div>

              {/* Business Items */}
              <div className="space-y-1">
                <p className="px-3 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                  {t('dashboard.nav.business') || 'Business'}
                </p>
                {businessItems.map((item) => {
                  const isActive = pathname === item.href
                  return (
                    <button
                      key={item.href}
                      onClick={() => handleItemClick(item.href)}
                      className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-left transition-all ${
                        isActive
                          ? 'bg-gradient-to-r from-myfav-primary to-purple-600 text-white shadow-lg shadow-myfav-primary/25'
                          : 'text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
                      }`}
                    >
                      <item.icon className="h-5 w-5" />
                      <span className="font-medium">{item.name}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Footer - Theme, Language, Settings & Logout */}
          <div className="border-t border-gray-200 dark:border-gray-700 p-4 space-y-3">
            {/* Theme & Language */}
            <div className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-800/50 rounded-xl">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600 dark:text-gray-400">{t('header.theme') || 'Theme'}</span>
                <ThemeToggle />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600 dark:text-gray-400">{t('header.language') || 'Language'}</span>
                <LanguageSelector />
              </div>
            </div>

            {/* Settings */}
            <button
              onClick={() => handleItemClick('/dashboard/settings')}
              className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-left transition-all ${
                pathname === '/dashboard/settings'
                  ? 'bg-gradient-to-r from-myfav-primary to-purple-600 text-white shadow-lg shadow-myfav-primary/25'
                  : 'text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <Settings className="h-5 w-5" />
              <span className="font-medium">{t('dashboard.nav.settings') || 'Settings'}</span>
            </button>
            
            {/* Logout */}
            <button
              onClick={handleLogout}
              className="w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-left transition-all text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
            >
              <LogOut className="h-5 w-5" />
              <span className="font-medium">{t('user.logout')}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
