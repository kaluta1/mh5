'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { 
  Wallet, 
  TrendingUp,
  History,
  Sparkles,
  ChevronRight,
  ShoppingBag,
  Clock
} from 'lucide-react'
import Link from 'next/link'
import { PaymentDialog } from '@/components/dialogs/payment-dialog-v2'
import { TransactionTable, Transaction } from '@/components/wallet/transaction-table'


export default function WalletPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { addToast } = useToast()
  
  const [balance, setBalance] = useState(0)
  const [pendingBalance, setPendingBalance] = useState(0)
  const [totalEarnings, setTotalEarnings] = useState(0)
  const [thisMonth, setThisMonth] = useState(0)
  const [growthRate, setGrowthRate] = useState(0)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [showPaymentDialog, setShowPaymentDialog] = useState(false)

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
      const token = localStorage.getItem('access_token')
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      // Charger le solde du portefeuille
      const balanceResponse = await fetch(`${apiUrl}/api/v1/wallet/balance`, { headers })
      
      if (balanceResponse.ok) {
        const balanceData = await balanceResponse.json()
        setBalance(balanceData.available_balance || 0)
        setPendingBalance(balanceData.pending_balance || 0)
        setTotalEarnings(balanceData.total_earnings || 0)
        setThisMonth(balanceData.this_month || 0)
        setGrowthRate(balanceData.growth_rate || 0)
      }
      
      // Charger les transactions
      const transactionsResponse = await fetch(`${apiUrl}/api/v1/wallet/transactions?limit=20`, { headers })
      
      if (transactionsResponse.ok) {
        const transactionsData = await transactionsResponse.json()
        setTransactions(transactionsData.map((t: any) => ({
          id: t.id,
          type: t.type,
          category: t.category,
          amount: t.amount,
          description: t.description,
          date: t.date,
          status: t.status,
          commission_type: t.commission_type,
          commission_type_label: t.commission_type_label,
          level: t.level,
          product_code: t.product_code,
          source_user: t.source_user,
          deposit_id: t.deposit_id,
          external_payment_id: t.external_payment_id
        })))
      }
    } catch (error) {
      console.error('Error loading wallet data:', error)
      addToast(t('common.error') || 'Erreur lors du chargement des données', 'error')
    } finally {
      setPageLoading(false)
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
            <div className="w-10 h-10 rounded-xl bg-myhigh5-primary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
              <Wallet className="w-5 h-5 text-white" />
            </div>
            {t('dashboard.wallet.title')}
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {t('dashboard.wallet.subtitle')}
          </p>
        </div>
        <div className="flex gap-3">
          <Link href="/dashboard/wallet/transactions">
            <Button 
              variant="outline"
              className="rounded-xl border-2"
            >
              <History className="w-4 h-4 mr-2" />
              {t('dashboard.wallet.history')}
            </Button>
          </Link>
          <Button 
            onClick={() => setShowPaymentDialog(true)}
            className="rounded-xl bg-sky-600 hover:bg-sky-700 shadow-lg shadow-sky-600/25"
          >
            <ShoppingBag className="w-4 h-4 mr-2" />
            {t('dashboard.wallet.buy_service')}
          </Button>
        </div>
      </div>

      {/* Balance Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Main Balance */}
        <div className="relative overflow-hidden bg-myhigh5-primary rounded-2xl p-6 text-white shadow-xl shadow-myhigh5-primary/20">
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
              <span>{growthRate >= 0 ? '+' : ''}{growthRate.toFixed(1)}% {t('dashboard.wallet.this_month')}</span>
            </div>
            <div className="text-xs mt-1 opacity-70">
              {t('dashboard.wallet.this_month')}: {formatCurrency(thisMonth)}
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
            <div className="w-12 h-12 rounded-xl bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
              <Sparkles className="w-6 h-6 text-myhigh5-primary" />
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

      {/* Recent Transactions */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 overflow-hidden">
        <div className="p-6 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <History className="w-5 h-5 text-gray-500" />
              {t('dashboard.wallet.recent_transactions')}
            </h2>
            <Link href="/dashboard/wallet/transactions">
              <Button variant="ghost" size="sm" className="text-myhigh5-primary hover:text-myhigh5-primary/80">
                {t('dashboard.wallet.see_all')}
                <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </Link>
          </div>
        </div>
        
        <TransactionTable 
          transactions={transactions.slice(0, 5)}
          showActions={true}
          onPaymentCompleted={loadWalletData}
          emptyTitle={t('dashboard.wallet.no_transactions') || 'Aucune transaction'}
          emptyDescription={t('dashboard.wallet.no_transactions_desc') || "Vous n'avez pas encore de transactions"}
        />
      </div>
      
      {/* Payment Dialog */}
      <PaymentDialog
        open={showPaymentDialog}
        onOpenChange={setShowPaymentDialog}
        initialProductCode="kyc"
        onPaymentInitiated={() => {
          loadWalletData()
        }}
      />
    </div>
  )
}
