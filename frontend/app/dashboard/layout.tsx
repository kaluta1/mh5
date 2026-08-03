"use client"

import * as React from "react"
import { useState, useEffect } from "react"
import { useRouter, usePathname } from "next/navigation"
import dynamic from "next/dynamic"
import { DashboardSidebar } from "@/components/dashboard/dashboard-sidebar"
import { AdminSidebar } from "@/components/dashboard/admin-sidebar"
import { DashboardNavbar } from "@/components/dashboard/dashboard-navbar"
import { useAuth } from "@/hooks/use-auth"
import { useReferralShare } from "@/hooks/use-referral-share"
import { toPublicSharePath } from "@/lib/public-share-urls"
import { Skeleton } from "@/components/ui/skeleton"

const MobileMenu = dynamic(
  () => import("@/components/dashboard/mobile-menu").then((m) => ({ default: m.MobileMenu })),
  { ssr: false },
)

interface DashboardLayoutProps {
  children: React.ReactNode
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const [hasStoredToken] = useState(() => {
    if (typeof window === "undefined") return false
    return Boolean(localStorage.getItem("access_token"))
  })
  const { isLoading, isAuthenticated } = useAuth()
  useReferralShare()
  const router = useRouter()
  const pathname = usePathname()
  
  // Détecter si on est sur une page admin
  const isAdminPage = pathname?.startsWith('/dashboard/admin') ?? false

  // Redirect guests away from dashboard; shared deep links go to public viewers.
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const publicPath = pathname ? toPublicSharePath(pathname) : null
      if (publicPath && publicPath !== pathname) {
        const query = typeof window !== 'undefined' ? window.location.search : ''
        router.replace(`${publicPath}${query}`)
        return
      }
      router.push('/')
    }
  }, [isLoading, isAuthenticated, router, pathname])

  const handleMenuToggle = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen)
  }

  const handleMenuClose = () => {
    setIsMobileMenuOpen(false)
  }

  const handleSidebarToggle = () => {
    setIsSidebarCollapsed(!isSidebarCollapsed)
  }

  // Only block unauthenticated first visits. Existing sessions can render while
  // the auth provider refreshes user data in the background.
  if (isLoading && !hasStoredToken) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex">
        {/* Sidebar Skeleton */}
        <div className="hidden lg:block w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 p-4">
          <Skeleton className="h-10 w-full mb-6" />
          <div className="space-y-3">
            {[...Array(8)].map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        </div>
        {/* Main Content Skeleton */}
        <div className="flex-1">
          {/* Navbar Skeleton */}
          <div className="h-16 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 flex items-center justify-between">
            <Skeleton className="h-8 w-48" />
            <div className="flex gap-3">
              <Skeleton className="h-10 w-10 rounded-full" />
              <Skeleton className="h-10 w-10 rounded-full" />
            </div>
          </div>
          {/* Content Skeleton */}
          <div className="p-6 space-y-6">
            <Skeleton className="h-40 w-full rounded-2xl" />
            <div className="grid grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-24 rounded-xl" />
              ))}
            </div>
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
        </div>
      </div>
    )
  }

  // Ne pas afficher le layout si non authentifié (sauf session en cours de restauration)
  if (!isAuthenticated && !hasStoredToken) {
    return null
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Desktop Sidebar - Admin ou Normal selon la route */}
      {isAdminPage ? (
        <AdminSidebar isCollapsed={isSidebarCollapsed} />
      ) : (
      <DashboardSidebar isCollapsed={isSidebarCollapsed} />
      )}
      
      {/* Mobile Menu */}
      <MobileMenu 
        isOpen={isMobileMenuOpen} 
        onClose={handleMenuClose} 
      />
      
      {/* Main content area */}
      <div className={`transition-all duration-300 ${isSidebarCollapsed ? 'lg:pl-16' : 'lg:pl-64'}`}>
        {/* Top navigation */}
        <DashboardNavbar 
          onMenuToggle={handleMenuToggle} 
          onSidebarToggle={handleSidebarToggle}
        />
        
        {/* Page content with padding for fixed header */}
        <main className="pt-16 py-6 px-4 sm:px-6 lg:px-8">
          <div className="max-w-7xl mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
