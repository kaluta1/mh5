"use client"

import * as React from "react"
import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useRouter } from 'next/navigation'
import { 
  Heart, Trophy, Users, Star, TrendingUp, Eye, MessageCircle, 
  ThumbsUp, UserPlus, DollarSign, BarChart3, Zap, ChevronRight, X,
  UserCircle, Fingerprint
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DashboardSkeleton } from '@/components/ui/skeleton'
import { analyticsService, DashboardAnalytics } from '@/services/analytics-service'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import { logger } from '@/lib/logger'

// Lazy load heavy chart components
const PerformanceChart = dynamic(() => import('@/components/dashboard/analytics').then(mod => ({ default: mod.PerformanceChart })), {
  loading: () => <div className="h-64 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg" />
})

const ReactionsChart = dynamic(() => import('@/components/dashboard/analytics').then(mod => ({ default: mod.ReactionsChart })), {
  loading: () => <div className="h-64 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg" />
})

const ActivityChart = dynamic(() => import('@/components/dashboard/analytics').then(mod => ({ default: mod.ActivityChart })), {
  loading: () => <div className="h-64 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg" />
})

const AffiliatesGrowthChart = dynamic(() => import('@/components/dashboard/analytics').then(mod => ({ default: mod.AffiliatesGrowthChart })), {
  loading: () => <div className="h-64 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg" />
})

const CommissionsChart = dynamic(() => import('@/components/dashboard/analytics').then(mod => ({ default: mod.CommissionsChart })), {
  loading: () => <div className="h-64 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg" />
})

