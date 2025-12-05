"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ArrowRight, Sparkles, Trophy, Users, Gift } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

export function CTA() {
  const { t } = useLanguage()

  return (
    <section className="" style={{background: 'linear-gradient(to right, rgba(30, 64, 175, 0.1), rgba(8, 145, 178, 0.05))'}}>
      <div className="container px-4 md:px-6">
        <div className="mx-auto max-w-4xl text-center space-y-8">
          <div className="space-y-4">
            <h2 className="text-3xl font-bold tracking-tighter sm:text-4xl md:text-5xl dsm-title">
              {t('cta.title')}
            </h2>
            <p className="mx-auto max-w-[600px] dsm-subtitle md:text-xl/relaxed">
              {t('cta.subtitle')}
            </p>
          </div>
          <Card className="relative overflow-hidden border-0 shadow-2xl" style={{background: 'rgba(255, 255, 255, 0.95)', backdropFilter: 'blur(10px)'}}>
            <CardContent className="p-8 md:p-12">
              <div className="flex flex-col items-center text-center space-y-8">
                {/* Icon */}
                <div className="flex items-center justify-center w-16 h-16 rounded-full" style={{background: 'rgba(30, 64, 175, 0.1)'}}>
                  <Sparkles className="w-8 h-8" style={{color: '#1e40af'}} />
                </div>

                {/* Features highlights */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-2xl">
                  <div className="flex flex-col items-center space-y-2">
                    <Trophy className="w-6 h-6" style={{color: '#1e40af'}} />
                    <span className="text-sm font-semibold" style={{color: '#1e40af'}}>{t('cta.features.free_contests')}</span>
                  </div>
                  <div className="flex flex-col items-center space-y-2">
                    <Users className="w-6 h-6" style={{color: '#1e40af'}} />
                    <span className="text-sm font-semibold" style={{color: '#1e40af'}}>{t('cta.features.active_community')}</span>
                  </div>
                  <div className="p-6 rounded-2xl dsm-bg-card dsm-hover-card">
                    <div className="flex flex-col items-center space-y-3">
                      <div className="w-12 h-12 rounded-lg flex items-center justify-center dsm-bg-primary">
                        <Gift className="h-6 w-6 dsm-text-white" />
                      </div>
                      <span className="text-sm font-semibold dsm-text-primary">
                        {t('cta.features.real_rewards')}
                      </span>
                    </div>
                  </div>
                </div>

                {/* CTA Buttons */}
                <div className="flex flex-col sm:flex-row gap-4">
                  <Button 
                    size="lg" 
                    className="text-lg px-8 py-4 font-semibold dsm-btn-primary"
                  >
                    {t('cta.button')}
                    <ArrowRight className="ml-2 h-5 w-5" />
                  </Button>
                  <Button 
                    variant="outline" 
                    size="lg" 
                    className="text-lg px-8 font-semibold rounded-lg transition-all duration-300 hover:-translate-y-1"
                    style={{
                      color: '#1e40af',
                      borderColor: '#1e40af',
                      borderWidth: '2px'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'rgba(30, 64, 175, 0.1)'
                      e.currentTarget.style.color = '#FFFF79'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent'
                      e.currentTarget.style.color = '#1e40af'
                    }}
                  >
                    {t('navigation.contests')}
                  </Button>
                </div>

                {/* Trust indicators */}
                <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-gray-600 font-medium">
                  <span>✓ {t('cta.trust.instant')}</span>
                  <span>✓ {t('cta.trust.secure')}</span>
                  <span>✓ {t('cta.trust.support')}</span>
                </div>
              </div>
            </CardContent>

            {/* Background decorations */}
            <div className="absolute top-0 right-0 w-32 h-32 rounded-full blur-3xl" style={{background: 'rgba(30, 64, 175, 0.05)'}} />
            <div className="absolute bottom-0 left-0 w-24 h-24 rounded-full blur-2xl" style={{background: 'rgba(8, 145, 178, 0.05)'}} />
          </Card>
        </div>
      </div>
    </section>
  )
}
