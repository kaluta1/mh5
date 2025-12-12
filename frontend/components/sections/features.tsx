"use client"

import * as React from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Trophy, DollarSign, Globe, Zap, Heart, ArrowRight } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

const featureIcons = {
  multi_level: Trophy,
  financial_rewards: DollarSign,
  international_reach: Globe,
  innovative_voting: Zap,
  varied_categories: Heart
}

export function Features() {
  const { t } = useLanguage()
  
  const features = [
    {
      key: 'multi_level',
      icon: featureIcons.multi_level
    },
    {
      key: 'financial_rewards',
      icon: featureIcons.financial_rewards
    },
    {
      key: 'international_reach',
      icon: featureIcons.international_reach
    },
    {
      key: 'innovative_voting',
      icon: featureIcons.innovative_voting
    },
    {
      key: 'varied_categories',
      icon: featureIcons.varied_categories
    }
  ]

  return (
    <section className="py-20 md:py-24 lg:py-32 relative">
      {/* Background decoration */}
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-gray-50/50 to-transparent dark:via-gray-900/50" />
      
      <div className="container px-4 md:px-6 relative z-10">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16 md:mb-20">
          <div className="inline-flex items-center gap-2 bg-myfav-primary/10 text-myfav-primary rounded-full px-4 py-2 text-sm font-semibold mb-6">
            <Trophy className="w-4 h-4" />
            <span>Fonctionnalités</span>
          </div>
          <h2 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight mb-6 bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            {t('features.title')}
          </h2>
          <p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 leading-relaxed">
            {t('features.subtitle')}
          </p>
        </div>
        
        {/* Features Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">
          {features.map((feature, index) => {
            const Icon = feature.icon
            return (
              <Card 
                key={index} 
                className="group relative overflow-hidden border-0 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm shadow-lg hover:shadow-2xl transition-all duration-500 hover:-translate-y-2 rounded-2xl"
              >
                {/* Gradient overlay on hover */}
                <div className="absolute inset-0 bg-gradient-to-br from-myfav-primary/0 to-myfav-secondary/0 group-hover:from-myfav-primary/5 group-hover:to-myfav-secondary/5 transition-all duration-500" />
                
                {/* Decorative corner */}
                <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-myfav-primary/10 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                
                <CardHeader className="relative z-10 pb-4">
                  <div className="flex items-start gap-4">
                    <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-myfav-primary to-myfav-secondary shadow-lg group-hover:scale-110 group-hover:rotate-3 transition-all duration-300 flex-shrink-0">
                      <Icon className="h-7 w-7 text-white" />
                    </div>
                    <div className="flex-1 pt-1">
                      <CardTitle className="text-xl font-bold text-gray-900 dark:text-white group-hover:text-myfav-primary dark:group-hover:text-myfav-blue-400 transition-colors">
                        {t(`features.items.${feature.key}.title`)}
                      </CardTitle>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="relative z-10">
                  <CardDescription className="text-base text-gray-600 dark:text-gray-400 leading-relaxed">
                    {t(`features.items.${feature.key}.description`)}
                  </CardDescription>
                  
                  {/* Arrow indicator */}
                  <div className="mt-6 flex items-center text-myfav-primary opacity-0 group-hover:opacity-100 translate-x-0 group-hover:translate-x-2 transition-all duration-300">
                    <ArrowRight className="h-5 w-5" />
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    </section>
  )
}
