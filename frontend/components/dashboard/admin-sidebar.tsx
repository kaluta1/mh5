"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { trOr } from "@/lib/nav-display"
import { useLanguage } from "@/contexts/language-context"
import { Heart, Home, Shield } from "lucide-react"
import { adminNavSections } from "./admin-nav-data"

interface AdminSidebarProps {
  isCollapsed?: boolean
  onToggleCollapse?: () => void
}

export function AdminSidebar({ isCollapsed = false, onToggleCollapse }: AdminSidebarProps) {
  const { t } = useLanguage()
  const pathname = usePathname()

  return (
    <>
      <aside
        className={cn(
          "hidden lg:flex fixed inset-y-0 left-0 z-40 flex-col bg-white dark:bg-gray-950 border-r border-gray-100 dark:border-gray-800 transition-all duration-300 ease-in-out",
          isCollapsed ? "w-[72px]" : "w-64"
        )}
      >
        <div
          className={cn(
            "flex items-center h-16 border-b border-gray-100 dark:border-gray-800",
            isCollapsed ? "justify-center px-2" : "justify-between px-4"
          )}
        >
          <Link href="/dashboard/admin" className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
              <Shield className="w-5 h-5 text-white fill-white" />
            </div>
            {!isCollapsed && <span className="text-lg font-bold text-gray-900 dark:text-white">Admin</span>}
          </Link>
        </div>

        <nav className={cn("flex-1 overflow-y-auto py-4", isCollapsed ? "px-2" : "px-3")}>
          <div className="space-y-6">
            <div>
              <Link
                href="/dashboard"
                className={cn(
                  "group flex items-center gap-3 rounded-lg transition-all duration-200",
                  isCollapsed ? "justify-center p-3" : "px-3 py-2.5",
                  pathname === "/dashboard" && !pathname.startsWith("/dashboard/")
                    ? "bg-myhigh5-primary text-white shadow-lg shadow-myhigh5-primary/30"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
                )}
                title={isCollapsed ? trOr(t, "navigation.home", "Home") : undefined}
              >
                <Home
                  className={cn(
                    "h-5 w-5 flex-shrink-0 transition-transform duration-200",
                    pathname !== "/dashboard" && "group-hover:scale-110"
                  )}
                />
                {!isCollapsed && (
                  <span className="text-sm font-medium">{trOr(t, "navigation.home", "Home")}</span>
                )}
              </Link>
            </div>

            {adminNavSections.map((section, idx) => (
              <div key={idx}>
                {!isCollapsed && (
                  <p className="px-3 mb-2 text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                    {trOr(t, section.title, section.titleLabel)}
                  </p>
                )}
                <div className="space-y-1">
                  {section.items.map((item) => {
                    const Icon = item.icon
                    const label = trOr(t, item.name, item.label)
                    const isActive =
                      item.href === "/dashboard/admin" ? pathname === "/dashboard/admin" : pathname.startsWith(item.href)

                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={cn(
                          "group flex items-center gap-3 rounded-lg transition-all duration-200",
                          isCollapsed ? "justify-center p-3" : "px-3 py-2.5",
                          isActive
                            ? "bg-myhigh5-primary text-white shadow-lg shadow-myhigh5-primary/30"
                            : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
                        )}
                        title={isCollapsed ? label : undefined}
                      >
                        <Icon
                          className={cn(
                            "h-5 w-5 flex-shrink-0 transition-transform duration-200",
                            !isActive && "group-hover:scale-110"
                          )}
                        />
                        {!isCollapsed && <span className="text-sm font-medium">{label}</span>}
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
