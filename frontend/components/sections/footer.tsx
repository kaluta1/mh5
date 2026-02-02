"use client"

import * as React from "react"
import { useState, useEffect } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { 
  Facebook, 
  Twitter, 
  Instagram, 
  Youtube, 
  Mail, 
  Phone, 
  Heart,
  Send,
  Globe,
  Trophy,
  Users,
  Sparkles,
  ArrowRight,
  CheckCircle
} from "lucide-react"
import { useLanguage } from "@/contexts/language-context"
import { newsletterService, type NewsletterSubscriptionData } from "@/services/newsletter-service"
import { useToast } from "@/components/ui/toast"
import api from "@/lib/api"

const socialLinks = [
  { name: "Facebook", icon: Facebook, href: "https://facebook.com/myhigh5", color: "hover:bg-blue-600" },
  { name: "Twitter", icon: Twitter, href: "https://twitter.com/myhigh5", color: "hover:bg-sky-500" },
  { name: "Instagram", icon: Instagram, href: "https://instagram.com/myhigh5", color: "hover:bg-pink-600" },
  { name: "YouTube", icon: Youtube, href: "https://youtube.com/myhigh5", color: "hover:bg-red-600" }
]

export function Footer() {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [email, setEmail] = useState("")
  const [subscribed, setSubscribed] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [deviceInfo, setDeviceInfo] = useState<NewsletterSubscriptionData['device_info']>(null)
  const [locationInfo, setLocationInfo] = useState<NewsletterSubscriptionData['location_info']>(null)
  const [categories, setCategories] = useState<Array<{ id: number; name: string; slug: string }>>([])
  const [categoriesLoading, setCategoriesLoading] = useState(true)

  const getBrowserName = (): string => {
    if (typeof window === 'undefined') return 'Unknown'
    const ua = navigator.userAgent
    if (ua.includes('Chrome')) return 'Chrome'
    if (ua.includes('Firefox')) return 'Firefox'
    if (ua.includes('Safari')) return 'Safari'
    if (ua.includes('Edge')) return 'Edge'
    if (ua.includes('Opera')) return 'Opera'
    return 'Unknown'
  }

  // Collecter les informations de l'appareil
  useEffect(() => {
    if (typeof window !== 'undefined') {
      setDeviceInfo({
        user_agent: navigator.userAgent,
        platform: navigator.platform,
        browser: getBrowserName(),
        screen_width: window.screen.width,
        screen_height: window.screen.height,
      })
    }
  }, [])

  // Collecter les informations de localisation
  useEffect(() => {
    const fetchLocationInfo = async () => {
      try {
        // Utiliser une API de géolocalisation gratuite
        const response = await fetch('https://ipapi.co/json/')
        if (response.ok) {
          const data = await response.json()
          setLocationInfo({
            country: data.country_name,
            city: data.city,
            continent: data.continent_code,
            ip: data.ip,
            timezone: data.timezone,
          })
        }
      } catch (error) {
        // Silently fail - location is optional
        // Essayer une autre API en fallback
        try {
          const fallbackResponse = await fetch('https://api.ipify.org?format=json')
          if (fallbackResponse.ok) {
            const ipData = await fallbackResponse.json()
            setLocationInfo({
              ip: ipData.ip,
            })
          }
        } catch (fallbackError) {
          // Silently fail - location is optional
        }
      }
    }

    fetchLocationInfo()
  }, [])

  const handleSubscribe = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || isSubmitting) return

    setIsSubmitting(true)
    try {
      const subscriptionData: NewsletterSubscriptionData = {
        email,
        device_info: deviceInfo || undefined,
        location_info: locationInfo || undefined,
      }

      await newsletterService.subscribe(subscriptionData)
      setSubscribed(true)
      setEmail("")
      addToast(t('common.success') || 'Inscription réussie !', 'success')
      setTimeout(() => setSubscribed(false), 5000)
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Une erreur est survenue'
      addToast(errorMessage, 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Charger les catégories depuis l'API
  useEffect(() => {
    const fetchCategories = async () => {
      try {
        setCategoriesLoading(true)
        const response = await api.get('/api/v1/categories/', {
          params: { active_only: true },
          timeout: 30000, // Timeout spécifique pour cette requête
        })
        if (response.data && Array.isArray(response.data)) {
          setCategories(response.data)
        }
      } catch (error: unknown) {
        // En cas d'erreur, on garde un tableau vide (l'UI gère déjà ce cas)
        setCategories([])
      } finally {
        setCategoriesLoading(false)
      }
    }

    fetchCategories()
  }, [])

  const quickLinks = [
    { name: t('footer.quick_links.about'), href: "/about", icon: Users },
    { name: t('footer.quick_links.contests'), href: "/contests", icon: Trophy },
    { name: t('navigation.clubs') || "Fan Clubs", href: "/clubs", icon: Sparkles },
    { name: t('navigation.contact') || "Contact", href: "/contact", icon: Mail },
  ]

  // Les catégories sont maintenant chargées depuis l'API
  const categoryLinks = categories.map(category => ({
    name: category.name,
    href: `/contests?category=${category.slug}`
  }))

  const legalLinks = [
    { name: t('footer.legal.privacy'), href: "/privacy" },
    { name: t('footer.legal.terms'), href: "/terms" },
    { name: t('footer.legal.cookies'), href: "/cookies" },
  ]
  
  return (
    <footer className="relative bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-950 border-t border-gray-200 dark:border-gray-800">
      {/* Decorative top border */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-myhigh5-primary via-myhigh5-secondary to-myhigh5-primary" />
      
      <div className="max-w-7xl mx-auto px-4 md:px-6">
        {/* Newsletter Section */}
        <div className="py-12 border-b border-gray-200 dark:border-gray-800">
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div>
              <div className="inline-flex items-center gap-2 bg-myhigh5-primary/10 text-myhigh5-primary rounded-full px-3 py-1 text-sm font-medium mb-4">
                <Mail className="w-4 h-4" />
                Newsletter
              </div>
              <h3 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-2">
                {t('footer.newsletter.title')}
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                {t('footer.newsletter.subtitle')}
              </p>
            </div>
            <div>
              {subscribed ? (
                <div className="flex items-center gap-3 bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 p-4 rounded-xl">
                  <CheckCircle className="w-6 h-6" />
                  <span className="font-medium">{t('common.success') || "Inscription réussie !"}</span>
                </div>
              ) : (
                <form onSubmit={handleSubscribe} className="flex flex-col sm:flex-row gap-3">
                  <Input 
                    placeholder={t('footer.newsletter.placeholder')}
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="flex-1 h-12 rounded-xl border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
                    required
                  />
                  <Button 
                    type="submit"
                    disabled={isSubmitting}
                    className="h-12 px-6 rounded-xl bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary hover:shadow-lg transition-all disabled:opacity-50"
                  >
                    <Send className="w-4 h-4 mr-2" />
                    {isSubmitting ? (t('common.loading') || 'Chargement...') : t('footer.newsletter.subscribe')}
                  </Button>
                </form>
              )}
              <p className="text-xs text-gray-500 dark:text-gray-500 mt-3">
                {t('footer.newsletter.terms')}
              </p>
            </div>
          </div>
        </div>

        {/* Main Footer Content */}
        <div className="py-12 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-8 lg:gap-12">
          {/* Brand Section */}
          <div className="col-span-2 md:col-span-4 lg:col-span-2 space-y-6">
            <Link href="/" className="flex items-center space-x-2.5 group">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary shadow-lg group-hover:shadow-xl transition-all">
                <Heart className="w-5 h-5 text-white fill-current" />
              </div>
              <span className="text-2xl font-black bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary bg-clip-text text-transparent">
                MyHigh5
              </span>
            </Link>
            <p className="text-gray-600 dark:text-gray-400 max-w-sm leading-relaxed">
              {t('footer.description')}
            </p>
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-gray-600 dark:text-gray-400">
                <div className="w-8 h-8 rounded-lg bg-myhigh5-primary/10 flex items-center justify-center">
                  <Globe className="w-4 h-4 text-myhigh5-primary" />
                </div>
                <span className="text-sm">{t('footer.brand.countries')}</span>
              </div>
              <div className="flex items-center gap-3 text-gray-600 dark:text-gray-400">
                <div className="w-8 h-8 rounded-lg bg-myhigh5-primary/10 flex items-center justify-center">
                  <Phone className="w-4 h-4 text-myhigh5-primary" />
                </div>
                <span className="text-sm">{t('footer.brand.support')}</span>
              </div>
              <a 
                href="mailto:infos@myhigh5.com" 
                className="flex items-center gap-3 text-gray-600 dark:text-gray-400 hover:text-myhigh5-primary transition-colors"
              >
                <div className="w-8 h-8 rounded-lg bg-myhigh5-primary/10 flex items-center justify-center">
                  <Mail className="w-4 h-4 text-myhigh5-primary" />
                </div>
                <span className="text-sm">{t('footer.brand.email')}</span>
              </a>
            </div>
          </div>

          {/* Quick Links */}
          <div className="space-y-4">
            <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-wider">
              {t('footer.quick_links.title')}
            </h4>
            <ul className="space-y-3">
              {quickLinks.map((link) => (
                <li key={link.name}>
                  <Link 
                    href={link.href}
                    className="group flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-myhigh5-primary dark:hover:text-myhigh5-cyan-400 transition-colors"
                  >
                    <ArrowRight className="w-3 h-3 opacity-0 -ml-5 group-hover:opacity-100 group-hover:ml-0 transition-all" />
                    <span className="text-sm">{link.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Categories */}
          <div className="space-y-4">
            <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-wider">
              {t('footer.categories.title')}
            </h4>
            {categoriesLoading ? (
              <ul className="space-y-3">
                {[...Array(3)].map((_, i) => (
                  <li key={i} className="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
                ))}
              </ul>
            ) : categoryLinks.length > 0 ? (
            <ul className="space-y-3">
                {categoryLinks.slice(0, 6).map((link) => (
                <li key={link.name}>
                  <Link 
                    href={link.href}
                    className="group flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-myhigh5-primary dark:hover:text-myhigh5-cyan-400 transition-colors"
                  >
                    <ArrowRight className="w-3 h-3 opacity-0 -ml-5 group-hover:opacity-100 group-hover:ml-0 transition-all" />
                    <span className="text-sm">{link.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('footer.categories.no_categories') || 'Aucune catégorie disponible'}
              </p>
            )}
          </div>

          {/* Legal */}
          <div className="space-y-4">
            <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-wider">
              {t('footer.legal.title')}
            </h4>
            <ul className="space-y-3">
              {legalLinks.map((link) => (
                <li key={link.name}>
                  <Link 
                    href={link.href}
                    className="group flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-myhigh5-primary dark:hover:text-myhigh5-cyan-400 transition-colors"
                  >
                    <ArrowRight className="w-3 h-3 opacity-0 -ml-5 group-hover:opacity-100 group-hover:ml-0 transition-all" />
                    <span className="text-sm">{link.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="py-6 border-t border-gray-200 dark:border-gray-800">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-500">
              <span>{t('footer.copyright')}</span>
              <span className="mx-2">•</span>
              <a 
                href="https://eminilabs.com" 
                target="_blank" 
                rel="noopener noreferrer"
                className="hover:text-myhigh5-primary dark:hover:text-myhigh5-cyan-400 transition-colors"
              >
                Emini
              </a>
            </div>
            
            <div className="flex items-center gap-2">
              {socialLinks.map((social) => (
                <Link
                  key={social.name}
                  href={social.href}
                  className={`w-10 h-10 rounded-xl bg-gray-200 dark:bg-gray-800 flex items-center justify-center text-gray-600 dark:text-gray-400 ${social.color} hover:text-white transition-all duration-300`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <social.icon className="w-5 h-5" />
                  <span className="sr-only">{social.name}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}
