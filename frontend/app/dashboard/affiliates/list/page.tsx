'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Users,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  Zap,
  TrendingUp,
  Calendar,
  DollarSign,
  ArrowLeft,
  CheckCircle,
  Clock,
  UserPlus,
  GitBranch
} from 'lucide-react'
import Link from 'next/link'

type KYCStatusType = 'none' | 'pending' | 'in_progress' | 'approved' | 'rejected' | 'expired' | 'requires_review'

interface Affiliate {
  id: string
  name: string
  email: string
  avatar?: string
  joinedAt: string
  level: number
  totalEarnings: number
  status: 'active' | 'inactive'
  referrals: number
  identity_verified?: boolean
  has_paid_kyc?: boolean
  kyc_status?: KYCStatusType
}

interface LevelStats {
  [key: number]: {
    count: number
    commissions: number
  }
}

interface KYCStats {
  none: number
  pending: number
  in_progress: number
  approved: number
  rejected: number
  expired: number
  requires_review: number
}

export default function AffiliatesListPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { addToast } = useToast()

  const [affiliates, setAffiliates] = useState<Affiliate[]>([])
  const [filteredAffiliates, setFilteredAffiliates] = useState<Affiliate[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [levelFilter, setLevelFilter] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [kycStatusFilter, setKycStatusFilter] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [levelStats, setLevelStats] = useState<LevelStats>({})
  const [kycStats, setKycStats] = useState<KYCStats | null>(null)
  const itemsPerPage = 10

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    } else if (!isLoading && isAuthenticated) {
      loadAffiliatesData()
    }
  }, [isLoading, isAuthenticated, router])

  // Recharger les données quand les filtres changent
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      setPageLoading(true)
      loadAffiliatesData()
    }
  }, [levelFilter, statusFilter, kycStatusFilter])

  // Filtrage local pour la recherche (plus rapide)
  useEffect(() => {
    filterAffiliates()
  }, [searchQuery, affiliates])

  const loadAffiliatesData = async () => {
    try {
      const token = localStorage.getItem('access_token')
      if (!token) {
        router.push('/')
        return
      }

      // Build query params
      const params = new URLSearchParams()
      params.append('limit', '10') // Get more to have full list for client-side pagination
      if (levelFilter !== null) params.append('level', levelFilter.toString())
      if (statusFilter) params.append('status', statusFilter)
      if (kycStatusFilter) params.append('kyc_status', kycStatusFilter)
      if (searchQuery) params.append('search', searchQuery)

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/referrals/all?${params.toString()}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (response.ok) {
        const data = await response.json()

        // Transform API data to match Affiliate interface
        const transformedAffiliates: Affiliate[] = data.referrals.map((r: any) => ({
          id: r.id?.toString() || '',
          name: r.full_name || [r.first_name, r.last_name].filter(Boolean).join(' ') || r.username || 'N/A',
          email: r.email || '',
          avatar: r.avatar_url,
          joinedAt: r.created_at || new Date().toISOString(),
          level: r.level || 1,
          totalEarnings: r.commissions_generated || 0,
          status: r.is_active ? 'active' : 'inactive',
          referrals: r.referrals_count || 0,
          identity_verified: r.identity_verified,
          has_paid_kyc: r.has_paid_kyc,
          kyc_status: r.kyc_status as KYCStatusType
        }))

        setAffiliates(transformedAffiliates)
        setFilteredAffiliates(transformedAffiliates)
        setTotalCount(data.total_all_levels || transformedAffiliates.length)
        setLevelStats(data.level_stats || {})
        setKycStats(data.kyc_stats || null)
      } else {
        console.error('Error fetching affiliates:', response.status)
        addToast(t('common.error') || 'Erreur lors du chargement des données', 'error')
      }
    } catch (error) {
      console.error('Error loading affiliates data:', error)
      addToast(t('common.error') || 'Erreur lors du chargement des données', 'error')
    } finally {
      setPageLoading(false)
    }
  }

  const filterAffiliates = () => {
    let filtered = [...affiliates]

    // Filtrage local uniquement pour la recherche (niveau et statut sont gérés côté serveur)
    if (searchQuery) {
      filtered = filtered.filter(a =>
        a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        a.email.toLowerCase().includes(searchQuery.toLowerCase())
      )
    }

    setFilteredAffiliates(filtered)
    setCurrentPage(1)
  }

  const getLevelBadge = (level: number) => {
    const opacity = Math.max(100 - (level - 1) * 10, 20)
    return `bg-myhigh5-primary/${opacity} text-white`
  }

  const getKycStatusBadge = (status: KYCStatusType | undefined) => {
    const statusConfig: Record<string, { label: string; className: string }> = {
      none: {
        label: t('dashboard.affiliates.kyc_none') || 'Non initié',
        className: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
      },
      pending: {
        label: t('dashboard.affiliates.kyc_pending') || 'En attente',
        className: 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400'
      },
      in_progress: {
        label: t('dashboard.affiliates.kyc_in_progress') || 'En cours',
        className: 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
      },
      approved: {
        label: t('dashboard.affiliates.kyc_approved') || 'Vérifié',
        className: 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
      },
      rejected: {
        label: t('dashboard.affiliates.kyc_rejected') || 'Rejeté',
        className: 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
      },
      expired: {
        label: t('dashboard.affiliates.kyc_expired') || 'Expiré',
        className: 'bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400'
      },
      requires_review: {
        label: t('dashboard.affiliates.kyc_requires_review') || 'À revoir',
        className: 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
      }
    }

    const config = statusConfig[status || 'none'] || statusConfig.none
    return config
  }

  const paginatedAffiliates = filteredAffiliates.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  )

  const totalPages = Math.ceil(filteredAffiliates.length / itemsPerPage)

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount)
  }

  if (isLoading || pageLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-20 bg-gray-200 dark:bg-gray-700 rounded-xl" />
          ))}
        </div>
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
        <div className="flex items-center gap-4">
          <Link href="/dashboard/affiliates">
            <Button variant="ghost" size="icon" className="rounded-xl">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-myhigh5-primary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
                <Users className="w-5 h-5 text-white" />
              </div>
              {t('dashboard.affiliates.all_affiliates') || 'Tous les affiliés'}
            </h1>
            <p className="text-gray-500 dark:text-gray-400 mt-1">
              {totalCount} {t('dashboard.affiliates.affiliates_found') || 'affiliés trouvés'} ({Object.keys(levelStats).length} {t('dashboard.affiliates.levels') || 'niveaux'})
            </p>
          </div>
        </div>
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {/* Total */}
        <div className="relative group bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700 cursor-help transition-all hover:shadow-lg hover:border-myhigh5-primary/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-myhigh5-primary/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-myhigh5-primary" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{totalCount}</p>
              <p className="text-xs text-gray-500">{t('dashboard.affiliates.total_affiliates')}</p>
            </div>
          </div>
          {/* Tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-gray-900 dark:bg-gray-700 text-white text-sm rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <p className="font-semibold mb-1">{t('dashboard.affiliates.total_tooltip_title') || 'Total Affiliés'}</p>
            <p className="text-gray-300 text-xs">
              {t('dashboard.affiliates.total_tooltip_desc') || 'Nombre total de personnes dans votre réseau d\'affiliation, tous niveaux confondus (1 à 10).'}
            </p>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full w-0 h-0 border-l-8 border-r-8 border-t-8 border-transparent border-t-gray-900 dark:border-t-gray-700" />
          </div>
        </div>
        {/* Direct (Level 1) */}
        <div className="relative group bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700 cursor-help transition-all hover:shadow-lg hover:border-blue-200 dark:hover:border-blue-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
              <UserPlus className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {levelStats[1]?.count || 0}
              </p>
              <p className="text-xs text-gray-500">{t('dashboard.affiliates.direct_referrals') || 'Directs'}</p>
            </div>
          </div>
          {/* Tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-gray-900 dark:bg-gray-700 text-white text-sm rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <p className="font-semibold mb-1">{t('dashboard.affiliates.direct_tooltip_title') || 'Referrals Directs'}</p>
            <p className="text-gray-300 text-xs mb-2">
              {t('dashboard.affiliates.direct_tooltip_desc') || 'Utilisateurs que vous avez directement parrainés (niveau 1). Vous gagnez 10% de commission sur leurs paiements KYC.'}
            </p>
            <div className="flex items-center justify-between pt-2 border-t border-gray-700 dark:border-gray-600">
              <span className="text-xs text-gray-400">{t('dashboard.affiliates.earned') || 'Gagné'}:</span>
              <span className="font-bold text-blue-400">{formatCurrency(levelStats[1]?.commissions || 0)}</span>
            </div>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full w-0 h-0 border-l-8 border-r-8 border-t-8 border-transparent border-t-gray-900 dark:border-t-gray-700" />
          </div>
        </div>
        {/* Indirect (Levels 2-10) */}
        <div className="relative group bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700 cursor-help transition-all hover:shadow-lg hover:border-purple-200 dark:hover:border-purple-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center">
              <GitBranch className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {Object.entries(levelStats).filter(([lvl]) => Number(lvl) > 1).reduce((sum, [, stat]) => sum + stat.count, 0)}
              </p>
              <p className="text-xs text-gray-500">{t('dashboard.affiliates.indirect_referrals') || 'Indirects'}</p>
            </div>
          </div>
          {/* Tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-gray-900 dark:bg-gray-700 text-white text-sm rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <p className="font-semibold mb-1">{t('dashboard.affiliates.indirect_tooltip_title') || 'Referrals Indirects'}</p>
            <p className="text-gray-300 text-xs mb-2">
              {t('dashboard.affiliates.indirect_tooltip_desc') || 'Utilisateurs parrainés par vos filleuls (niveaux 2-10). Vous gagnez 1% de commission sur leurs paiements KYC.'}
            </p>
            <div className="flex items-center justify-between pt-2 border-t border-gray-700 dark:border-gray-600">
              <span className="text-xs text-gray-400">{t('dashboard.affiliates.earned') || 'Gagné'}:</span>
              <span className="font-bold text-purple-400">
                {formatCurrency(Object.entries(levelStats).filter(([lvl]) => Number(lvl) > 1).reduce((sum, [, stat]) => sum + stat.commissions, 0))}
              </span>
            </div>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full w-0 h-0 border-l-8 border-r-8 border-t-8 border-transparent border-t-gray-900 dark:border-t-gray-700" />
          </div>
        </div>
        {/* Actifs */}
        <div className="relative group bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700 cursor-help transition-all hover:shadow-lg hover:border-green-200 dark:hover:border-green-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
              <Zap className="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {affiliates.filter(a => a.status === 'active').length}
              </p>
              <p className="text-xs text-gray-500">{t('dashboard.affiliates.active')}</p>
            </div>
          </div>
          {/* Tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-gray-900 dark:bg-gray-700 text-white text-sm rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <p className="font-semibold mb-1">{t('dashboard.affiliates.active_tooltip_title') || 'Affiliés Actifs'}</p>
            <p className="text-gray-300 text-xs">
              {t('dashboard.affiliates.active_tooltip_desc') || 'Utilisateurs ayant un compte actif et pouvant générer des commissions.'}
            </p>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full w-0 h-0 border-l-8 border-r-8 border-t-8 border-transparent border-t-gray-900 dark:border-t-gray-700" />
          </div>
        </div>
        {/* KYC Vérifiés */}
        <div className="relative group bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700 cursor-help transition-all hover:shadow-lg hover:border-teal-200 dark:hover:border-teal-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center">
              <CheckCircle className="w-5 h-5 text-teal-600 dark:text-teal-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {kycStats?.approved || 0}
              </p>
              <p className="text-xs text-gray-500">{t('dashboard.affiliates.kyc_verified') || 'KYC Vérifiés'}</p>
            </div>
          </div>
          {/* Tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-gray-900 dark:bg-gray-700 text-white text-sm rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <p className="font-semibold mb-1">{t('dashboard.affiliates.kyc_verified_tooltip_title') || 'KYC Vérifiés'}</p>
            <p className="text-gray-300 text-xs">
              {t('dashboard.affiliates.kyc_verified_tooltip_desc') || 'Affiliés ayant complété avec succès la vérification d\'identité (KYC approuvé).'}
            </p>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full w-0 h-0 border-l-8 border-r-8 border-t-8 border-transparent border-t-gray-900 dark:border-t-gray-700" />
          </div>
        </div>
        {/* Commissions */}
        <div className="relative group bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700 cursor-help transition-all hover:shadow-lg hover:border-emerald-200 dark:hover:border-emerald-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatCurrency(affiliates.reduce((sum, a) => sum + a.totalEarnings, 0))}
              </p>
              <p className="text-xs text-gray-500">{t('dashboard.affiliates.total_commissions')}</p>
            </div>
          </div>
          {/* Tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-gray-900 dark:bg-gray-700 text-white text-sm rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <p className="font-semibold mb-1">{t('dashboard.affiliates.commissions_tooltip_title') || 'Total Commissions'}</p>
            <p className="text-gray-300 text-xs">
              {t('dashboard.affiliates.commissions_tooltip_desc') || 'Somme de toutes les commissions gagnées grâce à votre réseau d\'affiliation.'}
            </p>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full w-0 h-0 border-l-8 border-r-8 border-t-8 border-transparent border-t-gray-900 dark:border-t-gray-700" />
          </div>
        </div>
      </div>

      {/* Filters */}
      {/* Commission Rates Info */}
      <div className="bg-gradient-to-r from-myhigh5-primary/10 to-purple-500/10 rounded-xl p-4 border border-myhigh5-primary/20">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-myhigh5-primary/20 flex items-center justify-center flex-shrink-0">
            <DollarSign className="w-4 h-4 text-myhigh5-primary" />
          </div>
          <div>
            <p className="font-medium text-gray-900 dark:text-white">
              {t('dashboard.affiliates.commission_structure') || 'Structure des commissions KYC'}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              <span className="font-semibold text-myhigh5-primary">10%</span> {t('dashboard.affiliates.level')} 1 (direct) •
              <span className="font-semibold text-purple-600 dark:text-purple-400 ml-1">1%</span> {t('dashboard.affiliates.levels')} 2-10 (indirect)
            </p>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder={t('dashboard.affiliates.search_placeholder') || 'Rechercher par nom ou email...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 rounded-lg"
            />
          </div>

          {/* Level Filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <select
              value={levelFilter ?? ''}
              onChange={(e) => setLevelFilter(e.target.value ? Number(e.target.value) : null)}
              className="bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">{t('dashboard.affiliates.all_levels') || 'Tous les niveaux'}</option>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(level => (
                <option key={level} value={level}>{t('dashboard.affiliates.level')} {level}</option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <select
            value={statusFilter ?? ''}
            onChange={(e) => setStatusFilter(e.target.value || null)}
            className="bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm"
          >
            <option value="">{t('dashboard.affiliates.all_statuses') || 'Tous les statuts'}</option>
            <option value="active">{t('dashboard.affiliates.active')}</option>
            <option value="inactive">{t('dashboard.affiliates.inactive') || 'Inactif'}</option>
          </select>

          {/* KYC Status Filter */}
          <select
            value={kycStatusFilter ?? ''}
            onChange={(e) => setKycStatusFilter(e.target.value || null)}
            className="bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm"
          >
            <option value="">{t('dashboard.affiliates.all_kyc_statuses') || 'Tous KYC'}</option>
            <option value="none">{t('dashboard.affiliates.kyc_none') || 'Non initié'}</option>
            <option value="pending">{t('dashboard.affiliates.kyc_pending') || 'En attente'}</option>
            <option value="in_progress">{t('dashboard.affiliates.kyc_in_progress') || 'En cours'}</option>
            <option value="approved">{t('dashboard.affiliates.kyc_approved') || 'Vérifié'}</option>
            <option value="rejected">{t('dashboard.affiliates.kyc_rejected') || 'Rejeté'}</option>
            <option value="expired">{t('dashboard.affiliates.kyc_expired') || 'Expiré'}</option>
            <option value="requires_review">{t('dashboard.affiliates.kyc_requires_review') || 'À revoir'}</option>
          </select>
        </div>
      </div>

      {/* Affiliates Table */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 overflow-hidden">
        {/* Table Header */}
        <div className="hidden md:grid md:grid-cols-7 gap-4 p-4 bg-gray-50 dark:bg-gray-700/50 border-b border-gray-100 dark:border-gray-700 text-sm font-medium text-gray-500 dark:text-gray-400">
          {/* Affilié */}
          <div className="col-span-2 relative group cursor-help">
            <span className="border-b border-dashed border-gray-400">{t('dashboard.affiliates.affiliate') || 'Affilié'}</span>
            <div className="absolute top-full left-0 mt-2 w-56 p-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
              {t('dashboard.affiliates.col_affiliate_hint') || 'Informations sur le membre de votre réseau'}
            </div>
          </div>
          {/* Niveau */}
          <div className="text-center relative group cursor-help">
            <span className="border-b border-dashed border-gray-400">{t('dashboard.affiliates.level')}</span>
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 p-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
              {t('dashboard.affiliates.col_level_hint') || 'Niveau 1 = direct (10%), Niveaux 2-10 = indirect (1%)'}
            </div>
          </div>
          {/* KYC */}
          <div className="text-center relative group cursor-help">
            <span className="border-b border-dashed border-gray-400">{t('dashboard.affiliates.kyc_status_label') || 'KYC'}</span>
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 p-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
              {t('dashboard.affiliates.col_kyc_hint') || 'Statut de vérification d\'identité (commission perçue si approuvé)'}
            </div>
          </div>
          {/* Parrainages */}
          <div className="text-center relative group cursor-help">
            <span className="border-b border-dashed border-gray-400">{t('dashboard.affiliates.referrals_count') || 'Parrainages'}</span>
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 p-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
              {t('dashboard.affiliates.col_referrals_hint') || 'Nombre de personnes parrainées par cet affilié'}
            </div>
          </div>
          {/* Gains */}
          <div className="text-center relative group cursor-help">
            <span className="border-b border-dashed border-gray-400">{t('dashboard.affiliates.earnings')}</span>
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 p-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
              {t('dashboard.affiliates.col_earnings_hint') || 'Commission que vous avez gagnée grâce à cet affilié'}
            </div>
          </div>
          {/* Statut */}
          <div className="text-center relative group cursor-help">
            <span className="border-b border-dashed border-gray-400">{t('dashboard.affiliates.status') || 'Statut'}</span>
            <div className="absolute top-full right-0 mt-2 w-56 p-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
              {t('dashboard.affiliates.col_status_hint') || 'Statut du compte utilisateur (actif ou inactif)'}
            </div>
          </div>
        </div>

        {/* Table Body */}
        <div className="divide-y divide-gray-100 dark:divide-gray-700">
          {paginatedAffiliates.map((affiliate) => (
            <div
              key={affiliate.id}
              className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <div className="md:grid md:grid-cols-7 md:gap-4 md:items-center space-y-3 md:space-y-0">
                {/* Affiliate Info */}
                <div className="col-span-2 flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-myhigh5-primary flex items-center justify-center text-white font-semibold shadow-lg shadow-myhigh5-primary/20 flex-shrink-0">
                    {affiliate.name.charAt(0)}
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium text-gray-900 dark:text-white truncate">
                      {affiliate.name}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                      {affiliate.email}
                    </p>
                    <div className="flex items-center gap-1 text-xs text-gray-400 mt-1 md:hidden">
                      <Calendar className="w-3 h-3" />
                      {new Date(affiliate.joinedAt).toLocaleDateString('fr-FR')}
                    </div>
                  </div>
                </div>

                {/* Level */}
                <div className="flex md:justify-center">
                  <span className={`text-xs font-medium px-3 py-1 rounded-full ${getLevelBadge(affiliate.level)}`}>
                    {t('dashboard.affiliates.level')} {affiliate.level}
                  </span>
                </div>

                {/* KYC Status */}
                <div className="flex md:justify-center items-center gap-2">
                  <span className="md:hidden text-sm text-gray-500">KYC:</span>
                  <span className={`text-xs font-medium px-2 py-1 rounded-full ${getKycStatusBadge(affiliate.kyc_status).className}`}>
                    {getKycStatusBadge(affiliate.kyc_status).label}
                  </span>
                </div>

                {/* Referrals */}
                <div className="flex md:justify-center items-center gap-2">
                  <span className="md:hidden text-sm text-gray-500">{t('dashboard.affiliates.referrals_count') || 'Parrainages'}:</span>
                  <span className="font-medium text-gray-900 dark:text-white">{affiliate.referrals}</span>
                </div>

                {/* Earnings */}
                <div className="flex md:justify-center items-center gap-2">
                  <span className="md:hidden text-sm text-gray-500">{t('dashboard.affiliates.earnings')}:</span>
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                    {formatCurrency(affiliate.totalEarnings)}
                  </span>
                </div>

                {/* Status */}
                <div className="flex md:justify-center">
                  {affiliate.status === 'active' ? (
                    <span className="flex items-center gap-1 text-xs font-medium text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30 px-2 py-1 rounded-full">
                      <Zap className="w-3 h-3" />
                      {t('dashboard.affiliates.active')}
                    </span>
                  ) : (
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded-full">
                      {t('dashboard.affiliates.inactive') || 'Inactif'}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Empty State */}
        {paginatedAffiliates.length === 0 && (
          <div className="p-12 text-center">
            <div className="w-16 h-16 mx-auto rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
              <Users className="w-8 h-8 text-gray-400" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              {t('dashboard.affiliates.no_results') || 'Aucun résultat'}
            </h3>
            <p className="text-gray-500 dark:text-gray-400">
              {t('dashboard.affiliates.try_different_filters') || 'Essayez avec des filtres différents'}
            </p>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between p-4 border-t border-gray-100 dark:border-gray-700">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.affiliates.showing') || 'Affichage'} {(currentPage - 1) * itemsPerPage + 1} - {Math.min(currentPage * itemsPerPage, filteredAffiliates.length)} {t('dashboard.affiliates.of') || 'sur'} {filteredAffiliates.length}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="rounded-lg"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <div className="flex items-center gap-1">
                {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    className={`w-8 h-8 rounded-lg text-sm font-medium transition-colors ${page === currentPage
                        ? 'bg-myhigh5-primary text-white'
                        : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400'
                      }`}
                  >
                    {page}
                  </button>
                ))}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="rounded-lg"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
