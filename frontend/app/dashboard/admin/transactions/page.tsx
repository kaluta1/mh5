'use client'

import { useLanguage } from '@/contexts/language-context'
import { CreditCard, Search, User, Calendar, CheckCircle2, Clock, XCircle, Eye, ArrowDownCircle, ArrowUpCircle, DollarSign, FileText } from 'lucide-react'
import { useState, useEffect } from 'react'
import api from '@/lib/api'
import { cacheService } from '@/lib/cache-service'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/toast'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface Transaction {
  id: number
  type: string
  amount: number
  currency: string
  status: string
  description: string | null
  reference: string | null
  created_at: string
  processed_at: string | null
  user: {
    id: number
    username: string | null
    email: string
    full_name: string | null
    avatar_url: string | null
  } | null
  contest: {
    id: number
    name: string
  } | null
  payment_method: string | null
  product_type: string | null
  order_id: string | null
  external_payment_id: string | null
  tx_hash: string | null
  validated_at: string | null
  validated_by: number | null
}

export default function TransactionsPage() {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  useEffect(() => {
    fetchTransactions()
  }, [typeFilter, statusFilter])

  const fetchTransactions = async () => {
    try {
      setLoading(true)
      const endpoint = '/api/v1/admin/transactions'
      const params: any = {}
      
      if (typeFilter !== 'all') {
        params.transaction_type = typeFilter
      }
      if (statusFilter !== 'all') {
        params.status = statusFilter
      }
      
      // Vérifier le cache
      const cachedData = cacheService.get<Transaction[]>(endpoint, params)
      if (cachedData) {
        setTransactions(cachedData)
        setLoading(false)
        return
      }
      
      // Si pas de cache, faire l'appel API
      const urlParams = new URLSearchParams()
      if (typeFilter !== 'all') {
        urlParams.append('transaction_type', typeFilter)
      }
      if (statusFilter !== 'all') {
        urlParams.append('status', statusFilter)
      }
      if (searchTerm) {
        urlParams.append('search', searchTerm)
      }
      
      const response = await api.get(`${endpoint}?${urlParams.toString()}`)
      const data = response.data || []
      setTransactions(data)
      
      // Mettre en cache (TTL de 2 minutes car les transactions changent souvent)
      cacheService.set(endpoint, data, params, 2 * 60 * 1000)
    } catch (error: any) {
      console.error('Erreur lors du chargement des transactions:', error)
      addToast(error.response?.data?.detail || t('admin.transactions.load_error') || 'Erreur lors du chargement des transactions', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async () => {
    try {
      setLoading(true)
      const endpoint = '/api/v1/admin/transactions'
      const urlParams = new URLSearchParams()
      
      if (typeFilter !== 'all') {
        urlParams.append('transaction_type', typeFilter)
      }
      if (statusFilter !== 'all') {
        urlParams.append('status', statusFilter)
      }
      if (searchTerm) {
        urlParams.append('search', searchTerm)
      }
      
      const response = await api.get(`${endpoint}?${urlParams.toString()}`)
      setTransactions(response.data || [])
      
      // Invalider le cache pour cette recherche
      cacheService.invalidate(endpoint)
    } catch (error: any) {
      console.error('Erreur lors de la recherche:', error)
      addToast(error.response?.data?.detail || t('admin.transactions.load_error') || 'Erreur lors du chargement des transactions', 'error')
    } finally {
      setLoading(false)
    }
  }

  const getTypeBadge = (type: string) => {
    const typeConfig: Record<string, { label: string; variant: string; icon: any }> = {
      deposit: { label: t('admin.transactions.type.deposit') || 'Dépôt', variant: 'green', icon: ArrowDownCircle },
      withdrawal: { label: t('admin.transactions.type.withdrawal') || 'Retrait', variant: 'red', icon: ArrowUpCircle },
      entry_fee: { label: t('admin.transactions.type.entry_fee') || 'Frais d\'entrée', variant: 'blue', icon: FileText },
      prize_payout: { label: t('admin.transactions.type.prize_payout') || 'Gain', variant: 'yellow', icon: DollarSign },
      commission: { label: t('admin.transactions.type.commission') || 'Commission', variant: 'purple', icon: DollarSign },
      refund: { label: t('admin.transactions.type.refund') || 'Remboursement', variant: 'gray', icon: ArrowDownCircle }
    }
    
    const config = typeConfig[type] || { label: type, variant: 'gray', icon: CreditCard }
    const Icon = config.icon
    
    const variantClasses: Record<string, string> = {
      green: 'bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-400',
      red: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400',
      blue: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-400',
      yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-400',
      purple: 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/20 dark:text-purple-400',
      gray: 'bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-900/20 dark:text-gray-400'
    }
    
    return (
      <Badge variant="outline" className={variantClasses[config.variant]}>
        <Icon className="h-3 w-3 mr-1" />
        {config.label}
      </Badge>
    )
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
      case 'PENDING':
        return <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-400"><Clock className="h-3 w-3 mr-1" />{t('admin.transactions.status.pending') || 'En attente'}</Badge>
      case 'completed':
      case 'COMPLETED':
      case 'validated':
      case 'VALIDATED':
        return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-400"><CheckCircle2 className="h-3 w-3 mr-1" />{t('admin.transactions.status.completed') || 'Complété'}</Badge>
      case 'failed':
      case 'FAILED':
      case 'rejected':
      case 'REJECTED':
        return <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400"><XCircle className="h-3 w-3 mr-1" />{t('admin.transactions.status.failed') || 'Échoué'}</Badge>
      case 'cancelled':
      case 'CANCELLED':
      case 'expired':
      case 'EXPIRED':
        return <Badge variant="outline" className="bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-900/20 dark:text-gray-400"><XCircle className="h-3 w-3 mr-1" />{t('admin.transactions.status.cancelled') || 'Annulé'}</Badge>
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  const formatAmount = (amount: number, currency: string) => {
    // Liste des devises fiat standard supportées par Intl.NumberFormat
    const fiatCurrencies = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CAD', 'AUD', 'CHF', 'INR', 'BRL', 'MXN', 'KRW', 'SGD', 'HKD', 'NZD', 'ZAR', 'SEK', 'NOK', 'DKK', 'PLN', 'TRY', 'RUB', 'CZK', 'HUF', 'ILS', 'CLP', 'PHP', 'AED', 'SAR', 'MYR', 'THB', 'IDR', 'VND', 'PKR', 'BDT', 'EGP', 'NGN', 'KES', 'UGX', 'TZS', 'ETB', 'GHS', 'ZMW', 'MAD', 'TND', 'DZD', 'XOF', 'XAF', 'RWF', 'MWK', 'MZN', 'AOA', 'BWP', 'LSL', 'SZL', 'ZWL', 'XCD', 'BBD', 'BMD', 'BZD', 'KYD', 'JMD', 'TTD', 'AWG', 'SRD', 'GYD', 'FJD', 'PGK', 'SBD', 'VUV', 'WST', 'TOP', 'XPF', 'NPR', 'BTN', 'AFN', 'IRR', 'IQD', 'JOD', 'KWD', 'LBP', 'OMR', 'QAR', 'YER', 'AMD', 'AZN', 'BYN', 'GEL', 'KZT', 'KGS', 'MDL', 'TJS', 'TMT', 'UAH', 'UZS', 'BGN', 'HRK', 'RON', 'RSD', 'BAM', 'MKD', 'ALL', 'ISK', 'LTL', 'LVL', 'EEK']
    
    // Si c'est une cryptomonnaie ou une devise non standard, formater manuellement
    if (!currency || !fiatCurrencies.includes(currency.toUpperCase())) {
      // Formater le nombre avec des séparateurs de milliers
      const formattedAmount = new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 8
      }).format(amount)
      
      // Retourner avec le symbole de la devise
      return `${formattedAmount} ${currency?.toUpperCase() || 'USD'}`
    }
    
    // Pour les devises fiat standard, utiliser Intl.NumberFormat
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency.toUpperCase()
      }).format(amount)
    } catch (error) {
      // En cas d'erreur, formater manuellement
      const formattedAmount = new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 8
      }).format(amount)
      return `${formattedAmount} ${currency?.toUpperCase() || 'USD'}`
    }
  }

  const filteredTransactions = transactions.filter((transaction) => {
    if (!searchTerm) return true
    const search = searchTerm.toLowerCase()
    return (
      transaction.reference?.toLowerCase().includes(search) ||
      transaction.description?.toLowerCase().includes(search) ||
      transaction.user?.email?.toLowerCase().includes(search) ||
      transaction.user?.username?.toLowerCase().includes(search) ||
      transaction.user?.full_name?.toLowerCase().includes(search) ||
      transaction.order_id?.toLowerCase().includes(search) ||
      transaction.external_payment_id?.toLowerCase().includes(search)
    )
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex items-center gap-3">
          <CreditCard className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
          <div>
            <h1 className="text-4xl font-bold text-white dark:text-white">
              {t('admin.transactions.title') || 'Gestion des Transactions'}
            </h1>
            <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium mt-1">
              {t('admin.transactions.description') || 'Consultez toutes les transactions (dépôts, retraits, etc.)'}
            </p>
          </div>
        </div>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder={t('admin.transactions.search_placeholder') || 'Rechercher par référence, description, utilisateur...'}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') handleSearch()
                }}
                className="pl-10"
              />
            </div>
            <div className="flex gap-2 flex-wrap">
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="block w-full sm:w-auto pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-myhigh5-primary focus:border-myhigh5-primary sm:text-sm rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              >
                <option value="all">{t('admin.transactions.all_types') || 'Tous les types'}</option>
                <option value="deposit">{t('admin.transactions.type.deposit') || 'Dépôt'}</option>
                <option value="withdrawal">{t('admin.transactions.type.withdrawal') || 'Retrait'}</option>
                <option value="entry_fee">{t('admin.transactions.type.entry_fee') || 'Frais d\'entrée'}</option>
                <option value="prize_payout">{t('admin.transactions.type.prize_payout') || 'Gain'}</option>
                <option value="commission">{t('admin.transactions.type.commission') || 'Commission'}</option>
                <option value="refund">{t('admin.transactions.type.refund') || 'Remboursement'}</option>
              </select>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="block w-full sm:w-auto pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-myhigh5-primary focus:border-myhigh5-primary sm:text-sm rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              >
                <option value="all">{t('admin.transactions.all_statuses') || 'Tous les statuts'}</option>
                <option value="pending">{t('admin.transactions.status.pending') || 'En attente'}</option>
                <option value="completed">{t('admin.transactions.status.completed') || 'Complété'}</option>
                <option value="validated">{t('admin.transactions.status.completed') || 'Validé'}</option>
                <option value="failed">{t('admin.transactions.status.failed') || 'Échoué'}</option>
                <option value="rejected">{t('admin.transactions.status.failed') || 'Rejeté'}</option>
                <option value="cancelled">{t('admin.transactions.status.cancelled') || 'Annulé'}</option>
              </select>
              <Button onClick={handleSearch}>
                {t('admin.transactions.search') || 'Rechercher'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Transactions List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
        </div>
      ) : filteredTransactions.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <CreditCard className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">
              {searchTerm || typeFilter !== 'all' || statusFilter !== 'all' 
                ? (t('admin.transactions.no_transactions_found') || 'Aucune transaction trouvée')
                : (t('admin.transactions.no_transactions') || 'Aucune transaction pour le moment')}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredTransactions.map((transaction) => (
            <Card key={transaction.id} className="hover:shadow-lg transition-shadow">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <CardTitle className="text-lg">{t('admin.transactions.transaction') || 'Transaction'} #{transaction.id}</CardTitle>
                      {getTypeBadge(transaction.type)}
                      {getStatusBadge(transaction.status)}
                    </div>
                    <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                      <span className="font-semibold text-lg text-gray-900 dark:text-white">
                        {formatAmount(transaction.amount, transaction.currency)}
                      </span>
                      {transaction.description && (
                        <span>{transaction.description}</span>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSelectedTransaction(transaction)
                      setIsDialogOpen(true)
                    }}
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    {t('admin.transactions.details') || 'Détails'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* User */}
                  {transaction.user && (
                    <div className="space-y-2">
                      <h4 className="font-semibold text-sm text-gray-700 dark:text-gray-300">{t('admin.transactions.user') || 'Utilisateur'}</h4>
                      <div className="flex items-center gap-2">
                        <Avatar className="h-8 w-8">
                          <AvatarImage src={transaction.user.avatar_url || undefined} />
                          <AvatarFallback>
                            {transaction.user.full_name?.[0] || transaction.user.username?.[0] || 'U'}
                          </AvatarFallback>
                        </Avatar>
                        <div className="text-sm">
                          <p className="font-medium">{transaction.user.full_name || transaction.user.username}</p>
                          <p className="text-gray-500 dark:text-gray-400 text-xs">{transaction.user.email}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Contest */}
                  {transaction.contest && (
                    <div className="space-y-2">
                      <h4 className="font-semibold text-sm text-gray-700 dark:text-gray-300">{t('admin.transactions.contest') || 'Concours'}</h4>
                      <p className="text-sm">{transaction.contest.name}</p>
                    </div>
                  )}

                  {/* Payment Method */}
                  {transaction.payment_method && (
                    <div className="space-y-2">
                      <h4 className="font-semibold text-sm text-gray-700 dark:text-gray-300">{t('admin.transactions.payment_method') || 'Méthode de paiement'}</h4>
                      <p className="text-sm">{transaction.payment_method}</p>
                    </div>
                  )}
                </div>

                <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                    <div className="flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      <span>{t('admin.transactions.created_at') || 'Créé le'} {new Date(transaction.created_at).toLocaleDateString('fr-FR')}</span>
                    </div>
                    {transaction.processed_at && (
                      <div className="flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" />
                        <span>{t('admin.transactions.processed_at') || 'Traité le'} {new Date(transaction.processed_at).toLocaleDateString('fr-FR')}</span>
                      </div>
                    )}
                    {transaction.reference && (
                      <div className="flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        <span>{t('admin.transactions.reference') || 'Réf.'}: {transaction.reference}</span>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialog pour les détails */}
      {selectedTransaction && (
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('admin.transactions.transaction_details') || 'Détails de la transaction'} #{selectedTransaction.id}</DialogTitle>
              <DialogDescription>
                {t('admin.transactions.transaction_details_description') || 'Informations complètes sur la transaction'}
              </DialogDescription>
            </DialogHeader>
            
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.transactions.type_label') || 'Type'}</h4>
                  {getTypeBadge(selectedTransaction.type)}
                </div>
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.transactions.status') || 'Statut'}</h4>
                  {getStatusBadge(selectedTransaction.status)}
                </div>
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.transactions.amount') || 'Montant'}</h4>
                  <p className="text-lg font-bold">{formatAmount(selectedTransaction.amount, selectedTransaction.currency)}</p>
                </div>
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.transactions.currency') || 'Devise'}</h4>
                  <p>{selectedTransaction.currency}</p>
                </div>
              </div>

              {selectedTransaction.description && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.transactions.description') || 'Description'}</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedTransaction.description}</p>
                </div>
              )}

              {selectedTransaction.user && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.transactions.user') || 'Utilisateur'}</h4>
                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Avatar>
                        <AvatarImage src={selectedTransaction.user.avatar_url || undefined} />
                        <AvatarFallback>
                          {selectedTransaction.user.full_name?.[0] || selectedTransaction.user.username?.[0] || 'U'}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-medium">{selectedTransaction.user.full_name || selectedTransaction.user.username}</p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{selectedTransaction.user.email}</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {selectedTransaction.contest && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.transactions.contest') || 'Concours'}</h4>
                  <p className="text-sm">{selectedTransaction.contest.name}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                {selectedTransaction.payment_method && (
                  <div>
                    <h4 className="font-semibold mb-2">{t('admin.transactions.payment_method') || 'Méthode de paiement'}</h4>
                    <p className="text-sm">{selectedTransaction.payment_method}</p>
                  </div>
                )}
                {selectedTransaction.product_type && (
                  <div>
                    <h4 className="font-semibold mb-2">{t('admin.transactions.product_type') || 'Type de produit'}</h4>
                    <p className="text-sm">{selectedTransaction.product_type}</p>
                  </div>
                )}
                {selectedTransaction.reference && (
                  <div>
                    <h4 className="font-semibold mb-2">{t('admin.transactions.reference') || 'Référence'}</h4>
                    <p className="text-sm font-mono">{selectedTransaction.reference}</p>
                  </div>
                )}
                {selectedTransaction.order_id && (
                  <div>
                    <h4 className="font-semibold mb-2">{t('admin.transactions.order_id') || 'ID Commande'}</h4>
                    <p className="text-sm font-mono">{selectedTransaction.order_id}</p>
                  </div>
                )}
                {selectedTransaction.external_payment_id && (
                  <div>
                    <h4 className="font-semibold mb-2">{t('admin.transactions.external_payment_id') || 'ID Paiement Externe'}</h4>
                    <p className="text-sm font-mono">{selectedTransaction.external_payment_id}</p>
                  </div>
                )}
                {selectedTransaction.tx_hash && (
                  <div>
                    <h4 className="font-semibold mb-2">{t('admin.transactions.tx_hash') || 'Hash Transaction'}</h4>
                    <p className="text-sm font-mono break-all">{selectedTransaction.tx_hash}</p>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.transactions.created_at') || 'Créé le'}</h4>
                  <p className="text-sm">{new Date(selectedTransaction.created_at).toLocaleString('fr-FR')}</p>
                </div>
                {selectedTransaction.processed_at && (
                  <div>
                    <h4 className="font-semibold mb-2">{t('admin.transactions.processed_at') || 'Traité le'}</h4>
                    <p className="text-sm">{new Date(selectedTransaction.processed_at).toLocaleString('fr-FR')}</p>
                  </div>
                )}
                {selectedTransaction.validated_at && (
                  <div>
                    <h4 className="font-semibold mb-2">{t('admin.transactions.validated_at') || 'Validé le'}</h4>
                    <p className="text-sm">{new Date(selectedTransaction.validated_at).toLocaleString('fr-FR')}</p>
                  </div>
                )}
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
