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
  ArrowLeft
} from 'lucide-react'
import Link from 'next/link'

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
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 10

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    } else if (!isLoading && isAuthenticated) {
      loadAffiliatesData()
    }
  }, [isLoading, isAuthenticated, router])

  useEffect(() => {
    filterAffiliates()
  }, [searchQuery, levelFilter, statusFilter, affiliates])

  const loadAffiliatesData = async () => {
    try {
      // TODO: Fetch real affiliates data from API
      // Simulated data for now
      const mockAffiliates: Affiliate[] = [
        { id: '1', name: 'Jean Dupont', email: 'jean.dupont@email.com', joinedAt: '2024-11-15', level: 1, totalEarnings: 450.00, status: 'active', referrals: 5 },
        { id: '2', name: 'Marie Martin', email: 'marie.martin@email.com', joinedAt: '2024-11-20', level: 1, totalEarnings: 320.50, status: 'active', referrals: 3 },
        { id: '3', name: 'Pierre Bernard', email: 'pierre.bernard@email.com', joinedAt: '2024-11-25', level: 2, totalEarnings: 180.00, status: 'active', referrals: 2 },
        { id: '4', name: 'Sophie Petit', email: 'sophie.petit@email.com', joinedAt: '2024-12-01', level: 1, totalEarnings: 95.00, status: 'inactive', referrals: 0 },
        { id: '5', name: 'Lucas Moreau', email: 'lucas.moreau@email.com', joinedAt: '2024-12-03', level: 2, totalEarnings: 0, status: 'active', referrals: 0 },
        { id: '6', name: 'Emma Leroy', email: 'emma.leroy@email.com', joinedAt: '2024-10-15', level: 1, totalEarnings: 780.00, status: 'active', referrals: 8 },
        { id: '7', name: 'Hugo Girard', email: 'hugo.girard@email.com', joinedAt: '2024-10-20', level: 3, totalEarnings: 120.00, status: 'active', referrals: 1 },
        { id: '8', name: 'Léa Bonnet', email: 'lea.bonnet@email.com', joinedAt: '2024-09-10', level: 1, totalEarnings: 1250.00, status: 'active', referrals: 12 },
        { id: '9', name: 'Nathan Dubois', email: 'nathan.dubois@email.com', joinedAt: '2024-11-05', level: 2, totalEarnings: 85.00, status: 'inactive', referrals: 0 },
        { id: '10', name: 'Chloé Fournier', email: 'chloe.fournier@email.com', joinedAt: '2024-11-28', level: 1, totalEarnings: 210.00, status: 'active', referrals: 2 },
        { id: '11', name: 'Louis Mercier', email: 'louis.mercier@email.com', joinedAt: '2024-12-02', level: 4, totalEarnings: 45.00, status: 'active', referrals: 0 },
        { id: '12', name: 'Camille Roux', email: 'camille.roux@email.com', joinedAt: '2024-10-30', level: 1, totalEarnings: 560.00, status: 'active', referrals: 6 },
        { id: '13', name: 'Gabriel Blanc', email: 'gabriel.blanc@email.com', joinedAt: '2024-11-12', level: 2, totalEarnings: 95.00, status: 'inactive', referrals: 1 },
        { id: '14', name: 'Inès Garnier', email: 'ines.garnier@email.com', joinedAt: '2024-09-25', level: 1, totalEarnings: 920.00, status: 'active', referrals: 9 },
        { id: '15', name: 'Raphaël Faure', email: 'raphael.faure@email.com', joinedAt: '2024-11-18', level: 3, totalEarnings: 65.00, status: 'active', referrals: 0 },
      ]
      setAffiliates(mockAffiliates)
      setFilteredAffiliates(mockAffiliates)
    } catch (error) {
      console.error('Error loading affiliates data:', error)
      addToast('Erreur lors du chargement des données', 'error')
    } finally {
      setPageLoading(false)
    }
  }

  const filterAffiliates = () => {
    let filtered = [...affiliates]
    
    if (searchQuery) {
      filtered = filtered.filter(a => 
        a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        a.email.toLowerCase().includes(searchQuery.toLowerCase())
      )
    }
    
    if (levelFilter !== null) {
      filtered = filtered.filter(a => a.level === levelFilter)
    }
    
    if (statusFilter) {
      filtered = filtered.filter(a => a.status === statusFilter)
    }
    
    setFilteredAffiliates(filtered)
    setCurrentPage(1)
  }

  const getLevelBadge = (level: number) => {
    const opacity = Math.max(100 - (level - 1) * 10, 20)
    return `bg-myfav-primary/${opacity} text-white`
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
              <div className="w-10 h-10 rounded-xl bg-myfav-primary flex items-center justify-center shadow-lg shadow-myfav-primary/25">
                <Users className="w-5 h-5 text-white" />
              </div>
              {t('dashboard.affiliates.all_affiliates') || 'Tous les affiliés'}
            </h1>
            <p className="text-gray-500 dark:text-gray-400 mt-1">
              {filteredAffiliates.length} {t('dashboard.affiliates.affiliates_found') || 'affiliés trouvés'}
            </p>
          </div>
        </div>
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-myfav-primary/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-myfav-primary" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{affiliates.length}</p>
              <p className="text-xs text-gray-500">{t('dashboard.affiliates.total_affiliates')}</p>
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700">
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
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {affiliates.reduce((sum, a) => sum + a.referrals, 0)}
              </p>
              <p className="text-xs text-gray-500">{t('dashboard.affiliates.total_referrals') || 'Parrainages'}</p>
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700">
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
        </div>
      </div>

      {/* Filters */}
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
        </div>
      </div>

      {/* Affiliates Table */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 overflow-hidden">
        {/* Table Header */}
        <div className="hidden md:grid md:grid-cols-6 gap-4 p-4 bg-gray-50 dark:bg-gray-700/50 border-b border-gray-100 dark:border-gray-700 text-sm font-medium text-gray-500 dark:text-gray-400">
          <div className="col-span-2">{t('dashboard.affiliates.affiliate') || 'Affilié'}</div>
          <div className="text-center">{t('dashboard.affiliates.level')}</div>
          <div className="text-center">{t('dashboard.affiliates.referrals_count') || 'Parrainages'}</div>
          <div className="text-center">{t('dashboard.affiliates.earnings')}</div>
          <div className="text-center">{t('dashboard.affiliates.status') || 'Statut'}</div>
        </div>
        
        {/* Table Body */}
        <div className="divide-y divide-gray-100 dark:divide-gray-700">
          {paginatedAffiliates.map((affiliate) => (
            <div 
              key={affiliate.id} 
              className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <div className="md:grid md:grid-cols-6 md:gap-4 md:items-center space-y-3 md:space-y-0">
                {/* Affiliate Info */}
                <div className="col-span-2 flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-myfav-primary flex items-center justify-center text-white font-semibold shadow-lg shadow-myfav-primary/20 flex-shrink-0">
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
                    className={`w-8 h-8 rounded-lg text-sm font-medium transition-colors ${
                      page === currentPage
                        ? 'bg-myfav-primary text-white'
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
