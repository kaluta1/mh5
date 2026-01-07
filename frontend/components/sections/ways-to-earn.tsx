"use client"

import * as React from "react"
import { TrendingUp, Users, BookOpen, Award, ShoppingBag, Megaphone, Target, DollarSign } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

export function WaysToEarn() {
  const { t } = useLanguage()

  const earningMethods = [
    {
      key: 'kyc_payments',
      icon: Users,
      title: t('landing.ways_to_earn.kyc_payments.title') || 'KYC Payments',
      description: t('landing.ways_to_earn.kyc_payments.description') || 'Earn commissions when members in your network complete their KYC verification',
      commission: t('landing.ways_to_earn.kyc_payments.commission') || '20% on Level 1, 2% on Levels 2-10'
    },
    {
      key: 'founding_membership',
      icon: BookOpen,
      title: t('landing.ways_to_earn.founding_membership.title') || 'Founding Membership',
      description: t('landing.ways_to_earn.founding_membership.description') || 'Earn commissions when network members join as Founding Members ($100 joining fee)',
      commission: t('landing.ways_to_earn.founding_membership.commission') || '$20 on Level 1, $2 on Levels 2-10'
    },
    {
      key: 'annual_membership',
      icon: Award,
      title: t('landing.ways_to_earn.annual_membership.title') || 'Annual Membership Fee',
      description: t('landing.ways_to_earn.annual_membership.description') || 'Earn commissions when Founding Members pay their annual membership fee ($50)',
      commission: t('landing.ways_to_earn.annual_membership.commission') || '$10 on Level 1, $1 on Levels 2-10'
    },
    {
      key: 'club_memberships',
      icon: Users,
      title: t('landing.ways_to_earn.club_memberships.title') || 'Club Memberships',
      description: t('landing.ways_to_earn.club_memberships.description') || 'Earn commissions on paid club membership fees. The website charges 20% of membership fees, and you earn a share of that.',
      commission: t('landing.ways_to_earn.club_memberships.commission') || '20% on Level 1, 2% on Levels 2-10'
    },
    {
      key: 'shop_purchases',
      icon: ShoppingBag,
      title: t('landing.ways_to_earn.shop_purchases.title') || 'Shop Purchases',
      description: t('landing.ways_to_earn.shop_purchases.description') || 'Earn commissions on digital content purchases in the MyHigh5 shop. The website charges 20% platform fees, and you earn a share of that.',
      commission: t('landing.ways_to_earn.shop_purchases.commission') || '20% on Level 1, 2% on Levels 2-10'
    },
    {
      key: 'ad_revenue',
      icon: Megaphone,
      title: t('landing.ways_to_earn.ad_revenue.title') || 'Ad Revenue Sharing',
      description: t('landing.ways_to_earn.ad_revenue.description') || 'Earn commissions from ad revenues generated on contest pages of members in your network',
      commission: t('landing.ways_to_earn.ad_revenue.commission') || '10% on Level 1, 1% on Levels 2-10'
    },
    {
      key: 'ad_campaigns',
      icon: Target,
      title: t('landing.ways_to_earn.ad_campaigns.title') || 'Advertisement Campaigns',
      description: t('landing.ways_to_earn.ad_campaigns.description') || 'Earn commissions from advertising campaigns purchased by members in your network through the native ad platform',
      commission: t('landing.ways_to_earn.ad_campaigns.commission') || 'Variable commission structure'
    }
  ]

  return (
    <section className="py-20 md:py-24 lg:py-32 relative">
      {/* Background decoration */}
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-gray-50/50 to-transparent dark:via-gray-900/50" />
      
      <div className="container px-4 md:px-6 relative z-10">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16 md:mb-20">
          <div className="inline-flex items-center gap-2 bg-myhigh5-primary/10 text-myhigh5-primary rounded-full px-4 py-2 text-sm font-semibold mb-6">
            <DollarSign className="w-4 h-4" />
            <span>{t('landing.ways_to_earn.badge') || 'Gagnez de l\'argent'}</span>
          </div>
          <h2 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight mb-6 bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            {t('landing.ways_to_earn.title') || 'Différentes façons de gagner'}
          </h2>
          <p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 leading-relaxed">
            {t('landing.ways_to_earn.subtitle') || 'Rejoignez notre programme d\'affiliation et gagnez des commissions sur plusieurs sources de revenus'}
          </p>
        </div>

        {/* Earning Methods Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">
          {earningMethods.map((method, index) => {
            const Icon = method.icon
            return (
              <div
                key={index}
                className="group relative overflow-hidden bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl p-6 border border-gray-200/50 dark:border-gray-700/50 shadow-lg hover:shadow-2xl transition-all duration-500 hover:-translate-y-2"
              >
                {/* Gradient overlay on hover */}
                <div className="absolute inset-0 bg-gradient-to-br from-myhigh5-primary/0 to-myhigh5-secondary/0 group-hover:from-myhigh5-primary/5 group-hover:to-myhigh5-secondary/5 transition-all duration-500" />
                
                {/* Decorative corner */}
                <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-myhigh5-primary/10 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                
                <div className="relative z-10">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-myhigh5-primary/10 to-myhigh5-secondary/10 dark:from-myhigh5-primary/20 dark:to-myhigh5-secondary/20 flex items-center justify-center group-hover:scale-110 transition-transform">
                      <Icon className="w-6 h-6 text-myhigh5-primary" />
                    </div>
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white group-hover:text-myhigh5-primary dark:group-hover:text-myhigh5-blue-400 transition-colors">
                      {method.title}
                    </h3>
                  </div>
                  
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 leading-relaxed">
                    {method.description}
                  </p>
                  
                  <div className="pt-4 border-t border-gray-200/50 dark:border-gray-700/50">
                    <p className="text-lg font-bold text-myhigh5-primary whitespace-pre-line">
                      {method.commission}
                    </p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

