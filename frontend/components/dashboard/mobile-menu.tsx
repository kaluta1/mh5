"use client"

import * as React from "react"
import { useRouter, usePathname } from "next/navigation"
import {
  Home,
  Heart,
  Shield,
  X,
  Settings,
  LogOut,
  Globe,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { trOr } from "@/lib/nav-display"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { ThemeToggle } from "@/components/theme-toggle"
import { LanguageSelector } from "@/components/ui/language-selector"
import { userAdminLinkSection, userNavSections } from "./dashboard-nav-data"
import { adminNavSections } from "./admin-nav-data"

interface MobileMenuProps {
  isOpen: boolean
  onClose: () => void
}

export function MobileMenu({ isOpen, onClose }: MobileMenuProps) {
  const { t } = useLanguage()
  const { user, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  const isAdminPage = pathname?.startsWith("/dashboard/admin") ?? false

  const displayMenuSections = isAdminPage
    ? adminNavSections
    : user?.is_admin
      ? [...userNavSections, userAdminLinkSection]
      : userNavSections

  const handleLogout = async () => {
    await logout()
    onClose()
    window.location.href = "/"
  }

  const handleItemClick = (href: string) => {
    router.push(href)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={onClose}
      />
      <div className="fixed inset-y-0 left-0 w-72 bg-white dark:bg-gray-950 border-r border-gray-100 dark:border-gray-800 animate-in slide-in-from-left duration-300">
        <div className="flex flex-col h-full">
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
                {isAdminPage ? "Admin" : "MyHigh5"}
              </span>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <X className="h-5 w-5 text-gray-500" />
            </button>
          </div>

          <nav className="flex-1 overflow-y-auto py-4 px-3">
            <div className="space-y-6">
              {isAdminPage && (
                <div>
                  <button
                    type="button"
                    onClick={() => handleItemClick("/dashboard")}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                      "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
                    )}
                  >
                    <Home className="h-5 w-5" />
                    <span className="text-sm font-medium">
                      {trOr(t, "navigation.dashboard", "Dashboard")}
                    </span>
                  </button>
                </div>
              )}

              {displayMenuSections.map((section, idx) => (
                <div key={idx}>
                  <p className="px-3 mb-2 text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                    {trOr(t, section.title, section.titleLabel)}
                  </p>
                  <div className="space-y-1">
                    {section.items.map((item) => {
                      const Icon = item.icon
                      const label = trOr(t, item.name, item.label)
                      const isActive =
                        item.href === "/dashboard"
                          ? pathname === "/dashboard"
                          : pathname.startsWith(item.href)

                      return (
                        <button
                          key={item.href}
                          type="button"
                          onClick={() => handleItemClick(item.href)}
                          className={cn(
                            "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                            isActive
                              ? "bg-myhigh5-primary text-white shadow-lg shadow-myhigh5-primary/30"
                              : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
                          )}
                        >
                          <Icon className="h-5 w-5 flex-shrink-0" />
                          <span className="text-sm font-medium">{label}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </nav>

          <div className="border-t border-gray-100 dark:border-gray-800 p-3 space-y-2">
            <div className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
              <ThemeToggle />
              <LanguageSelector />
            </div>
            <button
              type="button"
              onClick={() => handleItemClick("/")}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
              )}
            >
              <Globe className="h-5 w-5" />
              <span className="text-sm font-medium">{trOr(t, "navigation.home", "Home")}</span>
            </button>
            <button
              type="button"
              onClick={() => handleItemClick("/dashboard/settings")}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                pathname === "/dashboard/settings"
                  ? "bg-myhigh5-primary text-white shadow-lg shadow-myhigh5-primary/30"
                  : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-white"
              )}
            >
              <Settings className="h-5 w-5" />
              <span className="text-sm font-medium">{trOr(t, "user.settings", "Settings")}</span>
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors"
            >
              <LogOut className="h-5 w-5" />
              <span className="text-sm font-medium">{trOr(t, "user.logout", "Log out")}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
