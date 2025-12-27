'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { 
  DollarSign, 
  TrendingUp, 
  Calendar,
  ArrowDownRight,
  Clock,
  CheckCircle,
  XCircle,
  Filter,
  Download,
  Euro,
  Users,
  CreditCard,
  ShoppingBag,
  Trophy,
  BadgeCheck,
  Sparkles,
  PiggyBank,
  Video
} from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Commission {
  id: string
  amount: number
  baseAmount?: number
  type: 'direct' | 'indirect'
  level: number
  status: 'pending' | 'paid' | 'cancelled'
  commissionType: string
  productTypeCode?: string
  productTypeName?: string
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
  const { t, language } = useLanguage()
  
  // Mapping des langues vers les locales
  const localeMap: Record<string, string> = {
    fr: 'fr-FR',
    en: 'en-US',
    es: 'es-ES',
    de: 'de-DE'
  }
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
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [sortBy, setSortBy] = useState<'date' | 'amount' | 'type'>('date')
  const [pageLoading, setPageLoading] = useState(true)
  const [listLoading, setListLoading] = useState(false)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    } else if (!isLoading && isAuthenticated) {
      loadCommissionsData()
    }
  }, [isLoading, isAuthenticated, router])

  // Recharger quand les filtres changent
  useEffect(() => {
    if (isAuthenticated && !pageLoading) {
      loadCommissionsData(true)
    }
  }, [sortBy, typeFilter, filter])

  const loadCommissionsData = async (isFilterChange = false) => {
    if (isFilterChange) {
      setListLoading(true)
    }
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
      
      // Construire les paramètres de requête
      const params = new URLSearchParams()
      params.append('sort_by', sortBy)
      if (typeFilter !== 'all') {
        params.append('product_type', typeFilter)
      }
      if (filter !== 'all') {
        params.append('status', filter)
      }
      
      // Charger la liste des commissions
      const commissionsResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/commissions?${params.toString()}`, {
        headers
      })
      
      if (commissionsResponse.ok) {
        const commissionsData = await commissionsResponse.json()
        setCommissions(commissionsData.map((c: any) => ({
          id: c.id?.toString() || '',
          amount: c.amount || 0,
          baseAmount: c.base_amount,
          type: c.level === 1 ? 'direct' : 'indirect',
          level: c.level || 1,
          status: c.status || 'pending',
          commissionType: c.commission_type || 'SHOP_PURCHASE',
          productTypeCode: c.product_type_code,
          productTypeName: c.product_type_name,
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
      setListLoading(false)
    }
  }

  // Configuration des types de commission
  const getCommissionTypeConfig = (type: string, productCode?: string) => {
    // Priorité au code produit s'il existe
    const code = productCode || type
    
    const configs: Record<string, { icon: any; label: string; color: string; bgColor: string }> = {
      // Founding Members = KYC (même produit)
      'founding_membership': {
        icon: BadgeCheck,
        label: t('dashboard.commissions.types.KYC_PAYMENT'),
        color: 'text-indigo-600 dark:text-indigo-400',
        bgColor: 'bg-indigo-100 dark:bg-indigo-900/30'
      },
      'FOUNDING_MEMBERSHIP_FEE': {
        icon: BadgeCheck,
        label: t('dashboard.commissions.types.KYC_PAYMENT'),
        color: 'text-indigo-600 dark:text-indigo-400',
        bgColor: 'bg-indigo-100 dark:bg-indigo-900/30'
      },
      'annual_membership': {
        icon: CreditCard,
        label: t('dashboard.commissions.types.ANNUAL_MEMBERSHIP_FEE'),
        color: 'text-purple-600 dark:text-purple-400',
        bgColor: 'bg-purple-100 dark:bg-purple-900/30'
      },
      'ANNUAL_MEMBERSHIP_FEE': {
        icon: CreditCard,
        label: t('dashboard.commissions.types.ANNUAL_MEMBERSHIP_FEE'),
        color: 'text-purple-600 dark:text-purple-400',
        bgColor: 'bg-purple-100 dark:bg-purple-900/30'
      },
      'MONTHLY_REVENUE_POOL': {
        icon: PiggyBank,
        label: t('dashboard.commissions.types.MONTHLY_REVENUE_POOL'),
        color: 'text-cyan-600 dark:text-cyan-400',
        bgColor: 'bg-cyan-100 dark:bg-cyan-900/30'
      },
      'ANNUAL_PROFIT_POOL': {
        icon: Sparkles,
        label: t('dashboard.commissions.types.ANNUAL_PROFIT_POOL'),
        color: 'text-pink-600 dark:text-pink-400',
        bgColor: 'bg-pink-100 dark:bg-pink-900/30'
      },
      // Standard commissions
      'kyc_verification': {
        icon: BadgeCheck,
        label: t('dashboard.commissions.types.KYC_PAYMENT'),
        color: 'text-indigo-600 dark:text-indigo-400',
        bgColor: 'bg-indigo-100 dark:bg-indigo-900/30'
      },
      'KYC_PAYMENT': {
        icon: BadgeCheck,
        label: t('dashboard.commissions.types.KYC_PAYMENT'),
        color: 'text-indigo-600 dark:text-indigo-400',
        bgColor: 'bg-indigo-100 dark:bg-indigo-900/30'
      },
      'efm_membership': {
        icon: Sparkles,
        label: t('dashboard.commissions.types.EFM_MEMBERSHIP'),
        color: 'text-violet-600 dark:text-violet-400',
        bgColor: 'bg-violet-100 dark:bg-violet-900/30'
      },
      'EFM_MEMBERSHIP': {
        icon: Sparkles,
        label: t('dashboard.commissions.types.EFM_MEMBERSHIP'),
        color: 'text-violet-600 dark:text-violet-400',
        bgColor: 'bg-violet-100 dark:bg-violet-900/30'
      },
      'club_membership': {
        icon: Users,
        label: t('dashboard.commissions.types.CLUB_MEMBERSHIP'),
        color: 'text-teal-600 dark:text-teal-400',
        bgColor: 'bg-teal-100 dark:bg-teal-900/30'
      },
      'CLUB_MEMBERSHIP': {
        icon: Users,
        label: t('dashboard.commissions.types.CLUB_MEMBERSHIP'),
        color: 'text-teal-600 dark:text-teal-400',
        bgColor: 'bg-teal-100 dark:bg-teal-900/30'
      },
      'contest_participation': {
        icon: Trophy,
        label: t('dashboard.commissions.types.CONTEST_PARTICIPATION'),
        color: 'text-orange-600 dark:text-orange-400',
        bgColor: 'bg-orange-100 dark:bg-orange-900/30'
      },
      'CONTEST_PARTICIPATION': {
        icon: Trophy,
        label: t('dashboard.commissions.types.CONTEST_PARTICIPATION'),
        color: 'text-orange-600 dark:text-orange-400',
        bgColor: 'bg-orange-100 dark:bg-orange-900/30'
      },
      'shop_purchase': {
        icon: ShoppingBag,
        label: t('dashboard.commissions.types.SHOP_PURCHASE'),
        color: 'text-rose-600 dark:text-rose-400',
        bgColor: 'bg-rose-100 dark:bg-rose-900/30'
      },
      'SHOP_PURCHASE': {
        icon: ShoppingBag,
        label: t('dashboard.commissions.types.SHOP_PURCHASE'),
        color: 'text-rose-600 dark:text-rose-400',
        bgColor: 'bg-rose-100 dark:bg-rose-900/30'
      },
      'AD_REVENUE': {
        icon: Video,
        label: t('dashboard.commissions.types.AD_REVENUE'),
        color: 'text-sky-600 dark:text-sky-400',
        bgColor: 'bg-sky-100 dark:bg-sky-900/30'
      },
      'ad_revenue': {
        icon: Video,
        label: t('dashboard.commissions.types.AD_REVENUE'),
        color: 'text-sky-600 dark:text-sky-400',
        bgColor: 'bg-sky-100 dark:bg-sky-900/30'
      }
    }
    
    return configs[code] || {
      icon: DollarSign,
      label: productCode || type || 'Commission',
      color: 'text-gray-600 dark:text-gray-400',
      bgColor: 'bg-gray-100 dark:bg-gray-900/30'
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'paid':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
            <CheckCircle className="w-3 h-3" />
            {t('dashboard.commissions.paid') || 'Payé'}
          </span>
        )
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400">
            <Clock className="w-3 h-3" />
            {t('dashboard.commissions.pending') || 'En attente'}
          </span>
        )
      case 'cancelled':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400">
            <XCircle className="w-3 h-3" />
            {t('dashboard.commissions.cancelled') || 'Annulé'}
          </span>
        )
      default:
        return null
    }
  }

  // Types de commission disponibles pour le filtre
  const availableTypes = [
    { code: 'all', label: t('dashboard.commissions.filter_all') },
    { code: 'kyc_verification', label: t('dashboard.commissions.types.KYC_PAYMENT') },
    { code: 'annual_membership', label: t('dashboard.commissions.types.ANNUAL_MEMBERSHIP_FEE') },
    { code: 'mfm_membership', label: t('dashboard.commissions.types.MFM_MEMBERSHIP') },
    { code: 'club_membership', label: t('dashboard.commissions.types.CLUB_MEMBERSHIP') },
    { code: 'contest_participation', label: t('dashboard.commissions.types.CONTEST_PARTICIPATION') },
    { code: 'shop_purchase', label: t('dashboard.commissions.types.SHOP_PURCHASE') },
    { code: 'ad_revenue', label: t('dashboard.commissions.types.AD_REVENUE') }
  ]

  // Les commissions sont déjà triées et filtrées par le backend
  const filteredCommissions = commissions

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
            {t('dashboard.commissions.title') || 'Mes Commissions'}
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {t('dashboard.commissions.subtitle') || 'Suivez vos gains et revenus d\'affiliation'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button 
            variant="outline"
            size="sm"
            className="rounded-xl"
          >
            <Download className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">{t('dashboard.commissions.export') || 'Exporter'}</span>
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
            {stats.totalEarned.toLocaleString('fr-FR', { style: 'currency', currency: 'USD' })}
          </p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {t('dashboard.commissions.total_earned') || 'Total gagné'}
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
            {stats.pendingAmount.toLocaleString('fr-FR', { style: 'currency', currency: 'USD' })}
          </p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {t('dashboard.commissions.pending_amount') || 'En attente'}
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
            {stats.thisMonth.toLocaleString('fr-FR', { style: 'currency', currency: 'USD' })}
          </p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {t('dashboard.commissions.this_month') || 'Ce mois'}
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
            {t('dashboard.commissions.growth') || 'Croissance'}
          </p>
        </div>
      </div>

    

      {/* Commissions List */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 overflow-hidden">
        <div className="p-4 sm:p-6 border-b border-gray-100 dark:border-gray-700">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-gray-500" />
              {t('dashboard.commissions.history') || 'Historique des commissions'}
            </h2>
            
            {/* Filters */}
            <div className="flex flex-wrap items-center gap-3">
              {/* Tri */}
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'date' | 'amount' | 'type')}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-100 dark:bg-gray-700 border-0 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-emerald-500"
              >
                <option value="date">{t('dashboard.commissions.sort_by_date') || 'Par date'}</option>
                <option value="amount">{t('dashboard.commissions.sort_by_amount') || 'Par montant'}</option>
                <option value="type">{t('dashboard.commissions.sort_by_type') || 'Par type'}</option>
              </select>
              
              {/* Filtre par type */}
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-100 dark:bg-gray-700 border-0 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-emerald-500"
              >
                {availableTypes.map((type) => (
                  <option key={type.code} value={type.code}>
                    {type.label}
                  </option>
                ))}
              </select>
              
              {/* Filtre par statut */}
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
                      {status === 'all' && (t('dashboard.commissions.all') || 'Tout')}
                      {status === 'pending' && (t('dashboard.commissions.pending') || 'En attente')}
                      {status === 'paid' && (t('dashboard.commissions.paid') || 'Payé')}
                      {status === 'cancelled' && (t('dashboard.commissions.cancelled') || 'Annulé')}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div className={`divide-y divide-gray-100 dark:divide-gray-700 ${listLoading ? 'opacity-50 pointer-events-none' : ''}`}>
          {listLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/50 dark:bg-gray-800/50 z-10">
              <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
          {filteredCommissions.map((commission) => {
            const typeConfig = getCommissionTypeConfig(commission.commissionType, commission.productTypeCode)
            const TypeIcon = typeConfig.icon
            
            return (
              <div 
                key={commission.id} 
                className="p-4 sm:p-5 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <div className="flex items-start sm:items-center gap-4">
                  {/* Icon du type de commission */}
                  <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${typeConfig.bgColor}`}>
                    <TypeIcon className={`w-5 h-5 sm:w-6 sm:h-6 ${typeConfig.color}`} />
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      {/* Type de commission */}
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${typeConfig.bgColor} ${typeConfig.color}`}>
                        {typeConfig.label}
                      </span>
                      {/* Niveau */}
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        commission.type === 'direct'
                          ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                          : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400'
                      }`}>
                        {commission.type === 'direct' 
                          ? t('dashboard.commissions.direct') || 'Direct'
                          : `N${commission.level}`
                        }
                      </span>
                      {getStatusBadge(commission.status)}
                    </div>
                    
                    {/* Source user */}
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-5 h-5 rounded-full bg-gray-200 dark:bg-gray-600 flex items-center justify-center text-xs font-medium text-gray-600 dark:text-gray-300 overflow-hidden">
                        {commission.sourceUser.avatar ? (
                          <img src={commission.sourceUser.avatar} alt="" className="w-full h-full object-cover" />
                        ) : (
                          commission.sourceUser.name.charAt(0)
                        )}
                      </div>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {commission.sourceUser.name}
                      </p>
                    </div>
                    
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      {new Date(commission.createdAt).toLocaleDateString(localeMap[language] || 'en-US', {
                        day: 'numeric',
                        month: 'long',
                        year: 'numeric'
                      })}
                      {commission.baseAmount && (
                        <span className="ml-2">
                          • Base: {commission.baseAmount.toLocaleString(localeMap[language] || 'en-US', { style: 'currency', currency: 'USD' })}
                        </span>
                      )}
                    </p>
                  </div>
                  
                  <div className="text-right flex-shrink-0">
                    <p className={`text-lg sm:text-xl font-bold ${
                      commission.status === 'cancelled' 
                        ? 'text-gray-400 line-through' 
                        : 'text-emerald-600 dark:text-emerald-400'
                    }`}>
                      +{commission.amount.toLocaleString('fr-FR', { style: 'currency', currency: 'USD' })}
                    </p>
                    <p className={`text-xs ${commission.type === 'direct' ? 'text-emerald-600 dark:text-emerald-400' : 'text-blue-600 dark:text-blue-400'}`}>
                      {commission.type === 'direct' ? '20%' : '2%'}
                    </p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        
        {filteredCommissions.length === 0 && (
          <div className="p-12 text-center">
            <div className="w-16 h-16 mx-auto rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
              <DollarSign className="w-8 h-8 text-gray-400" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              {t('dashboard.commissions.no_commissions') || 'Aucune commission'}
            </h3>
            <p className="text-gray-500 dark:text-gray-400 mb-4">
              {t('dashboard.commissions.no_commissions_description') || 'Parrainez des utilisateurs pour commencer à gagner des commissions'}
            </p>
            <Button 
              onClick={() => router.push('/dashboard/affiliates')}
              className="rounded-xl bg-myhigh5-primary hover:bg-myhigh5-primary/90"
            >
              <Users className="w-4 h-4 mr-2" />
              {t('dashboard.commissions.go_to_affiliates') || 'Voir mes affiliés'}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
