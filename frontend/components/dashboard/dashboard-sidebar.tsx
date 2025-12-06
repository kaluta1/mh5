"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { 
  Heart, 
  FileText, 
  Wallet,
  UserPlus,
  DollarSign,
  Shield,
  Home,
  Trophy,
  Star
} from "lucide-react"

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
  const { user } = useAuth()

  const displayMenuSections = user?.is_admin 
    ? [...baseMenuSections, adminMenuSection]
    : baseMenuSections

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
      </aside>
    </>
  )
}
