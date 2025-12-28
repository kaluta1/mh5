"use client"

import * as React from "react"
import { useRouter, usePathname } from "next/navigation"
import { 
  Search, Menu, ShoppingBag, Command, MessageSquare
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { UserDropdown } from "@/components/user/user-dropdown"
import { ThemeToggle } from "@/components/theme-toggle"
import { LanguageSelector } from "@/components/ui/language-selector"
import { NotificationDropdown } from "@/components/dashboard/notification-dropdown"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { cn } from "@/lib/utils"

interface DashboardNavbarProps {
  onMenuToggle?: () => void
  onSidebarToggle?: () => void
}

export function DashboardNavbar({ onMenuToggle, onSidebarToggle }: DashboardNavbarProps) {
  const { t } = useLanguage()
  const router = useRouter()
  const pathname = usePathname()
  const { user, logout } = useAuth()

  return (
    <header className="fixed top-0 left-0 right-0 z-40 h-16">
      {/* Glass morphism background */}
      <div className="absolute inset-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur-xl border-b border-gray-200/50 dark:border-gray-700/50" />
      
      <div className="relative flex items-center justify-between h-full px-4 sm:px-6 lg:px-8">
        {/* Left side - Menu & Logo */}
        <div className="flex items-center gap-4">
          {/* Mobile Menu Button */}
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={onMenuToggle}
            className="md:hidden w-10 h-10 rounded-xl bg-gray-100/80 dark:bg-gray-800/80 hover:bg-gray-200 dark:hover:bg-gray-700 transition-all"
          >
            <Menu className="h-5 w-5 text-gray-700 dark:text-gray-300" />
          </Button>
          
          {/* Desktop Sidebar Toggle */}
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={onSidebarToggle}
            className="hidden md:flex w-10 h-10 rounded-xl bg-gray-100/80 dark:bg-gray-800/80 hover:bg-gray-200 dark:hover:bg-gray-700 transition-all"
          >
            <Menu className="h-5 w-5 text-gray-700 dark:text-gray-300" />
          </Button>

        </div>

        {/* Center - Search & Feed */}
        <div className="hidden md:flex flex-1 items-center gap-3 max-w-md mx-4">
          <button
            onClick={() => router.push('/dashboard/search')}
            className="flex-1 group flex items-center gap-3 px-4 py-2.5 bg-gray-100/80 dark:bg-gray-800/80 hover:bg-white dark:hover:bg-gray-700 border border-transparent hover:border-gray-200 dark:hover:border-gray-600 rounded-xl transition-all duration-200 hover:shadow-lg"
          >
            <Search className="h-4 w-4 text-gray-400 group-hover:text-myhigh5-primary transition-colors" />
            <span className="flex-1 text-left text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.search.placeholder') || 'Search...'}
            </span>
            <kbd className="hidden lg:inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-gray-400 bg-gray-200/80 dark:bg-gray-700 rounded-md">
              <Command className="w-3 h-3" />K
            </kbd>
          </button>
          
          {/* Feed Button */}
          {/* <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push('/dashboard/feed')}
            className={cn(
              "h-10 px-3 rounded-xl transition-all",
              "bg-gray-100/80 dark:bg-gray-800/80 hover:bg-white dark:hover:bg-gray-700",
              "border border-transparent hover:border-gray-200 dark:hover:border-gray-600",
              pathname === '/dashboard/feed' && "bg-myhigh5-primary/10 border-myhigh5-primary/20 text-myhigh5-primary"
            )}
            title={t('dashboard.nav.feed') || 'Feed'}
          >
            <MessageSquare className="h-5 w-5" />
          </Button> */}
        </div>

        {/* Right side - Actions */}
        <div className="flex items-center gap-1 sm:gap-2">
          {/* Mobile Search */}
          <Button 
            variant="ghost" 
            size="sm"
            onClick={() => router.push('/dashboard/search')}
            className="md:hidden w-10 h-10 rounded-xl bg-gray-100/80 dark:bg-gray-800/80 hover:bg-gray-200 dark:hover:bg-gray-700"
          >
            <Search className="h-5 w-5 text-gray-700 dark:text-gray-300" />
          </Button>

          {/* Shop Button */}
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => router.push('/dashboard/shop')}
            className="hidden sm:flex items-center gap-2 px-3 h-10 rounded-xl bg-gradient-to-r from-amber-500/10 to-orange-500/10 hover:from-amber-500/20 hover:to-orange-500/20 text-amber-700 dark:text-amber-400 transition-all"
          >
            <ShoppingBag className="h-4 w-4" />
            <span className="hidden lg:inline text-sm font-medium">{t('dashboard.nav.shop') || 'Shop'}</span>
          </Button>

          {/* Divider */}
          <div className="hidden sm:block w-px h-8 bg-gray-200 dark:bg-gray-700 mx-1" />

          {/* Settings Group */}
          <div className="hidden sm:flex items-center bg-gray-100/60 dark:bg-gray-800/60 rounded-xl p-1 gap-0.5">
            <NotificationDropdown />
            <ThemeToggle />
            <LanguageSelector />
          </div>

          {/* Mobile Notifications */}
          <div className="sm:hidden">
            <NotificationDropdown />
          </div>

          {/* User Dropdown */}
          {user && (
            <div className="ml-1 sm:ml-2">
              <UserDropdown 
                user={user}
                onLogout={logout}
                onSettings={() => router.push('/dashboard/settings')}
                onProfile={() => router.push('/dashboard/profile')}
                onKYC={() => router.push('/dashboard/kyc')}
              />
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
