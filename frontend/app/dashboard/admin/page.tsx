'use client'

import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useEffect, useState } from 'react'
import { AlertCircle } from 'lucide-react'
import api from '@/lib/api'
import { StatsCard } from '@/components/dashboard/stats-card'
import { QuickActionCard } from '@/components/dashboard/quick-action-card'
import { ReportsCard } from '@/components/dashboard/reports-card'
import { UserProgressChart } from '@/components/dashboard/user-progress-chart'
import { Calendar, Zap, Users, FileCheck, Settings, Trophy, UserCheck, CheckCircle2, Clock, XCircle, MessageCircle, ThumbsUp, Flag } from 'lucide-react'

interface Statistics {
  seasons: { total: number }
  contests: { total: number; active: number; inactive: number }
  contestants: { total: number; pending: number; verified: number; rejected: number }
  users: { total: number; active: number; admin: number; verified: number }
  votes: { total: number }
  comments: { total: number }
  reports: { total: number; pending: number; reviewed: number; resolved: number }
}

interface UserProgressData {
  date: string
  total: number
  active: number
  new: number
}

export default function AdminDashboard() {
  const { user, isLoading } = useAuth()
  const { t } = useLanguage()
  const router = useRouter()
  const [isAdmin, setIsAdmin] = useState(false)
  const [stats, setStats] = useState<Statistics | null>(null)
  const [loadingStats, setLoadingStats] = useState(true)
  const [userProgressData, setUserProgressData] = useState<UserProgressData[]>([])
  const [progressPeriod, setProgressPeriod] = useState<'today' | 'yesterday' | 'week' | 'month' | 'year'>('week')

  // Palette de couleurs uniforme et harmonieuse
  const colorPalette = {
    seasons: {
      bg: 'bg-blue-100 dark:bg-blue-900/50',
      text: 'text-blue-600 dark:text-blue-400',
      gradientFrom: 'from-blue-500',
      gradientTo: 'to-blue-600'
    },
    contests: {
      bg: 'bg-amber-100 dark:bg-amber-900/50',
      text: 'text-amber-600 dark:text-amber-400',
      gradientFrom: 'from-amber-500',
      gradientTo: 'to-amber-600'
    },
    contestants: {
      bg: 'bg-emerald-100 dark:bg-emerald-900/50',
      text: 'text-emerald-600 dark:text-emerald-400',
      gradientFrom: 'from-emerald-500',
      gradientTo: 'to-emerald-600'
    },
    kyc: {
      bg: 'bg-violet-100 dark:bg-violet-900/50',
      text: 'text-violet-600 dark:text-violet-400',
      gradientFrom: 'from-violet-500',
      gradientTo: 'to-violet-600'
    },
    users: {
      bg: 'bg-indigo-100 dark:bg-indigo-900/50',
      text: 'text-indigo-600 dark:text-indigo-400',
      gradientFrom: 'from-indigo-500',
      gradientTo: 'to-indigo-600'
    },
    votes: {
      bg: 'bg-orange-100 dark:bg-orange-900/50',
      text: 'text-orange-600 dark:text-orange-400',
      gradientFrom: 'from-orange-500',
      gradientTo: 'to-orange-600'
    },
    comments: {
      bg: 'bg-cyan-100 dark:bg-cyan-900/50',
      text: 'text-cyan-600 dark:text-cyan-400',
      gradientFrom: 'from-cyan-500',
      gradientTo: 'to-cyan-600'
    },
    reports: {
      bg: 'bg-rose-100 dark:bg-rose-900/50',
      text: 'text-rose-600 dark:text-rose-400',
      gradientFrom: 'from-rose-500',
      gradientTo: 'to-rose-600'
    }
  }

  const adminStats = [
    {
      title: t('admin.seasons.title'),
      description: t('admin.seasons.description'),
      icon: Calendar,
      href: '/dashboard/admin/seasons',
      gradientFrom: colorPalette.seasons.gradientFrom,
      gradientTo: colorPalette.seasons.gradientTo
    },
    {
      title: t('admin.contests.title'),
      description: t('admin.contests.description'),
      icon: Zap,
      href: '/dashboard/admin/contests',
      gradientFrom: colorPalette.contests.gradientFrom,
      gradientTo: colorPalette.contests.gradientTo
    },
    {
      title: t('admin.contestants.title'),
      description: t('admin.contestants.description'),
      icon: Users,
      href: '/dashboard/admin/contestants',
      gradientFrom: colorPalette.contestants.gradientFrom,
      gradientTo: colorPalette.contestants.gradientTo
    },
    {
      title: t('admin.kyc.title'),
      description: t('admin.kyc.description'),
      icon: FileCheck,
      href: '/dashboard/admin/kyc',
      gradientFrom: colorPalette.kyc.gradientFrom,
      gradientTo: colorPalette.kyc.gradientTo
    },
    {
      title: t('admin.users.title'),
      description: t('admin.users.description'),
      icon: Settings,
      href: '/dashboard/admin/users',
      gradientFrom: colorPalette.users.gradientFrom,
      gradientTo: colorPalette.users.gradientTo
    },
    {
      title: t('admin.reports.title') || 'Rapports',
      description: t('admin.reports.description') || 'Gérer les signalements de contenus',
      icon: Flag,
      href: '/dashboard/admin/reports',
      gradientFrom: colorPalette.reports.gradientFrom,
      gradientTo: colorPalette.reports.gradientTo
    }
  ]

  useEffect(() => {
    if (!isLoading) {
      if (!user) {
        router.push('/login')
        return
      }
      
      if (user.is_admin) {
        setIsAdmin(true)
        fetchStatistics()
      } else {
        router.push('/dashboard')
      }
    }
  }, [user, isLoading, router])

  const getDaysForPeriod = (period: 'today' | 'yesterday' | 'week' | 'month' | 'year'): number => {
    switch (period) {
      case 'today':
        return 1
      case 'yesterday':
        return 2
      case 'week':
        return 7
      case 'month':
        return 30
      case 'year':
        return 365
      default:
        return 7
    }
  }

  const fetchStatistics = async (period: 'today' | 'yesterday' | 'week' | 'month' | 'year' = progressPeriod) => {
    try {
      setLoadingStats(true)
      const days = getDaysForPeriod(period)
      const [statsResponse, progressResponse] = await Promise.all([
        api.get('/api/v1/admin/statistics'),
        api.get(`/api/v1/admin/statistics/user-progress?days=${days}`)
      ])
      setStats(statsResponse.data)
      setUserProgressData(progressResponse.data)
    } catch (error) {
      console.error('Erreur lors du chargement des statistiques:', error)
    } finally {
      setLoadingStats(false)
    }
  }

  const handlePeriodChange = (period: 'today' | 'yesterday' | 'week' | 'month' | 'year') => {
    setProgressPeriod(period)
    fetchStatistics(period)
  }

  const handleGenerateReport = (type: string) => {
    // TODO: Implémenter la génération de rapport
    console.log('Génération du rapport:', type)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <div className="flex items-center gap-3 text-red-800">
            <AlertCircle className="h-5 w-5" />
            <p className="font-semibold">{t('common.access_denied')}</p>
          </div>
          <p className="text-red-700 mt-2 text-sm">
            {t('common.no_permission')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col space-y-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-myhigh5-primary dark:text-myhigh5-blue-400">{t('admin.title')}</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-3 text-lg">
          {t('common.welcome')} <span className="font-semibold text-myhigh5-primary dark:text-myhigh5-blue-400">{user?.full_name || user?.username}</span>! {t('admin.subtitle')}
        </p>
      </div>

      {/* Statistics Cards */}
      {loadingStats ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
        </div>
      ) : stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <StatsCard
            icon={Calendar}
            title={t('admin.seasons.title')}
            value={stats.seasons.total}
            subtitle={t('admin.dashboard.total_seasons') || 'Total des saisons'}
            iconBgColor={colorPalette.seasons.bg}
            iconColor={colorPalette.seasons.text}
          />
          <StatsCard
            icon={Trophy}
            title={t('admin.contests.title')}
            value={stats.contests.total}
            subtitle={`${stats.contests.active} ${t('admin.dashboard.active') || 'actifs'} • ${stats.contests.inactive} ${t('admin.dashboard.inactive') || 'inactifs'}`}
            iconBgColor={colorPalette.contests.bg}
            iconColor={colorPalette.contests.text}
          />
          <StatsCard
            icon={Users}
            title={t('admin.contestants.title') || 'Contestants'}
            value={stats.contestants.total}
            subtitle={`${stats.contestants.pending} en attente • ${stats.contestants.verified} vérifiés`}
            iconBgColor={colorPalette.contestants.bg}
            iconColor={colorPalette.contestants.text}
          />
          <StatsCard
            icon={UserCheck}
            title={t('admin.users.title')}
            value={stats.users.total}
            subtitle={`${stats.users.active} ${t('admin.dashboard.active') || 'actifs'} • ${stats.users.admin} ${t('admin.dashboard.admins') || 'admins'}`}
            iconBgColor={colorPalette.users.bg}
            iconColor={colorPalette.users.text}
          />
          <StatsCard
            icon={ThumbsUp}
            title={t('admin.dashboard.votes') || 'Votes'}
            value={stats.votes.total}
            subtitle={t('admin.dashboard.total_votes') || 'Total des votes'}
            iconBgColor={colorPalette.votes.bg}
            iconColor={colorPalette.votes.text}
          />
          <StatsCard
            icon={MessageCircle}
            title={t('admin.dashboard.comments') || 'Commentaires'}
            value={stats.comments.total}
            subtitle={t('admin.dashboard.total_comments') || 'Total des commentaires'}
            iconBgColor={colorPalette.comments.bg}
            iconColor={colorPalette.comments.text}
          />
          <StatsCard
            icon={Flag}
            title={t('admin.reports.title') || 'Rapports'}
            value={stats.reports.total}
            subtitle={`${stats.reports.pending} ${t('admin.reports.pending') || 'en attente'} • ${stats.reports.resolved} ${t('admin.reports.resolved') || 'résolus'}`}
            iconBgColor={colorPalette.reports.bg}
            iconColor={colorPalette.reports.text}
          />
              </div>
      )}

      {/* User Progress Chart */}
      {!loadingStats && userProgressData.length > 0 && (
        <div>
          <UserProgressChart 
            data={userProgressData}
            title={t('admin.dashboard.user_progress') || 'Progression des utilisateurs'}
            period={progressPeriod}
            onPeriodChange={handlePeriodChange}
          />
        </div>
      )}

      {/* Quick Actions */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
          {t('admin.dashboard.quick_actions') || 'Actions rapides'}
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {adminStats.map((stat) => (
            <QuickActionCard
              key={stat.href}
              title={stat.title}
              description={stat.description}
              icon={stat.icon}
              href={stat.href}
              gradientFrom={stat.gradientFrom}
              gradientTo={stat.gradientTo}
            />
          ))}
        </div>
      </div>

      {/* Reports Card */}
      <div>
        <ReportsCard onGenerateReport={handleGenerateReport} />
      </div>
    </div>
  )
}
