"use client"

import * as React from "react"
import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useRouter } from 'next/navigation'
import { 
  Heart, Trophy, Users, Star, TrendingUp, Eye, MessageCircle, 
  ThumbsUp, UserPlus, DollarSign, BarChart3, Sparkles,
  ArrowRight, Zap
} from 'lucide-react'
import { 
  StatCard, 
  PerformanceChart, 
  ReactionsChart, 
  ActivityChart,
  AffiliatesGrowthChart,
  CommissionsChart
} from '@/components/dashboard/analytics'
import { DashboardSkeleton } from '@/components/ui/skeleton'
import { analyticsService, DashboardAnalytics } from '@/services/analytics-service'
import Link from 'next/link'

export default function DashboardPage() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const { t } = useLanguage()
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<'performance' | 'affiliates'>('performance')
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(true)

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
        console.error('Error fetching analytics:', error)
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
  const firstName = user.full_name?.split(' ')[0] || user.username

  return (
    <div className="space-y-8 pb-10">
      {/* Welcome Header */}
      <div className="relative overflow-hidden bg-gradient-to-br from-myfav-primary via-purple-600 to-purple-800 rounded-2xl p-6 md:p-8">
        <div className="absolute inset-0 bg-grid-white/10 [mask-image:linear-gradient(0deg,transparent,rgba(255,255,255,0.5))]" />
        <div className="absolute -top-24 -right-24 w-64 h-64 bg-white/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-white/10 rounded-full blur-3xl" />
        
        <div className="relative flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-yellow-300 animate-pulse" />
              <span className="text-white/80 text-sm font-medium">
                {t('dashboard.analytics.hello') || 'Hello'}, {firstName}!
              </span>
            </div>
            <h1 className="text-2xl md:text-3xl font-bold text-white">
              {t('dashboard.analytics.overview') || "Here's an overview of your performance"}
            </h1>
            <p className="text-white/70 text-sm md:text-base max-w-lg">
              {t('dashboard.subtitle') || 'Track your progress, manage your contests, and grow your network'}
            </p>
          </div>
          
          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard/contests"
              className="inline-flex items-center gap-2 bg-white/20 hover:bg-white/30 backdrop-blur-sm text-white px-4 py-2.5 rounded-xl font-medium transition-all hover:scale-105"
            >
              <Trophy className="h-4 w-4" />
              {t('dashboard.nav.contests') || 'Contests'}
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/dashboard/affiliates"
              className="inline-flex items-center gap-2 bg-white text-myfav-primary px-4 py-2.5 rounded-xl font-medium transition-all hover:scale-105 hover:shadow-lg"
            >
              <Users className="h-4 w-4" />
              {t('dashboard.nav.affiliates') || 'Affiliates'}
            </Link>
          </div>
        </div>
      </div>

      {/* Tab Switcher */}
      <div className="flex items-center justify-center">
        <div className="inline-flex items-center gap-1 bg-gray-100 dark:bg-gray-800/50 p-1.5 rounded-2xl border border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setActiveTab('performance')}
            className={`relative px-6 py-2.5 text-sm font-semibold rounded-xl transition-all duration-300 ${
              activeTab === 'performance' 
                ? 'bg-white dark:bg-gray-900 text-myfav-primary shadow-md' 
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              {t('dashboard.analytics.performance') || 'Performance'}
            </span>
            {activeTab === 'performance' && (
              <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-8 h-1 bg-myfav-primary rounded-full" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('affiliates')}
            className={`relative px-6 py-2.5 text-sm font-semibold rounded-xl transition-all duration-300 ${
              activeTab === 'affiliates' 
                ? 'bg-white dark:bg-gray-900 text-myfav-primary shadow-md' 
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            <span className="flex items-center gap-2">
              <UserPlus className="h-4 w-4" />
              {t('dashboard.analytics.affiliates') || 'Affiliates'}
            </span>
            {activeTab === 'affiliates' && (
              <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-8 h-1 bg-myfav-primary rounded-full" />
            )}
          </button>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        <StatCard
          title={t('dashboard.analytics.total_votes') || 'Total Votes'}
          value={data.total_votes.toLocaleString()}
          change={data.votes_change}
          icon={ThumbsUp}
          iconColor="text-myfav-primary"
          iconBg="bg-myfav-primary/10"
        />
        <StatCard
          title={t('dashboard.analytics.comments') || 'Comments'}
          value={data.total_comments.toLocaleString()}
          change={data.comments_change}
          icon={MessageCircle}
          iconColor="text-myfav-primary"
          iconBg="bg-myfav-primary/10"
        />
        <StatCard
          title={t('dashboard.analytics.total_views') || 'Total Views'}
          value={data.total_views.toLocaleString()}
          change={data.views_change}
          icon={Eye}
          iconColor="text-myfav-primary"
          iconBg="bg-myfav-primary/10"
        />
        <StatCard
          title={t('dashboard.analytics.reactions') || 'Reactions'}
          value={data.total_reactions.toLocaleString()}
          change={data.reactions_change}
          icon={Heart}
          iconColor="text-myfav-primary"
          iconBg="bg-myfav-primary/10"
        />
      </div>

      {activeTab === 'performance' ? (
        <div className="space-y-6">
          {/* Performance Charts */}
          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <PerformanceChart data={data.contest_performance} />
            </div>
            <ReactionsChart data={data.reactions_by_type} />
          </div>

          {/* Weekly Activity */}
          <ActivityChart data={data.weekly_activity} />

          {/* Quick Stats - Performance */}
          <div className="grid md:grid-cols-3 gap-4">
            <div className="group relative overflow-hidden bg-gradient-to-br from-myfav-primary to-purple-700 rounded-2xl p-6 text-white transition-transform hover:scale-[1.02]">
              <div className="absolute inset-0 bg-grid-white/10" />
              <div className="absolute -right-8 -bottom-8 w-32 h-32 bg-white/10 rounded-full blur-2xl group-hover:scale-150 transition-transform" />
              <div className="relative">
                <div className="flex items-center justify-between mb-4">
                  <div className="p-2 bg-white/20 rounded-xl">
                    <Trophy className="h-6 w-6" />
                  </div>
                  <span className="text-xs bg-white/20 px-3 py-1 rounded-full font-medium">
                    {t('dashboard.analytics.this_month') || 'This month'}
                  </span>
                </div>
                <p className="text-4xl font-bold">{data.active_contests}</p>
                <p className="text-sm text-white/80 mt-1">
                  {t('dashboard.analytics.active_contests') || 'Active Contests'}
                </p>
              </div>
            </div>

            <div className="group relative overflow-hidden bg-gradient-to-br from-purple-600 to-purple-800 rounded-2xl p-6 text-white transition-transform hover:scale-[1.02]">
              <div className="absolute inset-0 bg-grid-white/10" />
              <div className="absolute -right-8 -bottom-8 w-32 h-32 bg-white/10 rounded-full blur-2xl group-hover:scale-150 transition-transform" />
              <div className="relative">
                <div className="flex items-center justify-between mb-4">
                  <div className="p-2 bg-white/20 rounded-xl">
                    <Star className="h-6 w-6" />
                  </div>
                  <span className="text-xs bg-white/20 px-3 py-1 rounded-full font-medium">
                    {t('dashboard.analytics.total') || 'Total'}
                  </span>
                </div>
                <p className="text-4xl font-bold">#{data.best_ranking || '-'}</p>
                <p className="text-sm text-white/80 mt-1">
                  {t('dashboard.analytics.best_ranking') || 'Best Ranking'}
                </p>
              </div>
            </div>

            <div className="group relative overflow-hidden bg-gradient-to-br from-purple-700 to-myfav-primary rounded-2xl p-6 text-white transition-transform hover:scale-[1.02]">
              <div className="absolute inset-0 bg-grid-white/10" />
              <div className="absolute -right-8 -bottom-8 w-32 h-32 bg-white/10 rounded-full blur-2xl group-hover:scale-150 transition-transform" />
              <div className="relative">
                <div className="flex items-center justify-between mb-4">
                  <div className="p-2 bg-white/20 rounded-xl">
                    <Zap className="h-6 w-6" />
                  </div>
                  <span className="text-xs bg-white/20 px-3 py-1 rounded-full font-medium">
                    {t('dashboard.analytics.last_7_days') || '7 days'}
                  </span>
                </div>
                <p className="text-4xl font-bold">+{data.engagement_change}%</p>
                <p className="text-sm text-white/80 mt-1">
                  {t('dashboard.analytics.engagement') || 'Engagement'}
                </p>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Affiliates Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
            <StatCard
              title={t('dashboard.analytics.direct_affiliates') || 'Direct Affiliates'}
              value={data.affiliates_stats.direct_count}
              icon={UserPlus}
              iconColor="text-myfav-primary"
              iconBg="bg-myfav-primary/10"
            />
            <StatCard
              title={t('dashboard.analytics.total_network') || 'Total Network'}
              value={data.affiliates_stats.total_network}
              icon={Users}
              iconColor="text-myfav-primary"
              iconBg="bg-myfav-primary/10"
            />
            <StatCard
              title={t('dashboard.analytics.commissions') || 'Commissions'}
              value={`$${data.affiliates_stats.total_commissions}`}
              icon={DollarSign}
              iconColor="text-myfav-primary"
              iconBg="bg-myfav-primary/10"
            />
            <StatCard
              title={t('dashboard.analytics.conversion_rate') || 'Conversion Rate'}
              value={`${data.affiliates_stats.conversion_rate}%`}
              icon={TrendingUp}
              iconColor="text-myfav-primary"
              iconBg="bg-myfav-primary/10"
            />
          </div>

          {/* Affiliates Charts */}
          <div className="grid lg:grid-cols-2 gap-6">
            <AffiliatesGrowthChart data={data.affiliates_growth} />
            <CommissionsChart data={data.affiliates_growth} />
          </div>

          {/* CTA for Affiliates */}
          <div className="relative overflow-hidden bg-gradient-to-r from-myfav-primary via-purple-600 to-purple-700 rounded-2xl p-8">
            <div className="absolute inset-0 bg-grid-white/10" />
            <div className="absolute -top-24 -right-24 w-64 h-64 bg-white/10 rounded-full blur-3xl" />
            <div className="relative flex flex-col md:flex-row items-center justify-between gap-6">
              <div className="text-center md:text-left">
                <h3 className="text-xl md:text-2xl font-bold text-white mb-2">
                  {t('affiliates.grow_network') || 'Grow Your Network'}
                </h3>
                <p className="text-white/80 max-w-md">
                  {t('affiliates.invite_friends') || 'Invite friends and earn commissions on their activities'}
                </p>
              </div>
              <Link
                href="/dashboard/affiliates"
                className="inline-flex items-center gap-2 bg-white text-myfav-primary px-6 py-3 rounded-xl font-semibold transition-all hover:scale-105 hover:shadow-lg whitespace-nowrap"
              >
                <UserPlus className="h-5 w-5" />
                {t('affiliates.invite_now') || 'Invite Now'}
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
