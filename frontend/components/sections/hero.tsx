"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { ArrowRight, Trophy, CheckCircle2 } from "lucide-react"
import { InteractiveCarousel } from "@/components/ui/interactive-carousel"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/use-auth"
import { HERO_COPY } from "@/lib/hero-copy"
import { useLanguage } from "@/contexts/language-context"

/** Prefer live locale when loaded; always fall back to bundled English. */
function useHeroText() {
  const { t } = useLanguage()
  const pick = React.useCallback(
    (key: string, fallback: string) => {
      const value = t(key)
      return value && value.trim() ? value : fallback
    },
    [t],
  )

  return React.useMemo(
    () => ({
      titleLine1: pick('hero.title_line1', HERO_COPY.titleLine1),
      titleLine2: pick('hero.title_line2', HERO_COPY.titleLine2),
      titleLine3: pick('hero.title_line3', HERO_COPY.titleLine3),
      subtitle: pick('hero.subtitle', HERO_COPY.subtitle),
      cta: pick('hero.cta', HERO_COPY.cta),
      contests: pick('navigation.contests', HERO_COPY.contests),
      support: pick('hero.trust.support', HERO_COPY.support),
      free: pick('hero.trust.free', HERO_COPY.free),
    }),
    [pick],
  )
}

export function Hero() {
  const router = useRouter()
  const { isAuthenticated } = useAuth()
  const copy = useHeroText()

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-gradient-to-br from-white via-blue-50/30 to-purple-50/30 dark:from-gray-900 dark:via-gray-800/50 dark:to-gray-900 pt-20 md:pt-16">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-br from-myhigh5-primary/20 to-myhigh5-secondary/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-gradient-to-br from-purple-400/20 to-cyan-400/20 rounded-full blur-3xl animate-pulse delay-1000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-br from-blue-200/10 to-purple-200/10 rounded-full blur-3xl" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] opacity-40" />
      </div>

      <div className="container px-4 md:px-6 relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center min-h-[calc(100vh-5rem)] md:min-h-[calc(100vh-4rem)]">
          <div className="flex flex-col space-y-8 lg:space-y-10 text-center lg:text-left">
            <div className="space-y-6 lg:space-y-8">
              <h1 className="text-xl sm:text-2xl md:text-2xl lg:text-3xl xl:text-4xl font-black tracking-tight leading-[1.1] text-gray-900 dark:text-white">
                <span className="block">{copy.titleLine1}</span>
                <span className="block text-myhigh5-primary md:bg-gradient-to-r md:from-myhigh5-primary md:via-myhigh5-secondary md:to-myhigh5-primary md:bg-clip-text md:text-transparent">
                  {copy.titleLine2}
                </span>
                <span className="block">{copy.titleLine3}</span>
              </h1>
              <p className="max-w-2xl mx-auto lg:mx-0 text-lg sm:text-xl md:text-2xl text-gray-600 dark:text-gray-300 leading-relaxed font-medium">
                {copy.subtitle}
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-4 sm:gap-5 justify-center lg:justify-start pt-2 w-full">
              <Button
                size="lg"
                onClick={() => router.push('/register')}
                className="group w-full sm:w-auto min-h-[3.25rem] text-base sm:text-lg px-8 sm:px-10 py-6 sm:py-7 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary hover:from-myhigh5-primary-dark hover:to-myhigh5-secondary-dark text-white font-bold rounded-xl shadow-xl"
              >
                <span className="inline-block text-white">{copy.cta}</span>
                <ArrowRight className="ml-2 h-5 w-5 shrink-0 text-white group-hover:translate-x-1 transition-transform" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                onClick={() => router.push(isAuthenticated ? '/dashboard/contests' : '/contests')}
                className="w-full sm:w-auto min-h-[3.25rem] text-base sm:text-lg px-8 sm:px-10 py-6 sm:py-7 border-2 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white font-semibold rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                <Trophy className="mr-2 h-5 w-5 shrink-0" />
                <span className="inline-block text-gray-900 dark:text-white">{copy.contests}</span>
              </Button>
            </div>

            <div className="flex flex-wrap items-center justify-center lg:justify-start gap-4 sm:gap-6 pt-2">
              <div className="flex items-center gap-3 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-full px-4 py-2 border border-gray-200/50 dark:border-gray-700/50">
                <CheckCircle2 className="w-5 h-5 shrink-0 text-green-500" />
                <span className="text-sm sm:text-base text-gray-800 dark:text-gray-100 font-medium">
                  {copy.support}
                </span>
              </div>
              <div className="flex items-center gap-3 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-full px-4 py-2 border border-gray-200/50 dark:border-gray-700/50">
                <CheckCircle2 className="w-5 h-5 shrink-0 text-green-500" />
                <span className="text-sm sm:text-base text-gray-800 dark:text-gray-100 font-medium">
                  {copy.free}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center">
            <div className="w-full max-w-lg">
              <div className="relative">
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
