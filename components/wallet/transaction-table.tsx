'use client'

import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { 
  ArrowUpRight, 
  ArrowDownLeft, 
  Clock,
  CheckCircle,
  XCircle,
  History,
  Gift,
  DollarSign,
  FileText,
  CreditCard,
  ExternalLink
} from 'lucide-react'
import { ResumePaymentDialog } from '@/components/dialogs/resume-payment-dialog'

export interface Transaction {
  id: string
  type: 'credit' | 'debit' | 'withdrawal' | 'bonus'
  category?: 'commission' | 'deposit' | 'withdrawal'
  amount: number
  description: string
  date: string
  status: 'completed' | 'pending' | 'failed' | 'approved' | 'expired' | 'validated'
  commission_type?: string
  commission_type_label?: string
  level?: number
  product_code?: string
  source_user?: string
  deposit_id?: number
  external_payment_id?: string
}

interface TransactionTableProps {
  transactions: Transaction[]
  showActions?: boolean
  onPaymentCompleted?: () => void
  emptyIcon?: React.ReactNode
  emptyTitle?: string
  emptyDescription?: string
}

export function TransactionTable({ 
  transactions, 
  showActions = true,
  onPaymentCompleted,
  emptyIcon,
  emptyTitle,
  emptyDescription
}: TransactionTableProps) {
  const { t, language } = useLanguage()
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null)
  const [showResumeDialog, setShowResumeDialog] = useState(false)

  // Mapping des langues vers les locales
  const localeMap: Record<string, string> = {
    fr: 'fr-FR',
    en: 'en-US',
    es: 'es-ES',
    de: 'de-DE'
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat(localeMap[language] || 'en-US', { 
      style: 'currency', 
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(amount)
  }

  const formatDate = (dateString: string) => {
    if (!dateString) return '-'
    return new Date(dateString).toLocaleDateString(localeMap[language] || 'en-US', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getTransactionIcon = (type: string, category?: string) => {
    if (category === 'commission' || type === 'credit') {
      return <ArrowDownLeft className="w-5 h-5 text-green-500" />
    } else if (type === 'bonus') {
      return <Gift className="w-5 h-5 text-purple-500" />
    } else if (category === 'deposit' || type === 'debit') {
      return <ArrowUpRight className="w-5 h-5 text-red-500" />
    }
    return <DollarSign className="w-5 h-5 text-gray-500" />
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
      case 'validated':
        return (
          <span className="flex items-center gap-1 text-xs font-medium text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30 px-2 py-1 rounded-full">
            <CheckCircle className="w-3 h-3" />
            {t('dashboard.wallet.completed') || 'Payé'}
          </span>
        )
      case 'approved':
        return (
          <span className="flex items-center gap-1 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/30 px-2 py-1 rounded-full">
            <CheckCircle className="w-3 h-3" />
            {t('dashboard.wallet.approved') || 'Approuvé'}
          </span>
        )
      case 'pending':
        return (
          <span className="flex items-center gap-1 text-xs font-medium text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30 px-2 py-1 rounded-full">
            <Clock className="w-3 h-3" />
            {t('dashboard.wallet.pending') || 'En attente'}
          </span>
        )
      case 'failed':
        return (
          <span className="flex items-center gap-1 text-xs font-medium text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30 px-2 py-1 rounded-full">
            <XCircle className="w-3 h-3" />
            {t('dashboard.wallet.failed') || 'Échoué'}
          </span>
        )
      case 'expired':
        return (
          <span className="flex items-center gap-1 text-xs font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded-full">
            <Clock className="w-3 h-3" />
            {t('dashboard.wallet.expired') || 'Expiré'}
          </span>
        )
      default:
        return null
    }
  }

  const getCategoryBadge = (category?: string, commissionTypeLabel?: string) => {
    if (category === 'commission') {
      return (
        <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-900/30 px-2 py-0.5 rounded-full">
          {commissionTypeLabel || t('dashboard.wallet.commission') || 'Commission'}
        </span>
      )
    } else if (category === 'deposit') {
      return (
        <span className="text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/30 px-2 py-0.5 rounded-full">
          {t('dashboard.wallet.purchase') || 'Achat'}
        </span>
      )
    }
    return null
  }

  const handlePayClick = (transaction: Transaction) => {
    setSelectedTransaction(transaction)
    setShowResumeDialog(true)
  }

  const handlePaymentCompleted = () => {
    setShowResumeDialog(false)
    setSelectedTransaction(null)
    onPaymentCompleted?.()
  }

  const openInvoice = (transaction: Transaction) => {
    const token = localStorage.getItem('access_token')
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    
    // Extract deposit ID from transaction id (format: "dep_123")
    const depositId = transaction.deposit_id || transaction.id.replace('dep_', '')
    
    // Open invoice in new tab with language parameter
    window.open(`${apiUrl}/api/v1/payments/invoice/${depositId}?token=${token}&lang=${language}`, '_blank')
  }

  if (transactions.length === 0) {
    return (
      <div className="p-12 text-center">
        <div className="w-16 h-16 mx-auto rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
          {emptyIcon || <History className="w-8 h-8 text-gray-400" />}
        </div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          {emptyTitle || t('dashboard.wallet.no_transactions') || 'Aucune transaction'}
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          {emptyDescription || t('dashboard.wallet.no_transactions_desc') || "Vous n'avez pas encore de transactions"}
        </p>
      </div>
    )
  }

  return (
    <>
      <div className="divide-y divide-gray-100 dark:divide-gray-700">
        {transactions.map((transaction) => (
          <div 
            key={transaction.id} 
            className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
          >
            <div className="flex items-center gap-4">
              {/* Icon */}
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                transaction.type === 'credit' || transaction.type === 'bonus'
                  ? 'bg-green-100 dark:bg-green-900/30'
                  : transaction.type === 'withdrawal'
                  ? 'bg-orange-100 dark:bg-orange-900/30'
                  : 'bg-red-100 dark:bg-red-900/30'
              }`}>
                {getTransactionIcon(transaction.type, transaction.category)}
              </div>
              
              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  {getCategoryBadge(transaction.category, transaction.commission_type_label)}
                  {getStatusBadge(transaction.status)}
                </div>
                <p className="font-medium text-gray-900 dark:text-white truncate">
                  {transaction.description}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {formatDate(transaction.date)}
                </p>
              </div>
              
              {/* Amount & Actions */}
              <div className="text-right flex items-center gap-3">
                <p className={`text-lg font-bold ${
                  transaction.type === 'credit' || transaction.type === 'bonus'
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-gray-900 dark:text-white'
                }`}>
                  {formatCurrency(transaction.amount)}
                </p>
                
                {showActions && (
                  <div className="flex items-center gap-2">
                    {/* Bouton Payer pour les dépôts en attente uniquement (pas expiré) */}
                    {transaction.category === 'deposit' && 
                     transaction.status === 'pending' && 
                     transaction.external_payment_id && (
                      <Button
                        size="sm"
                        className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white rounded-lg"
                        onClick={() => handlePayClick(transaction)}
                      >
                        <CreditCard className="w-4 h-4 mr-1" />
                        {t('dashboard.wallet.pay') || 'Payer'}
                      </Button>
                    )}
                    
                    {/* Bouton Facture pour les dépôts complétés/validés */}
                    {transaction.category === 'deposit' && 
                     (transaction.status === 'completed' || transaction.status === 'validated') && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="rounded-lg"
                        onClick={() => openInvoice(transaction)}
                      >
                        <FileText className="w-4 h-4 mr-1" />
                        {t('dashboard.wallet.invoice') || 'Facture'}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Resume Payment Dialog */}
      {selectedTransaction && (
        <ResumePaymentDialog
          open={showResumeDialog}
          onOpenChange={setShowResumeDialog}
          depositId={selectedTransaction.deposit_id || parseInt(selectedTransaction.id)}
          externalPaymentId={selectedTransaction.external_payment_id}
          productCode={selectedTransaction.product_code}
          amount={selectedTransaction.amount}
          onPaymentCompleted={handlePaymentCompleted}
        />
      )}
    </>
  )
}
