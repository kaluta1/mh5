'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { 
  Wallet, 
  ArrowUpRight, 
  ArrowDownLeft, 
  CreditCard,
  TrendingUp,
  Clock,
  CheckCircle,
  XCircle,
  Plus,
  Send,
  History,
  Sparkles,
  Gift,
  DollarSign
} from 'lucide-react'

interface Transaction {
  id: string
  type: 'credit' | 'debit' | 'withdrawal' | 'bonus'
  amount: number
  description: string
  date: string
  status: 'completed' | 'pending' | 'failed'
}

export default function WalletPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { addToast } = useToast()
  
  const [balance, setBalance] = useState(0)
  const [pendingBalance, setPendingBalance] = useState(0)
  const [totalEarnings, setTotalEarnings] = useState(0)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [pageLoading, setPageLoading] = useState(true)

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', { 
      style: 'currency', 
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(amount)
  }

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    } else if (!isLoading && isAuthenticated) {
      loadWalletData()
    }
  }, [isLoading, isAuthenticated, router])

  const loadWalletData = async () => {
    try {
      // TODO: Fetch real wallet data from API
      // Simulated data for now
      setBalance(1250.50)
      setPendingBalance(320.00)
      setTotalEarnings(4580.75)
      setTransactions([
        {
          id: '1',
          type: 'credit',
          amount: 150.00,
          description: t('wallet.commission_affiliate') || 'Commission affilié - Jean Dupont',
          date: '2024-12-04',
          status: 'completed'
        },
        {
          id: '2',
          type: 'bonus',
          amount: 50.00,
          description: t('wallet.welcome_bonus') || 'Bonus de bienvenue',
          date: '2024-12-03',
          status: 'completed'
        },
        {
          id: '3',
          type: 'withdrawal',
          amount: 500.00,
          description: t('wallet.bank_withdrawal') || 'Retrait vers compte bancaire',
          date: '2024-12-02',
          status: 'pending'
        },
        {
          id: '4',
          type: 'credit',
          amount: 75.00,
          description: t('wallet.commission_affiliate') || 'Commission affilié - Marie Martin',
          date: '2024-12-01',
          status: 'completed'
        },
        {
          id: '5',
          type: 'debit',
          amount: 25.00,
          description: t('wallet.premium_votes') || 'Achat de votes premium',
          date: '2024-11-30',
          status: 'completed'
        }
      ])
    } catch (error) {
      console.error('Error loading wallet data:', error)
      addToast(t('common.error') || 'Erreur lors du chargement des données', 'error')
    } finally {
      setPageLoading(false)
    }
  }

  const getTransactionIcon = (type: string) => {
    switch (type) {
      case 'credit':
        return <ArrowDownLeft className="w-5 h-5 text-green-500" />
      case 'debit':
        return <ArrowUpRight className="w-5 h-5 text-red-500" />
      case 'withdrawal':
        return <Send className="w-5 h-5 text-orange-500" />
      case 'bonus':
        return <Gift className="w-5 h-5 text-myfav-primary" />
      default:
        return <DollarSign className="w-5 h-5 text-gray-500" />
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <span className="flex items-center gap-1 text-xs font-medium text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30 px-2 py-1 rounded-full">
            <CheckCircle className="w-3 h-3" />
            {t('dashboard.wallet.completed')}
          </span>
        )
      case 'pending':
        return (
          <span className="flex items-center gap-1 text-xs font-medium text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30 px-2 py-1 rounded-full">
            <Clock className="w-3 h-3" />
            {t('dashboard.wallet.pending')}
          </span>
        )
      case 'failed':
        return (
          <span className="flex items-center gap-1 text-xs font-medium text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30 px-2 py-1 rounded-full">
            <XCircle className="w-3 h-3" />
            {t('dashboard.wallet.failed')}
          </span>
        )
      default:
        return null
    }
  }

  if (isLoading || pageLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-40 bg-gray-200 dark:bg-gray-700 rounded-2xl" />
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
            <div className="w-10 h-10 rounded-xl bg-myfav-primary flex items-center justify-center shadow-lg shadow-myfav-primary/25">
              <Wallet className="w-5 h-5 text-white" />
            </div>
            {t('dashboard.wallet.title')}
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {t('dashboard.wallet.subtitle')}
          </p>
        </div>
        <div className="flex gap-3">
          <Button 
            variant="outline"
            className="rounded-xl border-2"
          >
            <History className="w-4 h-4 mr-2" />
            {t('dashboard.wallet.history')}
          </Button>
          <Button 
            className="rounded-xl bg-myfav-primary hover:bg-myfav-primary/90 shadow-lg shadow-myfav-primary/25"
          >
            <Send className="w-4 h-4 mr-2" />
            {t('dashboard.wallet.withdraw')}
          </Button>
        </div>
      </div>

      {/* Balance Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Main Balance */}
        <div className="relative overflow-hidden bg-myfav-primary rounded-2xl p-6 text-white shadow-xl shadow-myfav-primary/20">
          <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-white/10 rounded-full translate-y-1/2 -translate-x-1/2" />
          <div className="relative">
            <div className="flex items-center gap-2 mb-2">
              <Wallet className="w-5 h-5 opacity-80" />
              <span className="text-sm font-medium opacity-90">{t('dashboard.wallet.available_balance')}</span>
            </div>
            <div className="text-4xl font-bold mb-4">
              {formatCurrency(balance)}
            </div>
            <div className="flex items-center gap-2 text-sm opacity-80">
              <TrendingUp className="w-4 h-4" />
              <span>+12.5% {t('dashboard.wallet.this_month')}</span>
            </div>
          </div>
        </div>

        {/* Pending Balance */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-lg transition-shadow">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center">
              <Clock className="w-6 h-6 text-orange-500" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.wallet.pending_balance')}</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatCurrency(pendingBalance)}
              </p>
            </div>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t('dashboard.wallet.pending_description')}
          </p>
        </div>

        {/* Total Earnings */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-lg transition-shadow">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl bg-myfav-primary/10 dark:bg-myfav-primary/20 flex items-center justify-center">
              <Sparkles className="w-6 h-6 text-myfav-primary" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.wallet.total_earnings')}</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatCurrency(totalEarnings)}
              </p>
            </div>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t('dashboard.wallet.since_registration')}
          </p>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <button className="flex flex-col items-center gap-2 p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 hover:border-myfav-primary/50 dark:hover:border-myfav-primary/50 hover:shadow-lg transition-all group">
          <div className="w-12 h-12 rounded-full bg-myfav-primary/10 dark:bg-myfav-primary/20 flex items-center justify-center group-hover:scale-110 transition-transform">
            <Plus className="w-6 h-6 text-myfav-primary" />
          </div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('dashboard.wallet.add_funds')}</span>
        </button>
        
        <button className="flex flex-col items-center gap-2 p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 hover:border-purple-300 dark:hover:border-purple-700 hover:shadow-lg transition-all group">
          <div className="w-12 h-12 rounded-full bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center group-hover:scale-110 transition-transform">
            <Send className="w-6 h-6 text-purple-600 dark:text-purple-400" />
          </div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('dashboard.wallet.withdraw')}</span>
        </button>
        
        <button className="flex flex-col items-center gap-2 p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 hover:border-pink-300 dark:hover:border-pink-700 hover:shadow-lg transition-all group">
          <div className="w-12 h-12 rounded-full bg-pink-100 dark:bg-pink-900/30 flex items-center justify-center group-hover:scale-110 transition-transform">
            <Gift className="w-6 h-6 text-pink-600 dark:text-pink-400" />
          </div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('dashboard.wallet.redeem')}</span>
        </button>
        
        <button className="flex flex-col items-center gap-2 p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 hover:border-orange-300 dark:hover:border-orange-700 hover:shadow-lg transition-all group">
          <div className="w-12 h-12 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center group-hover:scale-110 transition-transform">
            <CreditCard className="w-6 h-6 text-orange-600 dark:text-orange-400" />
          </div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('dashboard.wallet.cards')}</span>
        </button>
      </div>

      {/* Recent Transactions */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 overflow-hidden">
        <div className="p-6 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <History className="w-5 h-5 text-gray-500" />
              {t('dashboard.wallet.recent_transactions')}
            </h2>
            <Button variant="ghost" size="sm" className="text-myfav-primary hover:text-myfav-primary/80">
              {t('dashboard.wallet.see_all')}
            </Button>
          </div>
        </div>
        
        <div className="divide-y divide-gray-100 dark:divide-gray-700">
          {transactions.map((transaction) => (
            <div 
              key={transaction.id} 
              className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                  transaction.type === 'credit' || transaction.type === 'bonus'
                    ? 'bg-green-100 dark:bg-green-900/30'
                    : transaction.type === 'withdrawal'
                    ? 'bg-orange-100 dark:bg-orange-900/30'
                    : 'bg-red-100 dark:bg-red-900/30'
                }`}>
                  {getTransactionIcon(transaction.type)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {transaction.description}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {new Date(transaction.date).toLocaleDateString('fr-FR', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric'
                    })}
                  </p>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-semibold ${
                    transaction.type === 'credit' || transaction.type === 'bonus'
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}>
                    {transaction.type === 'credit' || transaction.type === 'bonus' ? '+' : '-'}
                    {formatCurrency(transaction.amount)}
                  </p>
                  {getStatusBadge(transaction.status)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
