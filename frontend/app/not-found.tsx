'use client'

import { useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { Home, ArrowLeft, Search, Trophy, Users, HelpCircle } from 'lucide-react'
import Link from 'next/link'
import { Header } from '@/components/layout/header'
import { Footer } from '@/components/sections/footer'

export default function NotFound() {
  const router = useRouter()
  const { t } = useLanguage()

  const quickLinks = [
    { href: '/', label: t('navigation.home') || 'Accueil', icon: Home },
    { href: '/contests', label: t('navigation.contests') || 'Concours', icon: Trophy },
    { href: '/clubs', label: t('navigation.clubs') || 'Clubs', icon: Users },
    { href: '/about', label: t('navigation.about') || 'À propos', icon: HelpCircle },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-white via-myhigh5-blue-50/30 to-myhigh5-cyan-50/30 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <Header />
      
      <main className="flex-1 flex items-center justify-center px-4 py-16">
        <div className="max-w-4xl w-full text-center">
          {/* Animation 404 */}
          <div className="mb-8 relative">
            <div className="text-9xl md:text-[12rem] font-bold text-transparent bg-clip-text bg-gradient-to-r from-myhigh5-primary via-myhigh5-secondary to-myhigh5-accent animate-pulse">
              404
            </div>
            <div className="absolute inset-0 text-9xl md:text-[12rem] font-bold text-gray-200 dark:text-gray-800 blur-2xl -z-10">
              404
            </div>
          </div>

          {/* Message principal */}
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 dark:text-white mb-4">
            {t('not_found.title') || 'Page introuvable'}
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
            {t('not_found.description') || 'Désolé, la page que vous recherchez n\'existe pas ou a été déplacée.'}
          </p>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-12">
            <Button
              onClick={() => router.back()}
              variant="outline"
              size="lg"
              className="min-w-[200px] group"
            >
              <ArrowLeft className="mr-2 h-5 w-5 group-hover:-translate-x-1 transition-transform" />
              {t('not_found.go_back') || 'Retour'}
            </Button>
            <Button
              onClick={() => router.push('/')}
              size="lg"
              className="min-w-[200px] bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary hover:from-myhigh5-blue-700 hover:to-myhigh5-cyan-700 text-white shadow-lg shadow-myhigh5-primary/30"
            >
              <Home className="mr-2 h-5 w-5" />
              {t('not_found.go_home') || 'Accueil'}
            </Button>
          </div>

          {/* Liens rapides */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-8 border border-gray-200 dark:border-gray-700">
            <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-6">
              {t('not_found.quick_links') || 'Liens rapides'}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {quickLinks.map((link) => {
                const Icon = link.icon
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="group flex flex-col items-center gap-3 p-4 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-myhigh5-primary dark:hover:border-myhigh5-primary hover:bg-myhigh5-blue-50 dark:hover:bg-myhigh5-blue-900/20 transition-all duration-200"
                  >
                    <div className="w-12 h-12 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center group-hover:scale-110 transition-transform shadow-lg shadow-myhigh5-primary/25">
                      <Icon className="h-6 w-6 text-white" />
                    </div>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300 group-hover:text-myhigh5-primary dark:group-hover:text-myhigh5-blue-400">
                      {link.label}
                    </span>
                  </Link>
                )
              })}
            </div>
          </div>

          {/* Message d'aide */}
          <div className="mt-8 p-4 bg-myhigh5-blue-50 dark:bg-myhigh5-blue-900/20 rounded-lg border border-myhigh5-blue-200 dark:border-myhigh5-blue-800">
            <p className="text-sm text-myhigh5-blue-800 dark:text-myhigh5-blue-300">
              {t('not_found.help_text') || 'Si vous pensez qu\'il s\'agit d\'une erreur, veuillez contacter notre support.'}
            </p>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  )
}
