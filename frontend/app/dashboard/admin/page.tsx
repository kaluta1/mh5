'use client'

import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useEffect, useState } from 'react'
import { AlertCircle, TrendingUp, DollarSign, ArrowDownCircle, ArrowUpCircle, Users, Flag, Tag, BarChart3, Calendar } from 'lucide-react'
import api from '@/lib/api'
import { StatsCard } from '@/components/dashboard/stats-card'
import dynamic from 'next/dynamic'

// Lazy load heavy chart component
const UserProgressChart = dynamic(() => import('@/components/dashboard/user-progress-chart').then(mod => ({ default: mod.UserProgressChart })), {
  loading: () => <div className="h-64 animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg" />
})
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
// Note: Recharts kept as direct import for admin page (admin-only, not frequently accessed)
import { LineChart, Line, AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { cn } from '@/lib/utils'

interface DepositData {
  date: string
  amount: number
  count: number
}

interface WithdrawalData {
  date: string
  amount: number
  count: number
}

interface UserProgressData {
  date: string
  total: number
  active: number
  new: number
}

interface CategoryData {
  name: string
  count: number
  contests: number
}

interface ReportByType {
  category: number
  contest: number
  user: number
  contestant: number
  comment: number
  media: number
}

interface Statistics {
  deposits: {
    total_amount: number
    total_count: number
    chart_data: DepositData[]
  }
  withdrawals: {
    total_amount: number
    total_count: number
    chart_data: WithdrawalData[]
  }
  verified_users: number
  total_users: number
  categories: {
    total: number
    chart_data: CategoryData[]
  }
  reports: {
    total: number
    by_type: ReportByType
  }
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

type PeriodType = 'today' | 'yesterday' | 'week' | 'month' | 'year' | 'custom'

export default function AdminDashboard() {
  const { user, isLoading } = useAuth()
  const { t } = useLanguage()
  const router = useRouter()
  const [isAdmin, setIsAdmin] = useState(false)
  const [stats, setStats] = useState<Statistics | null>(null)
  const [loadingStats, setLoadingStats] = useState(true)
  const [loadingCharts, setLoadingCharts] = useState({
    deposits: false,
    withdrawals: false,
    users: false,
    categories: false
  })
  const [userProgressData, setUserProgressData] = useState<UserProgressData[]>([])
  const [progressPeriod, setProgressPeriod] = useState<PeriodType>('week')
  const [customStartDate, setCustomStartDate] = useState<string>('')
  const [customEndDate, setCustomEndDate] = useState<string>('')

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

  const getDaysForPeriod = (period: PeriodType, startDate?: string, endDate?: string): number => {
    if (period === 'custom' && startDate && endDate) {
      const start = new Date(startDate)
      const end = new Date(endDate)
      const diffTime = Math.abs(end.getTime() - start.getTime())
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
      return diffDays + 1
    }
    
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

  const getDateRange = (period: PeriodType, startDate?: string, endDate?: string): { start: Date, end: Date } => {
    const end = new Date()
    let start = new Date()
    
    if (period === 'custom' && startDate && endDate) {
      return {
        start: new Date(startDate),
        end: new Date(endDate)
      }
    }
    
    switch (period) {
      case 'today':
        start.setHours(0, 0, 0, 0)
        break
      case 'yesterday':
        start.setDate(start.getDate() - 1)
        start.setHours(0, 0, 0, 0)
        end.setDate(end.getDate() - 1)
        end.setHours(23, 59, 59, 999)
        break
      case 'week':
        start.setDate(start.getDate() - 6)
        start.setHours(0, 0, 0, 0)
        break
      case 'month':
        start.setDate(start.getDate() - 29)
        start.setHours(0, 0, 0, 0)
        break
      case 'year':
        start.setDate(start.getDate() - 364)
        start.setHours(0, 0, 0, 0)
        break
    }
    
    return { start, end }
  }

  const fetchStatistics = async (period: PeriodType = progressPeriod) => {
    try {
      setLoadingStats(true)
      const days = getDaysForPeriod(period, customStartDate, customEndDate)
      const dateRange = getDateRange(period, customStartDate, customEndDate)
      
      // Construire les paramètres pour les requêtes
      const params = new URLSearchParams()
      params.append('days', days.toString())
      if (period === 'custom' && customStartDate && customEndDate) {
        params.append('start_date', dateRange.start.toISOString().split('T')[0])
        params.append('end_date', dateRange.end.toISOString().split('T')[0])
      }
      
      const [statsResponse, progressResponse, depositsResponse, withdrawalsResponse] = await Promise.all([
        api.get('/api/v1/admin/statistics'),
        api.get(`/api/v1/admin/statistics/user-progress?${params.toString()}`),
        api.get(`/api/v1/admin/statistics/deposits?${params.toString()}`),
        api.get(`/api/v1/admin/statistics/withdrawals?${params.toString()}`)
      ])
      
      // Combiner les données - s'assurer que les données sont correctement extraites
      const combinedStats: Statistics = {
        deposits: depositsResponse?.data || { total_amount: 0, total_count: 0, chart_data: [] },
        withdrawals: withdrawalsResponse?.data || { total_amount: 0, total_count: 0, chart_data: [] },
        verified_users: statsResponse?.data?.users?.verified || 0,
        total_users: statsResponse?.data?.users?.total || 0,
        categories: statsResponse?.data?.categories || { total: 0, chart_data: [] },
        reports: statsResponse?.data?.reports || { total: 0, by_type: { category: 0, contest: 0, user: 0, contestant: 0, comment: 0, media: 0 } }
      }
      
      setStats(combinedStats)
      setUserProgressData(progressResponse?.data || [])
    } catch (error) {
      console.error('Erreur lors du chargement des statistiques:', error)
      // En cas d'erreur, initialiser avec des valeurs par défaut
      setStats({
        deposits: { total_amount: 0, total_count: 0, chart_data: [] },
        withdrawals: { total_amount: 0, total_count: 0, chart_data: [] },
        verified_users: 0,
        total_users: 0,
        categories: { total: 0, chart_data: [] },
        reports: { total: 0, by_type: { category: 0, contest: 0, user: 0, contestant: 0, comment: 0, media: 0 } }
      })
    } finally {
      setLoadingStats(false)
    }
  }

  const fetchChartData = async (chartType: 'deposits' | 'withdrawals' | 'users', period: PeriodType = progressPeriod) => {
    try {
      setLoadingCharts(prev => ({ ...prev, [chartType]: true }))
      const days = getDaysForPeriod(period, customStartDate, customEndDate)
      const dateRange = getDateRange(period, customStartDate, customEndDate)
      
      const params = new URLSearchParams()
      params.append('days', days.toString())
      if (period === 'custom' && customStartDate && customEndDate) {
        params.append('start_date', dateRange.start.toISOString().split('T')[0])
        params.append('end_date', dateRange.end.toISOString().split('T')[0])
      }
      
      if (chartType === 'deposits') {
        const response = await api.get(`/api/v1/admin/statistics/deposits?${params.toString()}`)
        setStats(prev => prev ? {
          ...prev,
          deposits: response.data || { total_amount: 0, total_count: 0, chart_data: [] }
        } : null)
      } else if (chartType === 'withdrawals') {
        const response = await api.get(`/api/v1/admin/statistics/withdrawals?${params.toString()}`)
        setStats(prev => prev ? {
          ...prev,
          withdrawals: response.data || { total_amount: 0, total_count: 0, chart_data: [] }
        } : null)
      } else if (chartType === 'users') {
        const response = await api.get(`/api/v1/admin/statistics/user-progress?${params.toString()}`)
        setUserProgressData(response.data || [])
      }
    } catch (error) {
      console.error(`Erreur lors du chargement des données ${chartType}:`, error)
    } finally {
      setLoadingCharts(prev => ({ ...prev, [chartType]: false }))
    }
  }

  const handlePeriodChange = (period: PeriodType) => {
    setProgressPeriod(period)
    if (period === 'custom') {
      // Ne pas charger automatiquement, attendre que l'utilisateur sélectionne les dates
      return
    }
    fetchStatistics(period)
  }

  const handleCustomDateApply = () => {
    if (customStartDate && customEndDate) {
      fetchStatistics('custom')
    }
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

  // Préparer les données pour le graphique des rapports par type
  const reportsByTypeData = stats ? [
    { name: t('admin.dashboard.statistics.categories'), value: stats.reports.by_type.category },
    { name: t('admin.dashboard.statistics.contests'), value: stats.reports.by_type.contest },
    { name: t('admin.users.user'), value: stats.reports.by_type.user },
    { name: t('admin.contestants.title'), value: stats.reports.by_type.contestant },
    { name: t('admin.dashboard.comments'), value: stats.reports.by_type.comment },
    { name: 'Média', value: stats.reports.by_type.media }
  ].filter(item => item.value > 0) : []

  const periods: { value: PeriodType; label: string }[] = [
    { value: 'today', label: t('admin.dashboard.periods.today') || 'Aujourd\'hui' },
    { value: 'yesterday', label: t('admin.dashboard.periods.yesterday') || 'Hier' },
    { value: 'week', label: t('admin.dashboard.periods.week') || 'Semaine' },
    { value: 'month', label: t('admin.dashboard.periods.month') || 'Mois' },
    { value: 'year', label: t('admin.dashboard.periods.year') || 'Année' },
    { value: 'custom', label: t('admin.dashboard.statistics.custom') || 'Personnalisé' }
  ]

  return (
    <div className="flex flex-col space-y-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-myhigh5-primary dark:text-myhigh5-blue-400">{t('admin.title') || 'Tableau de bord Admin'}</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-3 text-lg">
          {t('common.welcome')} <span className="font-semibold text-myhigh5-primary dark:text-myhigh5-blue-400">{user?.full_name || user?.username}</span>! {t('admin.subtitle') || 'Statistiques de la plateforme'}
        </p>
      </div>

      {/* Sélecteur de période */}
      <Card className="border-gray-200 dark:border-gray-700">
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              <span className="font-medium text-gray-700 dark:text-gray-300">{t('admin.dashboard.statistics.period') || 'Période:'}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {periods.map((p) => (
                <Button
                  key={p.value}
                  variant={progressPeriod === p.value ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handlePeriodChange(p.value)}
                  className={cn(
                    'h-9 px-4 text-sm',
                    progressPeriod === p.value
                      ? 'bg-blue-600 hover:bg-blue-700 text-white'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                  )}
                >
                  {p.label}
                </Button>
              ))}
            </div>
            {progressPeriod === 'custom' && (
              <div className="flex items-center gap-2 ml-auto">
                <Input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  className="w-40"
                />
                <span className="text-gray-600 dark:text-gray-400">à</span>
                <Input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  className="w-40"
                />
                <Button
                  onClick={handleCustomDateApply}
                  disabled={!customStartDate || !customEndDate}
                  size="sm"
                >
                  {t('admin.dashboard.statistics.apply') || 'Appliquer'}
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {loadingStats ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
        </div>
      ) : stats && (
        <>
          {/* Statistiques principales */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <StatsCard
              icon={ArrowDownCircle}
              title={t('admin.dashboard.statistics.total_deposits')}
              value={`$${stats.deposits.total_amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              subtitle={`${stats.deposits.total_count} ${t('admin.dashboard.statistics.deposits_count')}`}
              iconBgColor="bg-green-100 dark:bg-green-900/50"
              iconColor="text-green-600 dark:text-green-400"
          />
          <StatsCard
              icon={ArrowUpCircle}
              title={t('admin.dashboard.statistics.total_withdrawals')}
              value={`$${stats.withdrawals.total_amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              subtitle={`${stats.withdrawals.total_count} ${t('admin.dashboard.statistics.withdrawals_count')}`}
              iconBgColor="bg-red-100 dark:bg-red-900/50"
              iconColor="text-red-600 dark:text-red-400"
          />
          <StatsCard
            icon={Users}
              title={t('admin.dashboard.statistics.verified_users')}
              value={`${stats.verified_users} / ${stats.total_users}`}
              subtitle={t('admin.dashboard.statistics.kyc_verified')}
              iconBgColor="bg-blue-100 dark:bg-blue-900/50"
              iconColor="text-blue-600 dark:text-blue-400"
          />
          <StatsCard
            icon={Flag}
              title={t('admin.dashboard.statistics.reports')}
            value={stats.reports.total}
              subtitle={t('admin.dashboard.statistics.reports_count')}
              iconBgColor="bg-orange-100 dark:bg-orange-900/50"
              iconColor="text-orange-600 dark:text-orange-400"
            />
            <StatsCard
              icon={Tag}
              title={t('admin.dashboard.statistics.categories')}
              value={stats.categories.total}
              subtitle={t('admin.dashboard.statistics.categories_total')}
              iconBgColor="bg-purple-100 dark:bg-purple-900/50"
              iconColor="text-purple-600 dark:text-purple-400"
            />
          </div>

          {/* Graphique des dépôts */}
          <Card className="border-gray-200 dark:border-gray-700">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-10 h-10 rounded-lg bg-green-100 dark:bg-green-900/50 flex items-center justify-center">
                    <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
                  </div>
                  <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white">
                    {t('admin.dashboard.statistics.deposits_chart')}
                  </CardTitle>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fetchChartData('deposits')}
                  disabled={loadingCharts.deposits}
                >
                  {loadingCharts.deposits ? (t('admin.dashboard.statistics.loading') || 'Chargement...') : (t('admin.dashboard.statistics.refresh') || 'Actualiser')}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {loadingCharts.deposits ? (
                <div className="flex justify-center items-center h-[300px]">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-600"></div>
                </div>
              ) : stats.deposits.chart_data && stats.deposits.chart_data.length > 0 ? (
                <div className="overflow-x-auto">
                <div className="min-w-[500px]">
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={stats.deposits.chart_data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorDeposits" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis 
                      dataKey="date" 
                      className="text-xs text-gray-600 dark:text-gray-400"
                      tick={{ fill: 'currentColor' }}
                    />
                    <YAxis 
                      className="text-xs text-gray-600 dark:text-gray-400"
                      tick={{ fill: 'currentColor' }}
                    />
                    <Tooltip 
                      contentStyle={{
                        backgroundColor: 'var(--background)',
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        color: 'var(--foreground)'
                      }}
                      formatter={(value: any, name: string) => {
                        const amountLabel = t('admin.dashboard.statistics.amount_eur')
                        if (name === amountLabel || name === 'amount' || name?.includes('Montant') || name?.includes('Amount')) {
                          return [`$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, amountLabel]
                        }
                        return [value, name]
                      }}
                    />
                    <Legend />
                    <Area 
                      type="monotone" 
                      dataKey="amount" 
                      stroke="#10b981" 
                      fillOpacity={1} 
                      fill="url(#colorDeposits)"
                      name={t('admin.dashboard.statistics.amount_eur')}
                      strokeWidth={2}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="count" 
                      stroke="#3b82f6" 
                      strokeWidth={2}
                      dot={{ fill: '#3b82f6', r: 4 }}
                      name={t('admin.dashboard.statistics.count')}
                    />
                  </AreaChart>
                </ResponsiveContainer>
                </div>
                </div>
              ) : (
                <div className="flex justify-center items-center h-[300px] text-gray-500 dark:text-gray-400">
                  {t('admin.dashboard.statistics.no_data_available') || 'Aucune donnée disponible'}
              </div>
      )}
            </CardContent>
          </Card>

          {/* Graphique des retraits */}
          <Card className="border-gray-200 dark:border-gray-700">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-10 h-10 rounded-lg bg-red-100 dark:bg-red-900/50 flex items-center justify-center">
                    <TrendingUp className="w-5 h-5 text-red-600 dark:text-red-400" />
                  </div>
                  <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white">
                    {t('admin.dashboard.statistics.withdrawals_chart')}
                  </CardTitle>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fetchChartData('withdrawals')}
                  disabled={loadingCharts.withdrawals}
                >
                  {loadingCharts.withdrawals ? (t('admin.dashboard.statistics.loading') || 'Chargement...') : (t('admin.dashboard.statistics.refresh') || 'Actualiser')}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {loadingCharts.withdrawals ? (
                <div className="flex justify-center items-center h-[300px]">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-600"></div>
                </div>
              ) : stats.withdrawals.chart_data && stats.withdrawals.chart_data.length > 0 ? (
                <div className="overflow-x-auto">
                <div className="min-w-[500px]">
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={stats.withdrawals.chart_data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorWithdrawals" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis 
                      dataKey="date" 
                      className="text-xs text-gray-600 dark:text-gray-400"
                      tick={{ fill: 'currentColor' }}
                    />
                    <YAxis 
                      className="text-xs text-gray-600 dark:text-gray-400"
                      tick={{ fill: 'currentColor' }}
                    />
                    <Tooltip 
                      contentStyle={{
                        backgroundColor: 'var(--background)',
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        color: 'var(--foreground)'
                      }}
                      formatter={(value: any, name: string) => {
                        const amountLabel = t('admin.dashboard.statistics.amount_eur')
                        if (name === amountLabel || name === 'amount' || name?.includes('Montant') || name?.includes('Amount')) {
                          return [`$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, amountLabel]
                        }
                        return [value, name]
                      }}
                    />
                    <Legend />
                    <Area 
                      type="monotone" 
                      dataKey="amount" 
                      stroke="#ef4444" 
                      fillOpacity={1} 
                      fill="url(#colorWithdrawals)"
                      name={t('admin.dashboard.statistics.amount_eur')}
                      strokeWidth={2}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="count" 
                      stroke="#f59e0b" 
                      strokeWidth={2}
                      dot={{ fill: '#f59e0b', r: 4 }}
                      name={t('admin.dashboard.statistics.count')}
                    />
                  </AreaChart>
                </ResponsiveContainer>
                </div>
                </div>
              ) : (
                <div className="flex justify-center items-center h-[300px] text-gray-500 dark:text-gray-400">
                  {t('admin.dashboard.statistics.no_data_available') || 'Aucune donnée disponible'}
        </div>
      )}
            </CardContent>
          </Card>

          {/* Graphique des utilisateurs */}
          <Card className="border-gray-200 dark:border-gray-700">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center">
                    <Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white">
                    {t('admin.dashboard.user_progress') || 'Progression des utilisateurs'}
                  </CardTitle>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fetchChartData('users')}
                  disabled={loadingCharts.users}
                >
                  {loadingCharts.users ? (t('admin.dashboard.statistics.loading') || 'Chargement...') : (t('admin.dashboard.statistics.refresh') || 'Actualiser')}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {loadingCharts.users ? (
                <div className="flex justify-center items-center h-[300px]">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                </div>
              ) : userProgressData && userProgressData.length > 0 ? (
      <div>
                  <div className="overflow-x-auto">
                  <div className="min-w-[500px]">
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={userProgressData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                        </linearGradient>
                        <linearGradient id="colorActive" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                      <XAxis 
                        dataKey="date" 
                        className="text-xs text-gray-600 dark:text-gray-400"
                        tick={{ fill: 'currentColor' }}
                      />
                      <YAxis 
                        className="text-xs text-gray-600 dark:text-gray-400"
                        tick={{ fill: 'currentColor' }}
                      />
                      <Tooltip 
                        contentStyle={{
                          backgroundColor: 'var(--background)',
                          border: '1px solid var(--border)',
                          borderRadius: '8px',
                          color: 'var(--foreground)'
                        }}
                      />
                      <Legend />
                      <Area 
                        type="monotone" 
                        dataKey="total" 
                        stroke="#3b82f6" 
                        fillOpacity={1} 
                        fill="url(#colorTotal)"
                        name={t('admin.dashboard.chart_labels.total_users')}
                        strokeWidth={2}
                      />
                      <Area 
                        type="monotone" 
                        dataKey="active" 
                        stroke="#10b981" 
                        fillOpacity={1} 
                        fill="url(#colorActive)"
                        name={t('admin.dashboard.chart_labels.active_users')}
                        strokeWidth={2}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="new" 
                        stroke="#f59e0b" 
                        strokeWidth={2}
                        dot={{ fill: '#f59e0b', r: 4 }}
                        name={t('admin.dashboard.chart_labels.new_users')}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                  </div>
                  </div>
                </div>
              ) : (
                <div className="flex justify-center items-center h-[300px] text-gray-500 dark:text-gray-400">
                  {t('admin.dashboard.statistics.no_data_available') || 'Aucune donnée disponible'}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Graphique des catégories */}
          {stats.categories.chart_data && stats.categories.chart_data.length > 0 && (
            <Card className="border-gray-200 dark:border-gray-700">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-900/50 flex items-center justify-center">
                    <BarChart3 className="w-5 h-5 text-purple-600 dark:text-purple-400" />
        </div>
                  <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white">
                    {t('admin.dashboard.statistics.categories_chart')}
                  </CardTitle>
      </div>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                <div className="min-w-[500px]">
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={stats.categories.chart_data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis 
                      dataKey="name" 
                      className="text-xs text-gray-600 dark:text-gray-400"
                      tick={{ fill: 'currentColor' }}
                      angle={-45}
                      textAnchor="end"
                      height={80}
                    />
                    <YAxis 
                      className="text-xs text-gray-600 dark:text-gray-400"
                      tick={{ fill: 'currentColor' }}
                    />
                    <Tooltip 
                      contentStyle={{
                        backgroundColor: 'var(--background)',
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        color: 'var(--foreground)'
                      }}
                    />
                    <Legend />
                    <Bar dataKey="contests" fill="#3b82f6" name={t('admin.dashboard.statistics.contests')} />
                  </BarChart>
                </ResponsiveContainer>
                </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Graphique des rapports par type */}
          {reportsByTypeData.length > 0 && (
            <Card className="border-gray-200 dark:border-gray-700">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-10 h-10 rounded-lg bg-orange-100 dark:bg-orange-900/50 flex items-center justify-center">
                    <Flag className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                  </div>
                  <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white">
                    {t('admin.dashboard.statistics.reports_by_type')}
                  </CardTitle>
      </div>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={reportsByTypeData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {reportsByTypeData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{
                        backgroundColor: 'var(--background)',
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        color: 'var(--foreground)'
                      }}
                    />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
