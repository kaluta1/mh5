"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { ArrowRight, Play, Star, Trophy, Users, Globe } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"
import { InteractiveCarousel } from "@/components/ui/interactive-carousel"
import { useRouter } from "next/navigation"

export function Hero() {
  const { t } = useLanguage()
  const router = useRouter()

  return (
    <section className="relative min-h-screen flex items-center justify-center bg-gradient-to-br from-white via-blue-50/30 to-white dark:from-gray-900 dark:via-gray-800/50 dark:to-gray-900 pt-20 md:pt-16 overflow-hidden">
      {/* Animated background pattern */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(30,64,175,0.05),transparent_70%)] dark:bg-[radial-gradient(circle_at_50%_50%,rgba(59,130,246,0.03),transparent_70%)]" />
      
      <div className="container px-4 md:px-6 relative z-10 ">
        <div className="grid lg:grid-cols-2 gap-8 lg:gap-16 items-center min-h-[calc(100vh-5rem)] md:min-h-[calc(100vh-4rem)]">
          {/* Left Column - Main Content */}
          <div className="flex flex-col space-y-8 lg:space-y-10 text-center lg:text-left">
          
            {/* Main Heading */}
            <div className="space-y-5 lg:space-y-8 animate-fade-in">
              <h1 className="text-4xl font-black tracking-tight sm:text-5xl md:text-6xl lg:text-3xl xl:text-4xl leading-tight text-gray-900 dark:text-white">
                <span className="block">{t('hero.title_line1')}</span>
                <span className="block text-myfav-primary dark:text-myfav-blue-400">
                  {t('hero.title_line2')}
                </span>
                <span className="block">{t('hero.title_line3')}</span>
              </h1>
              <p className="max-w-2xl mx-auto lg:mx-0 text-lg sm:text-xl text-gray-700 dark:text-gray-200 leading-relaxed font-medium">
                {t('hero.subtitle')}
              </p>
            </div>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row gap-4 sm:gap-5 justify-center lg:justify-start pt-4">
              <Button 
                size="lg"
                onClick={() => router.push('/register')}
                className="text-base sm:text-lg px-8 sm:px-10 py-3 sm:py-4 bg-myfav-primary hover:bg-myfav-primary-dark text-white font-semibold rounded-lg shadow-lg hover:shadow-2xl transition-all duration-300 hover:-translate-y-1 group"
              >
                {t('hero.cta')}
                <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
              </Button>
              {/* <Button 
                size="lg" 
                className="text-base sm:text-lg px-8 sm:px-10 py-3 sm:py-4 border-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-white font-semibold rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-all duration-300 hover:-translate-y-1"
              >
                <Play className="mr-2 h-5 w-5" />
                {t('hero.demo')}
              </Button> */}
            </div>

            {/* Stats Cards  TODO::  complete start cards when users registed*/}
            {/* <div className="grid grid-cols-3 gap-3 sm:gap-5 pt-6">
              <div className="bg-white dark:bg-gray-800 rounded-xl p-4 sm:p-6 shadow-md dark:shadow-lg border border-gray-200 dark:border-gray-700 hover:shadow-lg dark:hover:shadow-xl transition-all duration-300 hover:-translate-y-1 group">
                <div className="flex items-center justify-center w-10 h-10 sm:w-12 sm:h-12 bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg mb-3 sm:mb-4 mx-auto group-hover:scale-110 transition-transform">
                  <Users className="h-5 w-5 sm:h-6 sm:w-6 text-myfav-primary dark:text-myfav-blue-400" />
                </div>
                <div className="text-xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-1">1M+</div>
                <div className="text-xs sm:text-sm text-gray-700 dark:text-gray-300 font-medium">{t('hero.stats.participants')}</div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-xl p-4 sm:p-6 shadow-md dark:shadow-lg border border-gray-200 dark:border-gray-700 hover:shadow-lg dark:hover:shadow-xl transition-all duration-300 hover:-translate-y-1 group">
                <div className="flex items-center justify-center w-10 h-10 sm:w-12 sm:h-12 bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg mb-3 sm:mb-4 mx-auto group-hover:scale-110 transition-transform">
                  <Trophy className="h-5 w-5 sm:h-6 sm:w-6 text-myfav-primary dark:text-myfav-blue-400" />
                </div>
                <div className="text-xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-1">50K+</div>
                <div className="text-xs sm:text-sm text-gray-700 dark:text-gray-300 font-medium">{t('hero.stats.contests')}</div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-xl p-4 sm:p-6 shadow-md dark:shadow-lg border border-gray-200 dark:border-gray-700 hover:shadow-lg dark:hover:shadow-xl transition-all duration-300 hover:-translate-y-1 group">
                <div className="flex items-center justify-center w-10 h-10 sm:w-12 sm:h-12 bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-lg mb-3 sm:mb-4 mx-auto group-hover:scale-110 transition-transform">
                  <Globe className="h-5 w-5 sm:h-6 sm:w-6 text-myfav-primary dark:text-myfav-blue-400" />
                </div>
                <div className="text-xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-1">200+</div>
                <div className="text-xs sm:text-sm text-gray-700 dark:text-gray-300 font-medium">{t('hero.stats.countries')}</div>
              </div>
            </div> */}

            {/* Trust Indicators */}
            <div className="flex flex-wrap items-center justify-center lg:justify-start gap-5 sm:gap-8 pt-4">
              <div className="flex items-center gap-2.5">
                <div className="w-2.5 h-2.5 bg-myfav-primary rounded-full shadow-md"></div>
                <span className="text-sm sm:text-base text-gray-700 dark:text-gray-200 font-medium">{t('hero.trust.secure')}</span>
              </div>
              <div className="flex items-center gap-2.5">
                <div className="w-2.5 h-2.5 bg-myfav-primary rounded-full shadow-md"></div>
                <span className="text-sm sm:text-base text-gray-700 dark:text-gray-200 font-medium">{t('hero.trust.support')}</span>
              </div>
              <div className="flex items-center gap-2.5">
                <div className="w-2.5 h-2.5 bg-myfav-primary rounded-full shadow-md"></div>
                <span className="text-sm sm:text-base text-gray-700 dark:text-gray-200 font-medium">{t('hero.trust.free')}</span>
              </div>
            </div>
          </div>

          {/* Right Column - Interactive Carousel */}
          <div className="flex items-center justify-center">
            <div className="w-full max-w-lg">
              <InteractiveCarousel />
            </div>
          </div>
        </div>
      </div>

      {/* Decorative elements */}
      <div className="absolute top-1/4 left-8 w-32 h-32 bg-gradient-to-br from-blue-300 to-purple-300 rounded-full blur-3xl opacity-20 animate-pulse" />
      <div className="absolute bottom-1/4 right-8 w-40 h-40 bg-gradient-to-br from-purple-300 to-cyan-300 rounded-full blur-3xl opacity-20 animate-pulse delay-1000" />
      <div className="absolute top-1/2 left-1/4 w-24 h-24 bg-gradient-to-br from-cyan-300 to-blue-300 rounded-full blur-2xl opacity-15 animate-pulse delay-500" />
      <div className="absolute bottom-1/3 left-1/3 w-20 h-20 bg-gradient-to-br from-blue-200 to-purple-200 rounded-full blur-2xl opacity-10 animate-pulse delay-700" />
    </section>
  )
}
