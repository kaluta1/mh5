"use client"

import * as React from "react"
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { LoginModal } from '@/components/auth/login-modal'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { UserDropdown } from "@/components/user/user-dropdown"
import { LanguageSelector } from "@/components/ui/language-selector"
import { 
  Heart, 
  Menu, 
  X, 
  Home, 
  Trophy, 
  Info, 
  Mail, 
  LayoutDashboard,
  Sparkles,
  ChevronRight,
  Smartphone,
  MessageSquare
} from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"

interface HeaderProps {
  user?: {
    name?: string
    email?: string
    avatar?: string
  }
  onLoginClick?: () => void
  onLogout?: () => void
}

export function Header({ user, onLoginClick, onLogout }: HeaderProps) {
  const router = useRouter()
  const pathname = usePathname()
  const { user: authUser, isAuthenticated, logout } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false)
  const [isScrolled, setIsScrolled] = useState(false)
  const { t } = useLanguage()

  // Handle scroll effect
  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10)
    }
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const navigationItems = [
    { name: t('navigation.home'), href: "/", icon: Home },
    ...(isAuthenticated ? [{ name: t('navigation.dashboard'), href: "/dashboard", icon: LayoutDashboard }] : []),
    ...(isAuthenticated ? [{ name: 'Feed', href: "/dashboard/feed", icon: MessageSquare }] : []),
    { name: t('navigation.contests'), href: "/contests", icon: Trophy },
    { name: t('navigation.about'), href: "/about", icon: Info },
    { name: t('navigation.contact'), href: "/contact", icon: Mail }
  ]

  const isActiveLink = (href: string) => {
    if (href === '/') return pathname === '/'
    return pathname?.startsWith(href)
  }

  return (
    <>
      <header 
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          isScrolled 
            ? 'bg-white/80 dark:bg-gray-900/80 backdrop-blur-xl shadow-lg border-b border-gray-200/50 dark:border-gray-700/50' 
            : 'bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700'
        }`}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 lg:h-18">
            {/* Logo */}
            <Link href="/" className="flex items-center space-x-2.5 group">
              <div className="relative">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-myfav-primary to-myfav-secondary shadow-lg group-hover:shadow-xl transition-all duration-300 group-hover:scale-105">
                  <Heart className="w-5 h-5 text-white fill-current" />
                </div>
                <div className="absolute -top-1 -right-1 w-3 h-3 bg-green-500 rounded-full border-2 border-white dark:border-gray-900 animate-pulse" />
              </div>
              <div className="flex flex-col">
                <span className="text-xl font-black bg-gradient-to-r from-myfav-primary to-myfav-secondary bg-clip-text text-transparent">
                  MyHigh5
                </span>
                <span className="text-[10px] font-medium text-gray-500 dark:text-gray-400 -mt-1 hidden sm:block">
                  Global Contest Platform
                </span>
              </div>
            </Link>

            {/* Desktop Navigation */}
            <nav className="hidden lg:flex items-center">
              <div className="flex items-center bg-gray-100/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-full px-1.5 py-1.5">
                {navigationItems.map((item) => {
                  const isActive = isActiveLink(item.href)
                  const Icon = item.icon
                  return (
                    <Link
                      key={item.name}
                      href={item.href}
                      className={`relative flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-300 ${
                        isActive 
                          ? 'bg-white dark:bg-gray-700 text-myfav-primary dark:text-white shadow-md' 
                          : 'text-gray-600 dark:text-gray-300 hover:text-myfav-primary dark:hover:text-white hover:bg-white/50 dark:hover:bg-gray-700/50'
                      }`}
                    >
                      <Icon className={`w-4 h-4 ${isActive ? 'text-myfav-primary dark:text-myfav-cyan-400' : ''}`} />
                      <span>{item.name}</span>
                      {isActive && (
                        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-myfav-primary" />
                      )}
                    </Link>
                  )
                })}
              </div>
            </nav>

            {/* Right Side Actions */}
            <div className="flex items-center gap-2 sm:gap-3">
              {/* Download App Button (Desktop) */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  // Scroll to download section or open app store
                  const downloadSection = document.getElementById('download-app')
                  if (downloadSection) {
                    downloadSection.scrollIntoView({ behavior: 'smooth' })
                  }
                }}
                className="hidden lg:flex items-center gap-2 font-semibold text-sm text-gray-700 dark:text-gray-300 hover:text-myfav-primary dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full px-4"
              >
                <Smartphone className="w-4 h-4" />
                <span>{t('navigation.download_app') || 'Télécharger l\'app'}</span>
              </Button>

              {/* Settings (Desktop) */}
              <div className="hidden md:flex items-center gap-1 bg-gray-100/80 dark:bg-gray-800/80 rounded-full px-2 py-1.5">
                <LanguageSelector />
                <div className="w-px h-5 bg-gray-300 dark:bg-gray-600" />
                <ThemeToggle />
              </div>
            
              {isAuthenticated && authUser ? (
                <UserDropdown 
                  user={authUser}
                  onLogout={logout}
                  onProfile={() => router.push('/profile')}
                  onSettings={() => router.push('/settings')}
                />
              ) : (
                <div className="hidden sm:flex items-center gap-2">
                  <Button 
                    variant="ghost" 
                    onClick={() => setIsLoginModalOpen(true)}
                    className="font-semibold text-sm text-gray-700 dark:text-gray-300 hover:text-myfav-primary dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full px-5"
                  >
                    {t('navigation.login')}
                  </Button>
                  <Button
                    onClick={() => router.push('/register')}
                    className="font-semibold text-sm text-white rounded-full px-5 bg-gradient-to-r from-myfav-primary to-myfav-secondary hover:shadow-xl hover:shadow-myfav-primary/25 transition-all duration-300 hover:-translate-y-0.5"
                  >
                    <Sparkles className="w-4 h-4 mr-1.5" />
                    {t('navigation.register')}
                  </Button>
                </div>
              )}

              {/* Mobile Menu Button */}
              <Button
                variant="ghost"
                size="sm"
                className="lg:hidden w-10 h-10 rounded-full bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              >
                <div className="relative w-5 h-5">
                  <Menu className={`absolute inset-0 h-5 w-5 transition-all duration-300 ${mobileMenuOpen ? 'opacity-0 rotate-90' : 'opacity-100 rotate-0'}`} />
                  <X className={`absolute inset-0 h-5 w-5 transition-all duration-300 ${mobileMenuOpen ? 'opacity-100 rotate-0' : 'opacity-0 -rotate-90'}`} />
                </div>
              </Button>
            </div>
          </div>
        </div>

        {/* Mobile Navigation */}
        <div 
          className={`lg:hidden absolute top-full left-0 right-0 bg-white/95 dark:bg-gray-900/95 backdrop-blur-xl border-b border-gray-200 dark:border-gray-700 shadow-xl transition-all duration-300 ${
            mobileMenuOpen 
              ? 'opacity-100 translate-y-0' 
              : 'opacity-0 -translate-y-4 pointer-events-none'
          }`}
        >
          <div className="max-w-7xl mx-auto px-4 py-4 space-y-3">
            {/* Nav Items */}
            <div className="space-y-1">
              {navigationItems.map((item, index) => {
                const isActive = isActiveLink(item.href)
                const Icon = item.icon
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`flex items-center justify-between px-4 py-3 rounded-xl transition-all duration-200 ${
                      isActive 
                        ? 'bg-gradient-to-r from-myfav-primary/10 to-myfav-secondary/10 text-myfav-primary dark:text-myfav-cyan-400' 
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                    }`}
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                        isActive 
                          ? 'bg-myfav-primary text-white' 
                          : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
                      }`}>
                        <Icon className="w-5 h-5" />
                      </div>
                      <span className="font-medium">{item.name}</span>
                    </div>
                    <ChevronRight className={`w-5 h-5 transition-transform ${isActive ? 'text-myfav-primary' : 'text-gray-400'}`} />
                  </Link>
                )
              })}
            </div>
            
            {/* Mobile Settings */}
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-800/50 rounded-xl">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-gray-600 dark:text-gray-400">{t('header.language')}</span>
                <LanguageSelector />
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-gray-600 dark:text-gray-400">{t('header.theme')}</span>
                <ThemeToggle />
              </div>
            </div>

            {/* Download App Button (Mobile) */}
            <div className="pt-2">
              <Button
                variant="outline"
                onClick={() => {
                  const downloadSection = document.getElementById('download-app')
                  if (downloadSection) {
                    downloadSection.scrollIntoView({ behavior: 'smooth' })
                  }
                  setMobileMenuOpen(false)
                }}
                className="w-full h-12 rounded-xl font-semibold border-2 border-gray-200 dark:border-gray-700 flex items-center justify-center gap-2"
              >
                <Smartphone className="w-5 h-5" />
                {t('navigation.download_app') || 'Télécharger l\'app'}
              </Button>
            </div>

            {/* Mobile Auth Buttons */}
            {!isAuthenticated && (
              <div className="grid grid-cols-2 gap-3 pt-2">
                <Button 
                  variant="outline" 
                  onClick={() => {
                    setIsLoginModalOpen(true)
                    setMobileMenuOpen(false)
                  }}
                  className="h-12 rounded-xl font-semibold border-2 border-gray-200 dark:border-gray-700"
                >
                  {t('navigation.login')}
                </Button>
                <Button
                  onClick={() => {
                    router.push('/register')
                    setMobileMenuOpen(false)
                  }}
                  className="h-12 rounded-xl font-semibold text-white bg-gradient-to-r from-myfav-primary to-myfav-secondary"
                >
                  <Sparkles className="w-4 h-4 mr-1.5" />
                  {t('navigation.register')}
                </Button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Mobile menu overlay */}
      {mobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}
      
      <LoginModal 
        open={isLoginModalOpen} 
        onOpenChange={setIsLoginModalOpen}
        onSwitchToRegister={() => {
          setIsLoginModalOpen(false)
          router.push('/register')
        }}
      />
    </>
  )
}
