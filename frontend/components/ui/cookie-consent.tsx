"use client"

import * as React from "react"
import { useState, useEffect } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { useLanguage } from "@/contexts/language-context"
import { Cookie, X, Shield, Settings } from "lucide-react"

const COOKIE_CONSENT_KEY = "myhigh5_cookie_consent"

export function CookieConsent() {
  const { language } = useLanguage()
  const [isVisible, setIsVisible] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)

  const content: Record<string, {
    title: string
    description: string
    accept: string
    decline: string
    settings: string
    learnMore: string
  }> = {
    en: {
      title: "We use cookies 🍪",
      description: "We use cookies to enhance your experience, analyze traffic, and personalize content. By continuing, you agree to our use of cookies.",
      accept: "Accept All",
      decline: "Decline",
      settings: "Settings",
      learnMore: "Learn more"
    },
    fr: {
      title: "Nous utilisons des cookies 🍪",
      description: "Nous utilisons des cookies pour améliorer votre expérience, analyser le trafic et personnaliser le contenu. En continuant, vous acceptez notre utilisation des cookies.",
      accept: "Tout accepter",
      decline: "Refuser",
      settings: "Paramètres",
      learnMore: "En savoir plus"
    },
    es: {
      title: "Usamos cookies 🍪",
      description: "Usamos cookies para mejorar tu experiencia, analizar el tráfico y personalizar el contenido. Al continuar, aceptas nuestro uso de cookies.",
      accept: "Aceptar todo",
      decline: "Rechazar",
      settings: "Configuración",
      learnMore: "Más información"
    },
    de: {
      title: "Wir verwenden Cookies 🍪",
      description: "Wir verwenden Cookies, um Ihre Erfahrung zu verbessern, den Verkehr zu analysieren und Inhalte zu personalisieren. Wenn Sie fortfahren, stimmen Sie unserer Verwendung von Cookies zu.",
      accept: "Alle akzeptieren",
      decline: "Ablehnen",
      settings: "Einstellungen",
      learnMore: "Mehr erfahren"
    }
  }

  const c = content[language] || content.en

  useEffect(() => {
    // Check if user has already made a choice
    const consent = localStorage.getItem(COOKIE_CONSENT_KEY)
    if (!consent) {
      // Small delay for better UX
      const timer = setTimeout(() => {
        setIsVisible(true)
        setTimeout(() => setIsAnimating(true), 50)
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [])

  const handleAccept = () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, JSON.stringify({
      accepted: true,
      timestamp: new Date().toISOString(),
      preferences: {
        essential: true,
        analytics: true,
        advertising: true
      }
    }))
    closeConsent()
  }

  const handleDecline = () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, JSON.stringify({
      accepted: false,
      timestamp: new Date().toISOString(),
      preferences: {
        essential: true,
        analytics: false,
        advertising: false
      }
    }))
    closeConsent()
  }

  const closeConsent = () => {
    setIsAnimating(false)
    setTimeout(() => setIsVisible(false), 300)
  }

  if (!isVisible) return null

  return (
    <div 
      className={`fixed bottom-0 left-0 right-0 z-[100] p-4 transition-all duration-300 ${
        isAnimating ? 'translate-y-0 opacity-100' : 'translate-y-full opacity-0'
      }`}
    >
      <div className="max-w-4xl mx-auto">
        <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          {/* Gradient top border */}
          <div className="h-1 bg-gradient-to-r from-myfav-primary via-myfav-secondary to-myfav-primary" />
          
          <div className="p-6">
            <div className="flex flex-col md:flex-row gap-6 items-start md:items-center">
              {/* Icon & Content */}
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center">
                    <Cookie className="w-5 h-5 text-white" />
                  </div>
                  <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                    {c.title}
                  </h3>
                </div>
                <p className="text-gray-600 dark:text-gray-400 text-sm leading-relaxed">
                  {c.description}{" "}
                  <Link 
                    href="/cookies" 
                    className="text-myfav-primary hover:underline font-medium inline-flex items-center gap-1"
                  >
                    {c.learnMore}
                    <Shield className="w-3 h-3" />
                  </Link>
                </p>
              </div>

              {/* Buttons */}
              <div className="flex flex-col sm:flex-row gap-2 w-full md:w-auto">
                <Button
                  variant="outline"
                  onClick={handleDecline}
                  className="border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  <X className="w-4 h-4 mr-2" />
                  {c.decline}
                </Button>
                <Button
                  onClick={handleAccept}
                  className="bg-gradient-to-r from-myfav-primary to-myfav-secondary hover:shadow-lg text-white"
                >
                  <Cookie className="w-4 h-4 mr-2" />
                  {c.accept}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
