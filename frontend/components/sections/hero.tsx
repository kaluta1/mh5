"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { ArrowRight, Play, Star, Trophy, Users, Globe, Sparkles, CheckCircle2 } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"
import { InteractiveCarousel } from "@/components/ui/interactive-carousel"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/use-auth"

export function Hero() {
  const { t } = useLanguage()
  const router = useRouter()
  const { isAuthenticated } = useAuth()

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-gradient-to-br from-white via-blue-50/30 to-purple-50/30 dark:from-gray-900 dark:via-gray-800/50 dark:to-gray-900 pt-20 md:pt-16">
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden">
        {/* Gradient orbs */}
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-br from-myhigh5-primary/20 to-myhigh5-secondary/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-gradient-to-br from-purple-400/20 to-cyan-400/20 rounded-full blur-3xl animate-pulse delay-1000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-br from-blue-200/10 to-purple-200/10 rounded-full blur-3xl" />

        {/* Grid pattern */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] opacity-40" />
      </div>

      <div className="container px-4 md:px-6 relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center min-h-[calc(100vh-5rem)] md:min-h-[calc(100vh-4rem)]">
          {/* Left Column - Main Content */}
          <div className="flex flex-col space-y-8 lg:space-y-10 text-center lg:text-left">
            {/* Badge */}
            {/* <div className="inline-flex items-center gap-2 bg-gradient-to-r from-myhigh5-primary/10 to-myhigh5-secondary/10 backdrop-blur-sm border border-myhigh5-primary/20 rounded-full px-4 py-2 w-fit mx-auto lg:mx-0">
              <Sparkles className="w-4 h-4 text-myhigh5-primary" />
              <span className="text-sm font-semibold text-myhigh5-primary">
                {t('hero.badge') || "World's #1 Contest Platform"}
              </span>
            </div> */}

            {/* Main Heading */}
            <div className="space-y-6 lg:space-y-8">
              <h1 className="text-xl sm:text-2xl md:text-2xl lg:text-3xl xl:text-4xl font-black tracking-tight leading-[1.1] text-gray-900 dark:text-white">
                <span className="block">{t('hero.title_line1')}</span>
                <span className="block bg-gradient-to-r from-myhigh5-primary via-myhigh5-secondary to-myhigh5-primary bg-clip-text text-transparent animate-gradient">
                  {t('hero.title_line2')}
                </span>
                <span className="block">{t('hero.title_line3')}</span>
              </h1>
              <p className="max-w-2xl mx-auto lg:mx-0 text-lg sm:text-xl md:text-2xl text-gray-600 dark:text-gray-300 leading-relaxed font-medium">
                {t('hero.subtitle')}
              </p>
            </div>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row gap-4 sm:gap-5 justify-center lg:justify-start pt-2">
              <Button
                size="lg"
                onClick={() => router.push('/register')}
                className="group text-base sm:text-lg px-8 sm:px-10 py-6 sm:py-7 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary hover:from-myhigh5-primary-dark hover:to-myhigh5-secondary-dark text-white font-bold rounded-xl shadow-xl hover:shadow-2xl hover:shadow-myhigh5-primary/50 transition-all duration-300 hover:-translate-y-1 hover:scale-105"
              >
                <span>{t('hero.cta')}</span>
                <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                onClick={() => router.push(isAuthenticated ? '/dashboard/contests' : '/contests')}
                className="text-base sm:text-lg px-8 sm:px-10 py-6 sm:py-7 border-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-white font-semibold rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition-all duration-300 hover:-translate-y-1 hover:border-myhigh5-primary dark:hover:border-myhigh5-primary"
              >
                <Trophy className="mr-2 h-5 w-5" />
                {t('navigation.contests')}
              </Button>
            </div>

            {/* Stats Cards */}
            {/* <div className="grid grid-cols-3 gap-4 sm:gap-6 pt-4">
              <div className="group bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl p-5 sm:p-6 shadow-lg dark:shadow-xl border border-gray-200/50 dark:border-gray-700/50 hover:shadow-xl dark:hover:shadow-2xl transition-all duration-300 hover:-translate-y-2">
                <div className="flex items-center justify-center w-12 h-12 sm:w-14 sm:h-14 bg-gradient-to-br from-myhigh5-primary/10 to-myhigh5-secondary/10 rounded-xl mb-3 sm:mb-4 mx-auto group-hover:scale-110 transition-transform">
                  <Users className="h-6 w-6 sm:h-7 sm:w-7 text-myhigh5-primary dark:text-myhigh5-blue-400" />
                </div>
                <div className="text-2xl sm:text-3xl md:text-4xl font-black text-gray-900 dark:text-white mb-1">1M+</div>
                <div className="text-xs sm:text-sm text-gray-600 dark:text-gray-400 font-medium">{t('hero.stats.participants')}</div>
              </div>
              <div className="group bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl p-5 sm:p-6 shadow-lg dark:shadow-xl border border-gray-200/50 dark:border-gray-700/50 hover:shadow-xl dark:hover:shadow-2xl transition-all duration-300 hover:-translate-y-2">
                <div className="flex items-center justify-center w-12 h-12 sm:w-14 sm:h-14 bg-gradient-to-br from-myhigh5-primary/10 to-myhigh5-secondary/10 rounded-xl mb-3 sm:mb-4 mx-auto group-hover:scale-110 transition-transform">
                  <Trophy className="h-6 w-6 sm:h-7 sm:w-7 text-myhigh5-primary dark:text-myhigh5-blue-400" />
                </div>
                <div className="text-2xl sm:text-3xl md:text-4xl font-black text-gray-900 dark:text-white mb-1">50K+</div>
                <div className="text-xs sm:text-sm text-gray-600 dark:text-gray-400 font-medium">{t('hero.stats.contests')}</div>
              </div>
              <div className="group bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl p-5 sm:p-6 shadow-lg dark:shadow-xl border border-gray-200/50 dark:border-gray-700/50 hover:shadow-xl dark:hover:shadow-2xl transition-all duration-300 hover:-translate-y-2">
                <div className="flex items-center justify-center w-12 h-12 sm:w-14 sm:h-14 bg-gradient-to-br from-myhigh5-primary/10 to-myhigh5-secondary/10 rounded-xl mb-3 sm:mb-4 mx-auto group-hover:scale-110 transition-transform">
                  <Globe className="h-6 w-6 sm:h-7 sm:w-7 text-myhigh5-primary dark:text-myhigh5-blue-400" />
                </div>
                <div className="text-2xl sm:text-3xl md:text-4xl font-black text-gray-900 dark:text-white mb-1">200+</div>
                <div className="text-xs sm:text-sm text-gray-600 dark:text-gray-400 font-medium">{t('hero.stats.countries')}</div>
              </div>
            </div> */}

            {/* Trust Indicators */}
            <div className="flex flex-wrap items-center justify-center lg:justify-start gap-6 sm:gap-8 pt-2">

              <div className="flex items-center gap-3 bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-full px-4 py-2 border border-gray-200/50 dark:border-gray-700/50">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <span className="text-sm sm:text-base text-gray-700 dark:text-gray-200 font-medium">{t('hero.trust.support')}</span>
              </div>
              <div className="flex items-center gap-3 bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-full px-4 py-2 border border-gray-200/50 dark:border-gray-700/50">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <span className="text-sm sm:text-base text-gray-700 dark:text-gray-200 font-medium">{t('hero.trust.free')}</span>
              </div>
            </div>
          </div>

          {/* Right Column - Interactive Carousel */}
          <div className="flex items-center justify-center">
            <div className="w-full max-w-lg">
              <div className="relative">
                {/* Glow effect behind carousel */}
                <div className="absolute inset-0 bg-gradient-to-r from-myhigh5-primary/20 to-myhigh5-secondary/20 rounded-3xl blur-2xl -z-10" />
                <InteractiveCarousel />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
