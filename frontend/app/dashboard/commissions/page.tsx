'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { 
  DollarSign, 
  TrendingUp, 
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  CheckCircle,
  XCircle,
  Filter,
  Download,
  Euro,
  Users
} from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Commission {
  id: string
  amount: number
  type: 'direct' | 'indirect'
  level: number
  status: 'pending' | 'paid' | 'cancelled'
  sourceUser: {
    name: string
    avatar?: string
  }
  description: string
  createdAt: string
  paidAt?: string
}

interface CommissionStats {
  totalEarned: number
  pendingAmount: number
  paidAmount: number
  thisMonth: number
  lastMonth: number
  growthRate: number
}

export default function CommissionsPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const { user, isAuthenticated, isLoading } = useAuth()
  
  const [commissions, setCommissions] = useState<Commission[]>([])
  const [stats, setStats] = useState<CommissionStats>({
    totalEarned: 0,
    pendingAmount: 0,
    paidAmount: 0,
    thisMonth: 0,
    lastMonth: 0,
    growthRate: 0
  })
  const [filter, setFilter] = useState<'all' | 'pending' | 'paid' | 'cancelled'>('all')
  const [pageLoading, setPageLoading] = useState(true)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    } else if (!isLoading && isAuthenticated) {
      loadCommissionsData()
    }
  }, [isLoading, isAuthenticated, router])

  const loadCommissionsData = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
      
      // Charger les statistiques de commission
      const statsResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/commissions/stats`, {
        headers
      })
      
      if (statsResponse.ok) {
        const statsData = await statsResponse.json()
        setStats({
          totalEarned: statsData.total_earned || 0,
          pendingAmount: statsData.pending_amount || 0,
          paidAmount: statsData.paid_amount || 0,
          thisMonth: statsData.this_month || 0,
          lastMonth: statsData.last_month || 0,
          growthRate: statsData.growth_rate || 0
        })
      }
      
      // Charger la liste des commissions
      const commissionsResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/commissions`, {
        headers
      })
      
      if (commissionsResponse.ok) {
        const commissionsData = await commissionsResponse.json()
        setCommissions(commissionsData.map((c: any) => ({
          id: c.id?.toString() || '',
          amount: c.amount || 0,
          type: c.level === 1 ? 'direct' : 'indirect',
          level: c.level || 1,
          status: c.status || 'pending',
          sourceUser: {
            name: c.source_user_name || 'Utilisateur',
            avatar: c.source_user_avatar
          },
          description: c.description || '',
          createdAt: c.created_at || new Date().toISOString(),
          paidAt: c.paid_at
        })))
      }
    } catch (error) {
      console.error('Error loading commissions data:', error)
    } finally {
      setPageLoading(false)
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'paid':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
            <CheckCircle className="w-3 h-3" />
            {t('commissions.paid') || 'Payé'}
          </span>
        )
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400">
            <Clock className="w-3 h-3" />
            {t('commissions.pending') || 'En attente'}
          </span>
        )
      case 'cancelled':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400">
            <XCircle className="w-3 h-3" />
            {t('commissions.cancelled') || 'Annulé'}
          </span>
        )
      default:
        return null
    }
  }

  const filteredCommissions = commissions.filter(c => {
    if (filter === 'all') return true
    return c.status === filter
  })

  if (isLoading || pageLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 bg-gray-200 dark:bg-gray-700 rounded-2xl" />
          ))}
        </div>
        <div className="h-96 bg-gray-200 dark:bg-gray-700 rounded-2xl" />
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500 flex items-center justify-center shadow-lg shadow-emerald-500/25">
              <DollarSign className="w-5 h-5 text-white" />
            </div>
            {t('commissions.title') || 'Mes Commissions'}
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {t('commissions.subtitle') || 'Suivez vos gains et revenus d\'affiliation'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button 
            variant="outline"
            size="sm"
            className="rounded-xl"
          >
            <Download className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">{t('commissions.export') || 'Exporter'}</span>
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* Total Earned */}
        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl p-4 sm:p-5 border border-gray-100 dark:border-gray-700 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
              <Euro className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            </div>
          </div>
          <p className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
            {stats.totalEarned.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}
          </p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {t('commissions.total_earned') || 'Total gagné'}
          </p>
        </div>

        {/* Pending */}
        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl p-4 sm:p-5 border border-gray-100 dark:border-gray-700 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
              <Clock className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
          </div>
          <p className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
            {stats.pendingAmount.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}
          </p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {t('commissions.pending_amount') || 'En attente'}
          </p>
        </div>

        {/* This Month */}
        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl p-4 sm:p-5 border border-gray-100 dark:border-gray-700 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
              <Calendar className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
          </div>
          <p className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
            {stats.thisMonth.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}
          </p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {t('commissions.this_month') || 'Ce mois'}
          </p>
        </div>

        {/* Growth */}
        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl p-4 sm:p-5 border border-gray-100 dark:border-gray-700 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
              stats.growthRate >= 0 
                ? 'bg-green-100 dark:bg-green-900/30' 
                : 'bg-red-100 dark:bg-red-900/30'
            }`}>
              {stats.growthRate >= 0 ? (
                <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
              ) : (
                <ArrowDownRight className="w-5 h-5 text-red-600 dark:text-red-400" />
              )}
            </div>
          </div>
          <p className={`text-xl sm:text-2xl font-bold ${
            stats.growthRate >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
          }`}>
            {stats.growthRate >= 0 ? '+' : ''}{stats.growthRate}%
          </p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {t('commissions.growth') || 'Croissance'}
          </p>
        </div>
      </div>

      {/* Commission Tiers Info */}
      <div className="bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20 rounded-2xl p-5 border border-emerald-200 dark:border-emerald-700/50">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-emerald-500 flex items-center justify-center shadow-lg shadow-emerald-500/25">
              <Users className="w-7 h-7 text-white" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-white">
                {t('commissions.affiliate_program') || 'Programme d\'affiliation'}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {t('commissions.ten_levels_description') || 'Gagnez jusqu\'à 38% sur 10 niveaux de parrainage'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">20%</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('commissions.level_1') || 'Niveau 1'}</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">2%</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('commissions.levels_2_10') || 'Niveaux 2-10'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Commissions List */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 overflow-hidden">
        <div className="p-4 sm:p-6 border-b border-gray-100 dark:border-gray-700">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-gray-500" />
              {t('commissions.history') || 'Historique des commissions'}
            </h2>
            
            {/* Filters */}
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-gray-400" />
              <div className="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
                {(['all', 'pending', 'paid', 'cancelled'] as const).map((status) => (
                  <button
                    key={status}
                    onClick={() => setFilter(status)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                      filter === status
                        ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                        : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                    }`}
                  >
                    {status === 'all' && (t('commissions.all') || 'Tout')}
                    {status === 'pending' && (t('commissions.pending') || 'En attente')}
                    {status === 'paid' && (t('commissions.paid') || 'Payé')}
                    {status === 'cancelled' && (t('commissions.cancelled') || 'Annulé')}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
        
        <div className="divide-y divide-gray-100 dark:divide-gray-700">
          {filteredCommissions.map((commission) => (
            <div 
              key={commission.id} 
              className="p-4 sm:p-5 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <div className="flex items-start sm:items-center gap-4">
                <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center text-white font-semibold shadow-lg flex-shrink-0 ${
                  commission.type === 'direct' 
                    ? 'bg-emerald-500 shadow-emerald-500/25' 
                    : 'bg-blue-500 shadow-blue-500/25'
                }`}>
                  {commission.sourceUser.avatar ? (
                    <img src={commission.sourceUser.avatar} alt="" className="w-full h-full rounded-full object-cover" />
                  ) : (
                    commission.sourceUser.name.charAt(0)
                  )}
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <p className="font-medium text-gray-900 dark:text-white">
                      {commission.sourceUser.name}
                    </p>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      commission.type === 'direct'
                        ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                        : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400'
                    }`}>
                      {t('commissions.level') || 'Niveau'} {commission.level}
                    </span>
                    {getStatusBadge(commission.status)}
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {commission.description || (commission.type === 'direct' 
                      ? t('commissions.direct_referral') || 'Parrainage direct'
                      : t('commissions.indirect_referral') || 'Parrainage indirect'
                    )}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    {new Date(commission.createdAt).toLocaleDateString('fr-FR', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric'
                    })}
                  </p>
                </div>
                
                <div className="text-right flex-shrink-0">
                  <p className={`text-lg sm:text-xl font-bold ${
                    commission.status === 'cancelled' 
                      ? 'text-gray-400 line-through' 
                      : 'text-emerald-600 dark:text-emerald-400'
                  }`}>
                    +{commission.amount.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}
                  </p>
                  {commission.type === 'direct' && (
                    <p className="text-xs text-emerald-600 dark:text-emerald-400">20%</p>
                  )}
                  {commission.type === 'indirect' && (
                    <p className="text-xs text-blue-600 dark:text-blue-400">2%</p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
        
        {filteredCommissions.length === 0 && (
          <div className="p-12 text-center">
            <div className="w-16 h-16 mx-auto rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
              <DollarSign className="w-8 h-8 text-gray-400" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              {t('commissions.no_commissions') || 'Aucune commission'}
            </h3>
            <p className="text-gray-500 dark:text-gray-400 mb-4">
              {t('commissions.no_commissions_description') || 'Parrainez des utilisateurs pour commencer à gagner des commissions'}
            </p>
            <Button 
              onClick={() => router.push('/dashboard/affiliates')}
              className="rounded-xl bg-myfav-primary hover:bg-myfav-primary/90"
            >
              <Users className="w-4 h-4 mr-2" />
              {t('commissions.go_to_affiliates') || 'Voir mes affiliés'}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