export default function DashboardPage() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const { t } = useLanguage()
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<'performance' | 'affiliates'>('performance')
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [showMobileStats, setShowMobileStats] = useState(false)
  const [showMobileAlert, setShowMobileAlert] = useState(true)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  // Fetch analytics data
  useEffect(() => {
    const fetchAnalytics = async () => {
      if (!isAuthenticated) return
      
      try {
        setAnalyticsLoading(true)
        const data = await analyticsService.getDashboardAnalytics()
        setAnalytics(data)
      } catch (error) {
        logger.error('Error fetching analytics:', error)
        setAnalytics(analyticsService.getDefaultAnalytics())
      } finally {
        setAnalyticsLoading(false)
      }
    }

    fetchAnalytics()
  }, [isAuthenticated])

  if (isLoading || analyticsLoading) {
    return <DashboardSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  const data = analytics || analyticsService.getDefaultAnalytics()
  const firstName = user.first_name || user.full_name?.split(' ')[0] || user.username

  // Vérifier si le profil est complet
  const isProfileComplete = !!(user.first_name && user.last_name && user.avatar_url && user.bio && user.gender && user.date_of_birth && user.country && user.city)
  
  // Vérifier si le KYC est passé
  const isKycVerified = !!user.identity_verified
  
  // L'utilisateur peut participer si le profil est complet
  // Le KYC sera vérifié par concours (certains concours n'exigent pas le KYC)
  const canParticipate = isProfileComplete

  return (
    <div className="space-y-6 pb-10">
      {/* Welcome Header */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-100 dark:border-gray-700 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p className="text-gray-500 dark:text-gray-400 text-sm">
              {t('dashboard.analytics.hello') || 'Bonjour'}, {firstName} 👋
            </p>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {t('dashboard.analytics.overview') || "Vue d'ensemble"}
            </h1>
          </div>
          
          <div className="flex flex-wrap gap-2">
            <Link
              href="/dashboard/contests"
              className="inline-flex items-center gap-2 bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white px-4 py-2.5 rounded-xl text-sm font-medium transition-colors"
            >
              <Trophy className="h-4 w-4" />
              {t('dashboard.nav.contests') || 'Concours'}
              <ChevronRight className="h-4 w-4" />
            </Link>
            <Link
              href="/dashboard/affiliates"
              className="inline-flex items-center gap-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors"
            >
              <Users className="h-4 w-4" />
              {t('dashboard.nav.affiliates') || 'Affiliés'}
            </Link>
          </div>
        </div>
      </div>

      {/* Alertes profil/KYC - Desktop */}
      {!canParticipate && (
        <div className="hidden md:block space-y-3">
          {!isProfileComplete && (
            <div className="flex items-center justify-between gap-4 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-amber-100 dark:bg-amber-800/50 rounded-lg">
                  <UserCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <p className="font-medium text-amber-900 dark:text-amber-200">
                    {t('contests.profile_incomplete_title') || 'Profil incomplet'}
                  </p>
                  <p className="text-sm text-amber-700 dark:text-amber-300">
                    {t('contests.profile_incomplete_message') || 'Complétez votre profil pour pouvoir participer aux concours.'}
                  </p>
                </div>
              </div>
              <Link href="/dashboard/settings">
                <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white rounded-lg">
                  {t('contests.complete_profile') || 'Compléter'}
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </Link>
            </div>
          )}

        </div>
      )}

      {/* Alerte KYC informative (non bloquante) - certains concours peuvent l'exiger */}
      {isProfileComplete && !isKycVerified && (
        <div className="hidden md:block">
          <div className="flex items-center justify-between gap-4 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700/50 rounded-xl">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-800/50 rounded-lg">
                <Fingerprint className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <p className="font-medium text-blue-900 dark:text-blue-200">
                  {t('contests.kyc_recommended_title') || 'Vérification d\'identité recommandée'}
                </p>
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  {t('contests.kyc_recommended_message') || 'Certains concours exigent la vérification KYC pour participer.'}
                </p>
              </div>
            </div>
            <Link href="/dashboard/kyc">
              <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg">
                {t('contests.verify_identity') || 'Vérifier'}
                <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </Link>
          </div>
        </div>
      )}

      {/* Notification flottante - Mobile - Profil incomplet */}
      {!canParticipate && showMobileAlert && (
        <div className="md:hidden fixed bottom-4 left-4 right-4 z-50 animate-in slide-in-from-bottom duration-300">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-xl shrink-0">
                <UserCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900 dark:text-white text-sm">
                  {t('contests.profile_incomplete_title') || 'Profil incomplet'}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">
                  {t('contests.profile_incomplete_message') || 'Complétez votre profil pour participer.'}
                </p>
              </div>
              <button
                onClick={() => setShowMobileAlert(false)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg shrink-0"
              >
                <X className="w-4 h-4 text-gray-400" />
              </button>
            </div>
            <Link href="/dashboard/settings" className="block mt-3">
              <Button size="sm" className="w-full bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-sm">
                {t('contests.complete_profile') || 'Compléter mon profil'}
                <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </Link>
          </div>
        </div>
      )}

      {/* Tab Switcher */}
      <div className="flex items-center justify-center">
        <div className="inline-flex items-center gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-xl">
          <button
            onClick={() => setActiveTab('performance')}
            className={`flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-lg transition-all ${
              activeTab === 'performance' 
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' 
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            <BarChart3 className="h-4 w-4" />
            {t('dashboard.analytics.performance') || 'Performance'}
          </button>
          <button
            onClick={() => setActiveTab('affiliates')}
            className={`flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-lg transition-all ${
              activeTab === 'affiliates' 
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' 
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            <UserPlus className="h-4 w-4" />
            {t('dashboard.analytics.affiliates') || 'Affiliés'}
          </button>
        </div>
      </div>

      {/* Mobile Stats Button */}
      <button
        onClick={() => setShowMobileStats(true)}
        className="md:hidden w-full bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700 flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-myhigh5-primary/10 flex items-center justify-center">
            <BarChart3 className="h-5 w-5 text-myhigh5-primary" />
          </div>
          <div className="text-left">
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {t('dashboard.analytics.view_stats') || 'Voir les statistiques'}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {data.total_votes.toLocaleString()} votes • {data.total_views.toLocaleString()} vues
            </p>
          </div>
        </div>
        <ChevronRight className="h-5 w-5 text-gray-400" />
      </button>

      {/* Mobile Stats Dialog */}
      {showMobileStats && (
        <div className="md:hidden fixed inset-0 z-50 flex items-end">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setShowMobileStats(false)}
          />
          
          {/* Dialog */}
          <div className="relative w-full bg-white dark:bg-gray-800 rounded-t-3xl p-6 pb-8 animate-in slide-in-from-bottom duration-300 max-h-[85vh] overflow-y-auto">
            {/* Handle */}
            <div className="absolute top-3 left-1/2 -translate-x-1/2 w-12 h-1.5 bg-gray-300 dark:bg-gray-600 rounded-full" />
            
            {/* Header */}
            <div className="flex items-center justify-between mb-6 pt-2">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                {t('dashboard.analytics.statistics') || 'Statistiques'}
              </h3>
              <button
                onClick={() => setShowMobileStats(false)}
                className="w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center"
              >
                <X className="h-4 w-4 text-gray-500 dark:text-gray-400" />
              </button>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-4">
                <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center mb-3">
                  <ThumbsUp className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {data.total_votes.toLocaleString()}
                </p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t('dashboard.analytics.total_votes') || 'Votes'}
                  </p>
                  {data.votes_change !== 0 && (
                    <span className={`text-xs font-medium ${data.votes_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {data.votes_change > 0 ? '+' : ''}{data.votes_change}%
                    </span>
                  )}
                </div>
              </div>

              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-4">
                <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center mb-3">
                  <MessageCircle className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                </div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {data.total_comments.toLocaleString()}
                </p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t('dashboard.analytics.comments') || 'Commentaires'}
                  </p>
                  {data.comments_change !== 0 && (
                    <span className={`text-xs font-medium ${data.comments_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {data.comments_change > 0 ? '+' : ''}{data.comments_change}%
                    </span>
                  )}
                </div>
              </div>

              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-4">
                <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center mb-3">
                  <Eye className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                </div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {data.total_views.toLocaleString()}
                </p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t('dashboard.analytics.total_views') || 'Vues'}
                  </p>
                  {data.views_change !== 0 && (
                    <span className={`text-xs font-medium ${data.views_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {data.views_change > 0 ? '+' : ''}{data.views_change}%
                    </span>
                  )}
                </div>
              </div>

              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-4">
                <div className="w-10 h-10 rounded-xl bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center mb-3">
                  <Heart className="h-5 w-5 text-rose-600 dark:text-rose-400" />
                </div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {data.total_reactions.toLocaleString()}
                </p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t('dashboard.analytics.reactions') || 'Réactions'}
                  </p>
                  {data.reactions_change !== 0 && (
                    <span className={`text-xs font-medium ${data.reactions_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {data.reactions_change > 0 ? '+' : ''}{data.reactions_change}%
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Quick Stats */}
            <div className="mt-4 space-y-3">
              <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-myhigh5-primary/10 flex items-center justify-center">
                    <Trophy className="h-5 w-5 text-myhigh5-primary" />
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t('dashboard.analytics.active_contests') || 'Concours actifs'}
                  </p>
                </div>
                <p className="text-xl font-bold text-gray-900 dark:text-white">{data.active_contests}</p>
              </div>

              <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                    <Star className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t('dashboard.analytics.best_ranking') || 'Meilleur classement'}
                  </p>
                </div>
                <p className="text-xl font-bold text-gray-900 dark:text-white">#{data.best_ranking || '-'}</p>
              </div>

              <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                    <Zap className="h-5 w-5 text-green-600 dark:text-green-400" />
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t('dashboard.analytics.engagement') || 'Engagement'}
                  </p>
                </div>
                <p className="text-xl font-bold text-green-600 dark:text-green-400">+{data.engagement_change}%</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stats Overview - Desktop Only */}
      <div className="hidden md:grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
              <ThumbsUp className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.total_votes.toLocaleString()}
          </p>
          <div className="flex items-center justify-between mt-1">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.analytics.total_votes') || 'Votes'}
            </p>
            {data.votes_change !== 0 && (
              <span className={`text-xs font-medium ${data.votes_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                {data.votes_change > 0 ? '+' : ''}{data.votes_change}%
              </span>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
              <MessageCircle className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
            </div>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.total_comments.toLocaleString()}
          </p>
          <div className="flex items-center justify-between mt-1">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.analytics.comments') || 'Commentaires'}
            </p>
            {data.comments_change !== 0 && (
              <span className={`text-xs font-medium ${data.comments_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                {data.comments_change > 0 ? '+' : ''}{data.comments_change}%
              </span>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
              <Eye className="h-5 w-5 text-amber-600 dark:text-amber-400" />
            </div>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.total_views.toLocaleString()}
          </p>
          <div className="flex items-center justify-between mt-1">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.analytics.total_views') || 'Vues'}
            </p>
            {data.views_change !== 0 && (
              <span className={`text-xs font-medium ${data.views_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                {data.views_change > 0 ? '+' : ''}{data.views_change}%
              </span>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center">
              <Heart className="h-5 w-5 text-rose-600 dark:text-rose-400" />
            </div>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.total_reactions.toLocaleString()}
          </p>
          <div className="flex items-center justify-between mt-1">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.analytics.reactions') || 'Réactions'}
            </p>
            {data.reactions_change !== 0 && (
              <span className={`text-xs font-medium ${data.reactions_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                {data.reactions_change > 0 ? '+' : ''}{data.reactions_change}%
              </span>
            )}
          </div>
        </div>
      </div>

      {activeTab === 'performance' ? (
        <div className="space-y-6">
          {/* Performance Charts - Desktop Only */}
          <div className="hidden md:grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <PerformanceChart data={data.contest_performance} />
            </div>
            <ReactionsChart data={data.reactions_by_type} />
          </div>

          {/* Weekly Activity - Desktop Only */}
          <div className="hidden md:block">
            <ActivityChart data={data.weekly_activity} />
          </div>

          {/* Quick Stats Cards - Desktop Only */}
          <div className="hidden md:grid md:grid-cols-3 gap-4">
            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-100 dark:border-gray-700">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-myhigh5-primary/10 flex items-center justify-center">
                  <Trophy className="h-6 w-6 text-myhigh5-primary" />
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded-md">
                  {t('dashboard.analytics.this_month') || 'Ce mois'}
                </span>
              </div>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{data.active_contests}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t('dashboard.analytics.active_contests') || 'Concours actifs'}
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-100 dark:border-gray-700">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                  <Star className="h-6 w-6 text-amber-600 dark:text-amber-400" />
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded-md">
                  {t('dashboard.analytics.total') || 'Total'}
                </span>
              </div>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">#{data.best_ranking || '-'}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t('dashboard.analytics.best_ranking') || 'Meilleur classement'}
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-100 dark:border-gray-700">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                  <Zap className="h-6 w-6 text-green-600 dark:text-green-400" />
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded-md">
                  {t('dashboard.analytics.last_7_days') || '7 jours'}
                </span>
              </div>
              <p className="text-3xl font-bold text-green-600 dark:text-green-400">+{data.engagement_change}%</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t('dashboard.analytics.engagement') || 'Engagement'}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Affiliates Stats - Desktop Only */}
          <div className="hidden md:grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-100 dark:border-gray-700">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                  <UserPlus className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{data.affiliates_stats.direct_count}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t('dashboard.analytics.direct_affiliates') || 'Affiliés directs'}
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-100 dark:border-gray-700">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                  <Users className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                </div>
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{data.affiliates_stats.total_network}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t('dashboard.analytics.total_network') || 'Réseau total'}
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-100 dark:border-gray-700">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                  <DollarSign className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                </div>
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">${data.affiliates_stats.total_commissions}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t('dashboard.analytics.commissions') || 'Commissions'}
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-100 dark:border-gray-700">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center">
                  <TrendingUp className="h-5 w-5 text-rose-600 dark:text-rose-400" />
                </div>
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{data.affiliates_stats.conversion_rate}%</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t('dashboard.analytics.conversion_rate') || 'Taux de conversion'}
              </p>
            </div>
          </div>

          {/* Affiliates Charts - Desktop Only */}
          <div className="hidden md:grid lg:grid-cols-2 gap-6">
            <AffiliatesGrowthChart data={data.affiliates_growth} />
            <CommissionsChart data={data.affiliates_growth} />
          </div>

          {/* CTA for Affiliates */}
          <div className="bg-gradient-to-r from-myhigh5-primary to-myhigh5-primary/80 rounded-2xl p-6 md:p-8">
            <div className="flex flex-col md:flex-row items-center justify-between gap-4">
              <div className="text-center md:text-left">
                <h3 className="text-xl font-bold text-white mb-2">
                  {t('affiliates.grow_network') || 'Développez votre réseau'}
                </h3>
                <p className="text-white/80 text-sm max-w-md">
                  {t('affiliates.invite_friends') || 'Invitez vos amis et gagnez des commissions sur leurs activités'}
                </p>
              </div>
              <Link
                href="/dashboard/affiliates"
                className="inline-flex items-center gap-2 bg-white text-myhigh5-primary px-5 py-2.5 rounded-xl text-sm font-semibold transition-all hover:shadow-lg whitespace-nowrap"
              >
                <UserPlus className="h-4 w-4" />
                {t('affiliates.invite_now') || 'Inviter maintenant'}
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
