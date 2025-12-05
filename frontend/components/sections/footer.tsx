"use client"

import * as React from "react"
import { useState } from "react"
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

const socialLinks = [
  { name: "Facebook", icon: Facebook, href: "https://facebook.com/myhigh5", color: "hover:bg-blue-600" },
  { name: "Twitter", icon: Twitter, href: "https://twitter.com/myhigh5", color: "hover:bg-sky-500" },
  { name: "Instagram", icon: Instagram, href: "https://instagram.com/myhigh5", color: "hover:bg-pink-600" },
  { name: "YouTube", icon: Youtube, href: "https://youtube.com/myhigh5", color: "hover:bg-red-600" }
]

export function Footer() {
  const { t } = useLanguage()
  const [email, setEmail] = useState("")
  const [subscribed, setSubscribed] = useState(false)

  const handleSubscribe = (e: React.FormEvent) => {
    e.preventDefault()
    if (email) {
      setSubscribed(true)
      setEmail("")
      setTimeout(() => setSubscribed(false), 3000)
    }
  }

  const quickLinks = [
    { name: t('footer.quick_links.about'), href: "/about", icon: Users },
    { name: t('footer.quick_links.contests'), href: "/contests", icon: Trophy },
    { name: t('navigation.clubs') || "Fan Clubs", href: "/clubs", icon: Sparkles },
    { name: t('navigation.contact') || "Contact", href: "/contact", icon: Mail },
  ]

  const categoryLinks = [
    { name: t('footer.categories.beauty'), href: "/contests?category=beauty" },
    { name: t('footer.categories.handsome'), href: "/contests?category=handsome" },
    { name: t('footer.categories.latest_hits'), href: "/contests?category=hits" },
    { name: t('footer.categories.pets'), href: "/contests?category=pets" },
    { name: t('footer.categories.sports_clubs'), href: "/contests?category=sports" },
  ]

  const legalLinks = [
    { name: t('footer.legal.privacy'), href: "/privacy" },
    { name: t('footer.legal.terms'), href: "/terms" },
    { name: t('footer.legal.cookies'), href: "/cookies" },
  ]
  
  return (
    <footer className="relative bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-950 border-t border-gray-200 dark:border-gray-800">
      {/* Decorative top border */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-myfav-primary via-myfav-secondary to-myfav-primary" />
      
      <div className="max-w-7xl mx-auto px-4 md:px-6">
        {/* Newsletter Section */}
        <div className="py-12 border-b border-gray-200 dark:border-gray-800">
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div>
              <div className="inline-flex items-center gap-2 bg-myfav-primary/10 text-myfav-primary rounded-full px-3 py-1 text-sm font-medium mb-4">
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
                    className="h-12 px-6 rounded-xl bg-gradient-to-r from-myfav-primary to-myfav-secondary hover:shadow-lg transition-all"
                  >
                    <Send className="w-4 h-4 mr-2" />
                    {t('footer.newsletter.subscribe')}
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
              <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-myfav-primary to-myfav-secondary shadow-lg group-hover:shadow-xl transition-all">
                <Heart className="w-5 h-5 text-white fill-current" />
              </div>
              <span className="text-2xl font-black bg-gradient-to-r from-myfav-primary to-myfav-secondary bg-clip-text text-transparent">
                MyHigh5
              </span>
            </Link>
            <p className="text-gray-600 dark:text-gray-400 max-w-sm leading-relaxed">
              {t('footer.description')}
            </p>
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-gray-600 dark:text-gray-400">
                <div className="w-8 h-8 rounded-lg bg-myfav-primary/10 flex items-center justify-center">
                  <Globe className="w-4 h-4 text-myfav-primary" />
                </div>
                <span className="text-sm">{t('footer.brand.countries')}</span>
              </div>
              <div className="flex items-center gap-3 text-gray-600 dark:text-gray-400">
                <div className="w-8 h-8 rounded-lg bg-myfav-primary/10 flex items-center justify-center">
                  <Phone className="w-4 h-4 text-myfav-primary" />
                </div>
                <span className="text-sm">{t('footer.brand.support')}</span>
              </div>
              <a 
                href="mailto:support@myhigh5.com" 
                className="flex items-center gap-3 text-gray-600 dark:text-gray-400 hover:text-myfav-primary transition-colors"
              >
                <div className="w-8 h-8 rounded-lg bg-myfav-primary/10 flex items-center justify-center">
                  <Mail className="w-4 h-4 text-myfav-primary" />
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
                    className="group flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-myfav-primary dark:hover:text-myfav-cyan-400 transition-colors"
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
            <ul className="space-y-3">
              {categoryLinks.map((link) => (
                <li key={link.name}>
                  <Link 
                    href={link.href}
                    className="group flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-myfav-primary dark:hover:text-myfav-cyan-400 transition-colors"
                  >
                    <ArrowRight className="w-3 h-3 opacity-0 -ml-5 group-hover:opacity-100 group-hover:ml-0 transition-all" />
                    <span className="text-sm">{link.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
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
                    className="group flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-myfav-primary dark:hover:text-myfav-cyan-400 transition-colors"
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
              <span>{t('common.made_with') || "Made with"}</span>
              <Heart className="w-4 h-4 text-red-500 fill-current mx-1" />
              <span>in Montreal</span>
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
