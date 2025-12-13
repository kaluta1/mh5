"use client"

import * as React from "react"
import { useSearchParams } from "next/navigation"
import { Header } from "@/components/layout/header"
import { Hero } from "@/components/sections/hero"
import { Features } from "@/components/sections/features"
import { WaysToEarn } from "@/components/sections/ways-to-earn"
import { FAQ } from "@/components/sections/faq"
import { DownloadApp } from "@/components/sections/download-app"
import { Footer } from "@/components/sections/footer"
import { LoginModal } from "@/components/auth/login-modal"

export default function HomePage() {
  const searchParams = useSearchParams()
  const [user, setUser] = React.useState<{
    name?: string
    email?: string
    avatar?: string
  } | undefined>(undefined)
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

  const handleLoginSuccess = (userData: any) => {
    setUser(userData)
  }

  const handleLogout = () => {
    setUser(undefined)
    console.log("Déconnexion")
  }

  const handleRegisterClick = () => {
    // TODO: Rediriger vers la page d'inscription
    console.log("Redirection vers inscription")
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
