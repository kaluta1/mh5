"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { ArrowRight, Sparkles, Trophy, Users, Gift, Shield, Zap, CheckCircle2 } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"
import { useRouter } from "next/navigation"

export function CTA() {
  const { t } = useLanguage()
  const router = useRouter()

  return (
    <section className="relative py-20 md:py-24 lg:py-32 overflow-hidden">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-myfav-primary via-myfav-secondary to-myfav-primary/80" />
      
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-0 left-0 w-96 h-96 bg-white/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-white/10 rounded-full blur-3xl animate-pulse delay-1000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-white/5 rounded-full blur-3xl" />
        
        {/* Grid pattern overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff12_1px,transparent_1px),linear-gradient(to_bottom,#ffffff12_1px,transparent_1px)] bg-[size:24px_24px]" />
      </div>

      <div className="container px-4 md:px-6 relative z-10">
        <div className="max-w-5xl mx-auto">
          {/* Main CTA Card */}
          <div className="relative bg-white/95 dark:bg-gray-900/95 backdrop-blur-xl rounded-3xl p-8 md:p-12 lg:p-16 shadow-2xl border border-white/20">
            {/* Decorative elements */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-myfav-primary/10 to-transparent rounded-bl-full" />
            <div className="absolute bottom-0 left-0 w-64 h-64 bg-gradient-to-tr from-myfav-secondary/10 to-transparent rounded-tr-full" />
            
            <div className="relative z-10 text-center space-y-10">
              {/* Icon */}
              <div className="flex justify-center">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-myfav-primary to-myfav-secondary flex items-center justify-center shadow-xl">
                  <Sparkles className="w-10 h-10 text-white" />
                </div>
              </div>

              {/* Title and Description */}
              <div className="space-y-4">
                <h2 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight text-gray-900 dark:text-white">
                  {t('cta.title')}
                </h2>
                <p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 max-w-2xl mx-auto leading-relaxed">
                  {t('cta.subtitle')}
                </p>
              </div>

              {/* Features highlights */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl mx-auto">
                <div className="group flex flex-col items-center space-y-3 p-6 rounded-2xl bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-900/20 dark:to-blue-800/20 border border-blue-200/50 dark:border-blue-700/50 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                  <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
                    <Trophy className="w-7 h-7 text-white" />
                  </div>
                  <span className="text-sm font-bold text-gray-900 dark:text-white text-center">
                    {t('cta.features.free_contests')}
                  </span>
                </div>
                
                <div className="group flex flex-col items-center space-y-3 p-6 rounded-2xl bg-gradient-to-br from-purple-50 to-purple-100/50 dark:from-purple-900/20 dark:to-purple-800/20 border border-purple-200/50 dark:border-purple-700/50 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                  <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-purple-500 to-purple-600 flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
                    <Users className="w-7 h-7 text-white" />
                  </div>
                  <span className="text-sm font-bold text-gray-900 dark:text-white text-center">
                    {t('cta.features.active_community')}
                  </span>
                </div>
                
                <div className="group flex flex-col items-center space-y-3 p-6 rounded-2xl bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-900/20 dark:to-amber-800/20 border border-amber-200/50 dark:border-amber-700/50 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                  <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
                    <Gift className="w-7 h-7 text-white" />
                  </div>
                  <span className="text-sm font-bold text-gray-900 dark:text-white text-center">
                    {t('cta.features.real_rewards')}
                  </span>
                </div>
              </div>

              {/* CTA Buttons */}
              <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
                <Button 
                  size="lg"
                  onClick={() => router.push('/register')}
                  className="group text-lg px-10 py-7 bg-gradient-to-r from-myfav-primary to-myfav-secondary hover:from-myfav-primary-dark hover:to-myfav-secondary-dark text-white font-bold rounded-xl shadow-xl hover:shadow-2xl hover:shadow-myfav-primary/50 transition-all duration-300 hover:-translate-y-1 hover:scale-105"
                >
                  <Sparkles className="mr-2 h-5 w-5" />
                  {t('cta.button')}
                  <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
                </Button>
                <Button 
                  variant="outline" 
                  size="lg"
                  onClick={() => router.push('/contests')}
                  className="text-lg px-10 py-7 border-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-white font-semibold rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 hover:border-myfav-primary dark:hover:border-myfav-primary transition-all duration-300 hover:-translate-y-1"
                >
                  <Trophy className="mr-2 h-5 w-5" />
                  {t('navigation.contests')}
                </Button>
              </div>

              {/* Trust indicators */}
              <div className="flex flex-wrap items-center justify-center gap-6 pt-6">
                <div className="flex items-center gap-2 bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-full px-4 py-2 border border-gray-200/50 dark:border-gray-700/50">
                  <Zap className="w-5 h-5 text-amber-500" />
                  <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{t('cta.trust.instant')}</span>
                </div>
                <div className="flex items-center gap-2 bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-full px-4 py-2 border border-gray-200/50 dark:border-gray-700/50">
                  <Shield className="w-5 h-5 text-green-500" />
                  <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{t('cta.trust.secure')}</span>
                </div>
                <div className="flex items-center gap-2 bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm rounded-full px-4 py-2 border border-gray-200/50 dark:border-gray-700/50">
                  <Users className="w-5 h-5 text-blue-500" />
                  <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{t('cta.trust.support')}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
