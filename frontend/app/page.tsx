"use client"

import * as React from "react"
import { Suspense } from "react"
import dynamicImport from "next/dynamic"
import { useSearchParams, useRouter } from "next/navigation"
import { Header } from "@/components/layout/header"
import type { User } from "@/types/user"

// Lazy load Hero component for faster initial page load (it's heavy with animations)
const Hero = dynamicImport(() => import("@/components/sections/hero").then(mod => ({ default: mod.Hero })), {
  loading: () => <div className="min-h-screen animate-pulse bg-gradient-to-br from-white via-blue-50/30 to-purple-50/30 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900" />
})

// Lazy load components below the fold for faster initial page load
const Features = dynamicImport(() => import("@/components/sections/features").then(mod => ({ default: mod.Features })), {
  loading: () => <div className="min-h-[400px] animate-pulse bg-gray-100 dark:bg-gray-800 rounded-lg" />
})

const WaysToEarn = dynamicImport(() => import("@/components/sections/ways-to-earn").then(mod => ({ default: mod.WaysToEarn })), {
  loading: () => <div className="min-h-[400px] animate-pulse bg-gray-100 dark:bg-gray-800 rounded-lg" />
})

const FAQ = dynamicImport(() => import("@/components/sections/faq").then(mod => ({ default: mod.FAQ })), {
  loading: () => <div className="min-h-[400px] animate-pulse bg-gray-100 dark:bg-gray-800 rounded-lg" />
})

const DownloadApp = dynamicImport(() => import("@/components/sections/download-app").then(mod => ({ default: mod.DownloadApp })), {
  loading: () => <div className="min-h-[300px] animate-pulse bg-gray-100 dark:bg-gray-800 rounded-lg" />
})

const Footer = dynamicImport(() => import("@/components/sections/footer").then(mod => ({ default: mod.Footer })), {
  loading: () => <div className="min-h-[200px] animate-pulse bg-gray-100 dark:bg-gray-800" />
})

const LoginModal = dynamicImport(() => import("@/components/auth/login-modal").then(mod => ({ default: mod.LoginModal })), {
  ssr: false
})

interface HomePageUser {
  name?: string
  email?: string
  avatar?: string
}

function HomePageContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [user, setUser] = React.useState<HomePageUser | undefined>(undefined)
  const [showLoginModal, setShowLoginModal] = React.useState(false)

  // Capturer le code de parrainage depuis l'URL
  React.useEffect(() => {
    const refCode = searchParams.get('ref') || searchParams.get('referral')
    if (refCode) {
      localStorage.setItem('referral_code', refCode)
    }
  }, [searchParams])

  const handleLoginClick = () => {
    setShowLoginModal(true)
  }

  const handleLoginSuccess = (userData: User) => {
    setUser({
      name: userData.full_name || userData.username,
      email: userData.email,
      avatar: userData.avatar_url,
    })
  }

  const handleLogout = () => {
    setUser(undefined)
  }

  const handleRegisterClick = () => {
    router.push('/register')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-blue-50/30 to-purple-50/30 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <Header 
        user={user}
        onLoginClick={handleLoginClick}
        onLogout={handleLogout}
      />
      
      <main className="relative">
        <Hero />
        <Features />
        <WaysToEarn />
        <FAQ />
        <DownloadApp />
      </main>
      
      <Footer />

      <LoginModal
        open={showLoginModal}
        onOpenChange={setShowLoginModal}
        onLoginSuccess={handleLoginSuccess}
        onRegisterClick={handleRegisterClick}
      />
    </div>
  )
}

export default function HomePage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gradient-to-br from-white via-blue-50/30 to-purple-50/30 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900" />}>
      <HomePageContent />
    </Suspense>
  )
}
