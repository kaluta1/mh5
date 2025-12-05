"use client"

import * as React from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Trophy, DollarSign, Globe, Zap, Heart } from "lucide-react"
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
    <section >
      <div>
        <div className="flex flex-col items-start justify-start space-y-4 text-start">
          <div className="space-y-2">
            <h2 className="text-3xl font-bold tracking-tighter sm:text-4xl md:text-5xl dsm-title">
              {t('features.title')}
            </h2>
            <p className="mx-auto dsm-subtitle md:text-xl/relaxed lg:text-base/relaxed xl:text-xl/relaxed">
              {t('features.subtitle')}
            </p>
          </div>  
        </div>
        
        <div className="mx-auto grid items-center gap-6 py-16 lg:grid-cols-3 lg:gap-12">
          {features.map((feature, index) => (
            <Card 
              key={index} 
              className="relative overflow-hidden group dsm-bg-card dsm-hover-card rounded-xl "
            >
              <CardHeader>
                <div className="flex items-center space-x-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-lg dsm-bg-primary dsm-text-white transition-all duration-300">
                    <feature.icon className="h-6 w-6" />
                  </div>
                  <div>
                    <CardTitle className="text-xl font-bold dsm-text-primary">
                      {t(`features.items.${feature.key}.title`)}
                    </CardTitle>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <CardDescription className="text-base dsm-text-gray">
                  {t(`features.items.${feature.key}.description`)}
                </CardDescription>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
