"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { 
  Users, 
  Heart, 
  FileText, 
  Wallet,
  UserPlus,
  DollarSign,
  Award,
  Shield,
  LogOut,
  Settings
} from "lucide-react"

const baseMenuSections = [
  {
    title: "dashboard.nav.competitions",
    items: [
      { name: "dashboard.nav.my_applications", href: "/dashboard/my-applications", icon: FileText },
      { name: "dashboard.nav.clubs", href: "/dashboard/clubs", icon: Users },
    ]
  },
  {
    title: "dashboard.nav.business",
    items: [
      { name: "dashboard.nav.wallet", href: "/dashboard/wallet", icon: Wallet },
      { name: "dashboard.nav.affiliates", href: "/dashboard/affiliates", icon: UserPlus },
      { name: "dashboard.nav.commissions", href: "/dashboard/commissions", icon: DollarSign },
      { name: "dashboard.nav.prize", href: "/dashboard/prize", icon: Award },
    ]
  },
]

const adminMenuSection = {
  title: "dashboard.nav.admin",
  items: [
    { name: "dashboard.nav.admin_panel", href: "/dashboard/admin", icon: Shield },
  ]
}

interface DashboardSidebarProps {
  isCollapsed?: boolean
  onToggleCollapse?: () => void
}

export function DashboardSidebar({ isCollapsed = false, onToggleCollapse }: DashboardSidebarProps) {
  const { t } = useLanguage()
  const pathname = usePathname()
  const { user, logout } = useAuth()

  const displayMenuSections = user?.is_admin 
    ? [...baseMenuSections, adminMenuSection]
    : baseMenuSections

  const handleLogout = async () => {
    await logout()
    window.location.href = '/'
  }

  return (
    <>
      {/* Sidebar - Desktop only */}
      <aside className={cn(
        "hidden lg:flex fixed inset-y-0 left-0 z-40 flex-col bg-white dark:bg-gray-950 border-r border-gray-100 dark:border-gray-800 transition-all duration-300 ease-in-out",
        isCollapsed ? "w-[72px]" : "w-64"
      )}>
        
        {/* Header */}
        <div className={cn(
          "flex items-center h-16 border-b border-gray-100 dark:border-gray-800",
          isCollapsed ? "justify-center px-2" : "justify-between px-4"
        )}>
          <Link href="/dashboard" className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center shadow-lg shadow-myfav-primary/25">
              <Heart className="w-5 h-5 text-white fill-white" />
            </div>
            {!isCollapsed && (
              <span className="text-lg font-bold text-gray-900 dark:text-white">
                MyHigh5
              </span>
            )}
          </Link>
          
        </div>

        {/* User Profile Card */}
        {!isCollapsed && user && (
          <div className="mx-3 mt-4 p-3 rounded-xl bg-gradient-to-br from-gray-50 to-gray-100/50 dark:from-gray-900 dark:to-gray-800/50 border border-gray-100 dark:border-gray-800">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center text-white font-semibold text-sm">
                {user.full_name?.charAt(0) || user.username?.charAt(0) || 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                  {user.full_name || user.username}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                  {user.email}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Navigation */}
        <nav className={cn(
          "flex-1 overflow-y-auto py-4",
          isCollapsed ? "px-2" : "px-3"
        )}>
          <div className="space-y-6">
            {displayMenuSections.map((section, idx) => (
              <div key={idx}>
                {!isCollapsed && (
                  <p className="px-3 mb-2 text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                    {t(section.title)}
                  </p>
                )}
                
                <div className="space-y-1">
                  {section.items.map((item) => {
                    const Icon = item.icon
                    const isActive = item.href === "/dashboard"
                      ? pathname === "/dashboard"
                      : pathname.startsWith(item.href)

                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={cn(
                          "group flex items-center gap-3 rounded-lg transition-all duration-200",
                          isCollapsed ? "justify-center p-3" : "px-3 py-2.5",
                          isActive
                            ? "bg-myfav-primary text-white shadow-lg shadow-myfav-primary/30"
                            : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
                        )}
                        title={isCollapsed ? t(item.name) : undefined}
                      >
                        <Icon className={cn(
                          "h-5 w-5 flex-shrink-0 transition-transform duration-200",
                          !isActive && "group-hover:scale-110"
                        )} />
                        
                        {!isCollapsed && (
                          <span className="text-sm font-medium">
                            {t(item.name)}
                          </span>
                        )}
                      </Link>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </nav>

        {/* Footer Actions */}
        <div className={cn(
          "border-t border-gray-100 dark:border-gray-800 py-3",
          isCollapsed ? "px-2" : "px-3"
        )}>
          <div className="space-y-1">
            <Link
              href="/dashboard/settings"
              className={cn(
                "flex items-center gap-3 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white transition-colors",
                isCollapsed ? "justify-center p-3" : "px-3 py-2.5"
              )}
              title={isCollapsed ? t('dashboard.nav.settings') : undefined}
            >
              <Settings className="h-5 w-5" />
              {!isCollapsed && (
                <span className="text-sm font-medium">{t('dashboard.nav.settings') || 'Paramètres'}</span>
              )}
            </Link>
            
            <button
              onClick={handleLogout}
              className={cn(
                "w-full flex items-center gap-3 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors",
                isCollapsed ? "justify-center p-3" : "px-3 py-2.5"
              )}
              title={isCollapsed ? t('user.logout') : undefined}
            >
              <LogOut className="h-5 w-5" />
              {!isCollapsed && (
                <span className="text-sm font-medium">{t('user.logout')}</span>
              )}
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
