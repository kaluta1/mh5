'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { 
  History,
  ArrowLeft,
  Download
} from 'lucide-react'
import Link from 'next/link'
import { TransactionTable, Transaction } from '@/components/wallet/transaction-table'

export default function TransactionsPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const { user, isAuthenticated, isLoading } = useAuth()
  
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'commission' | 'deposit'>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'completed' | 'approved' | 'pending'>('all')

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    } else if (!isLoading && isAuthenticated) {
      loadTransactions()
    }
  }, [isLoading, isAuthenticated, router])

  useEffect(() => {
    if (isAuthenticated && !pageLoading) {
      loadTransactions()
    }
  }, [filter, statusFilter])

  const loadTransactions = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      const params = new URLSearchParams()
      params.append('limit', '100')
      if (filter !== 'all') {
        params.append('transaction_type', filter)
      }
      
      const response = await fetch(`${apiUrl}/api/v1/wallet/transactions?${params.toString()}`, { headers })
      
      if (response.ok) {
        let data = await response.json()
        
        // Filter by status on client side
        if (statusFilter !== 'all') {
          data = data.filter((t: Transaction) => t.status === statusFilter)
        }
        
        setTransactions(data.map((t: any) => ({
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
      console.error('Error loading transactions:', error)
    } finally {
      setPageLoading(false)
    }
  }

  const exportTransactions = () => {
    if (transactions.length === 0) return
    
    // Create CSV content
    const headers = ['Date', 'Type', 'Description', 'Montant', 'Statut']
    const rows = transactions.map(t => [
      t.date ? new Date(t.date).toLocaleDateString('fr-FR') : '-',
      t.category === 'commission' ? 'Commission' : 'Achat',
      t.description,
      `${t.amount.toFixed(2)} USD`,
      t.status === 'completed' ? 'Payé' : 
        t.status === 'approved' ? 'Approuvé' : 
        t.status === 'pending' ? 'En attente' : 
        t.status === 'expired' ? 'Expiré' : 'Échoué'
    ])
    
    const csvContent = [
      headers.join(';'),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(';'))
    ].join('\n')
    
    // Download CSV
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `transactions-${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }

  if (isLoading || pageLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded-lg" />
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
        <div className="flex items-center gap-4">
          <Link href="/dashboard/wallet">
            <Button variant="ghost" size="icon" className="rounded-xl">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-myfav-primary flex items-center justify-center shadow-lg shadow-myfav-primary/25">
                <History className="w-5 h-5 text-white" />
              </div>
              {t('dashboard.wallet.all_transactions') || 'Toutes les transactions'}
            </h1>
            <p className="text-gray-500 dark:text-gray-400 mt-1">
              {t('dashboard.wallet.transactions_subtitle') || 'Historique complet de vos transactions'}
            </p>
          </div>
        </div>
        <Button 
          variant="outline" 
          className="rounded-xl"
          onClick={exportTransactions}
          disabled={transactions.length === 0}
        >
          <Download className="w-4 h-4 mr-2" />
          {t('dashboard.wallet.export') || 'Exporter'}
        </Button>
      </div>

      {/* Filters */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-4">
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Type filter */}
          <div className="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
            {(['all', 'commission', 'deposit'] as const).map((type) => (
              <button
                key={type}
                onClick={() => setFilter(type)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  filter === type
                    ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                {type === 'all' && (t('dashboard.wallet.all') || 'Tout')}
                {type === 'commission' && (t('dashboard.wallet.commissions') || 'Commissions')}
                {type === 'deposit' && (t('dashboard.wallet.purchases') || 'Achats')}
              </button>
            ))}
          </div>
          
          {/* Status filter */}
          <div className="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-1 overflow-x-auto">
            {(['all', 'completed', 'approved', 'pending'] as const).map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                  statusFilter === status
                    ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                {status === 'all' && (t('dashboard.wallet.all') || 'Tout')}
                {status === 'completed' && (t('dashboard.wallet.completed') || 'Payé')}
                {status === 'approved' && (t('dashboard.wallet.approved') || 'Approuvé')}
                {status === 'pending' && (t('dashboard.wallet.pending') || 'En attente')}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Transactions List */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 overflow-hidden">
        <TransactionTable 
          transactions={transactions}
          showActions={true}
          onPaymentCompleted={loadTransactions}
        />
      </div>
    </div>
  )
}
