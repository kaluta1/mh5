"use client"

import * as React from "react"
import { useSearchParams } from "next/navigation"
import { Header } from "@/components/layout/header"
import { Hero } from "@/components/sections/hero"
import { Features } from "@/components/sections/features"
import { Testimonials } from "@/components/sections/testimonials"
import { CTA } from "@/components/sections/cta"
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
    <div className=" bg-gradient-to-br from-blue-50 via-white to-purple-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <Header 
        user={user}
        onLoginClick={handleLoginClick}
        onLogout={handleLogout}
      />
      
      <main className="pt-10 flex-1">
        <Hero />
        <div className="py-16 dsm-bg-light">
        <div className="container">
          <Features />
          <Testimonials />
        </div>  
        </div>
        
        
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
