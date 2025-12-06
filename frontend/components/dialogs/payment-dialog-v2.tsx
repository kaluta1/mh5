'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  CreditCard,
  Wallet,
  Building2,
  Bitcoin,
  Copy,
  Check,
  AlertCircle,
  Shield,
  Plus,
  Loader2,
  X,
  User,
  Trash2,
  Users,
  ChevronRight
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { paymentService, CryptoPaymentResponse, VerifiedUser, PaymentRecipient } from '@/services/payment-service'

interface PaymentMethod {
  id: string
  name: string
  icon: React.ReactNode
  category: 'crypto' | 'card' | 'bank'
  network?: string
}

interface Recipient {
  id: string
  usernameOrEmail: string
  verifiedUser: VerifiedUser | null
  productCode: 'kyc' | 'efm_membership'
  amount: number
  isVerifying: boolean
  error: string | null
}

const paymentMethods: PaymentMethod[] = [
  {
    id: 'usdtbsc',
    name: 'USDT (BNB Chain)',
    icon: <Wallet className="w-5 h-5 text-yellow-500" />,
    category: 'crypto',
    network: 'BNB Smart Chain (BEP20)'
  },
  {
    id: 'usdtsol',
    name: 'USDT (Solana)',
    icon: <Wallet className="w-5 h-5 text-purple-500" />,
    category: 'crypto',
    network: 'Solana'
  },
  {
    id: 'btc',
    name: 'Bitcoin',
    icon: <Bitcoin className="w-5 h-5 text-orange-500" />,
    category: 'crypto',
    network: 'Bitcoin'
  },
  {
    id: 'sol',
    name: 'Solana',
    icon: <Wallet className="w-5 h-5 text-green-500" />,
    category: 'crypto',
    network: 'Solana'
  },
  {
    id: 'card',
    name: 'Carte bancaire',
    icon: <CreditCard className="w-5 h-5 text-blue-500" />,
    category: 'card'
  },
  {
    id: 'bank',
    name: 'Virement bancaire',
    icon: <Building2 className="w-5 h-5 text-gray-500" />,
    category: 'bank'
  }
]

interface PaymentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialProductCode?: string
  onPaymentInitiated?: () => void
}

export function PaymentDialog({
  open,
  onOpenChange,
  initialProductCode = 'kyc',
  onPaymentInitiated
}: PaymentDialogProps) {
  const { t } = useLanguage()
  const { user } = useAuth()
  
  // Steps: 'recipients' | 'method' | 'payment' | 'success'
  const [step, setStep] = useState<'recipients' | 'method' | 'payment' | 'success'>('recipients')
  const [recipients, setRecipients] = useState<Recipient[]>([])
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [cryptoPayment, setCryptoPayment] = useState<CryptoPaymentResponse | null>(null)
  const [paymentError, setPaymentError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [includeMyself, setIncludeMyself] = useState(true)
  const [myselfProduct, setMyselfProduct] = useState<'kyc' | 'efm_membership'>(initialProductCode as 'kyc' | 'efm_membership')
  const [myselfAmount, setMyselfAmount] = useState(initialProductCode === 'kyc' ? 10 : 100)
  const [isCheckingPayment, setIsCheckingPayment] = useState(false)
  const [paymentConfirmed, setPaymentConfirmed] = useState(false)
  const [lastCheckTime, setLastCheckTime] = useState<Date | null>(null)
  
  // Ref for polling interval
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const POLLING_INTERVAL = 30000 // 30 seconds

  // Automatic check for polling (shows status messages)
  const autoCheckPaymentStatus = useCallback(async () => {
    if (!cryptoPayment?.deposit_id || paymentConfirmed) return
    
    try {
      const token = localStorage.getItem('access_token')
      if (!token) return
      
      const result = await paymentService.checkDepositStatus(token, cryptoPayment.deposit_id)
      setLastCheckTime(new Date())
      
      if (result.is_confirmed) {
        setPaymentConfirmed(true)
        setPaymentError(null)
        setStep('success')
        // Stop polling on success
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current)
          pollingIntervalRef.current = null
        }
      } else if (result.payment_status === 'waiting') {
        setPaymentError(t('payment.waiting_payment') || 'En attente de paiement...')
      } else if (result.payment_status === 'confirming') {
        setPaymentError(t('payment.confirming') || 'Paiement détecté, confirmation en cours...')
      } else if (result.payment_status === 'partially_paid') {
        setPaymentError(t('payment.partially_paid') || 'Paiement partiel reçu. Veuillez compléter le montant.')
      } else if (result.error) {
        setPaymentError(result.error)
      }
    } catch (error) {
      console.error('Auto check error:', error)
    }
  }, [cryptoPayment?.deposit_id, paymentConfirmed, t])

  // Start/stop polling when on payment step
  useEffect(() => {
    if (step === 'payment' && cryptoPayment?.deposit_id && !paymentConfirmed) {
      // Initial check after 10 seconds
      const initialTimeout = setTimeout(() => {
        autoCheckPaymentStatus()
      }, 10000)
      
      // Then check every 30 seconds
      pollingIntervalRef.current = setInterval(() => {
        autoCheckPaymentStatus()
      }, POLLING_INTERVAL)
      
      return () => {
        clearTimeout(initialTimeout)
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current)
          pollingIntervalRef.current = null
        }
      }
    }
    
    // Cleanup when leaving payment step
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }
    }
  }, [step, cryptoPayment?.deposit_id, paymentConfirmed, autoCheckPaymentStatus])

  // Generate unique ID
  const generateId = () => Math.random().toString(36).substr(2, 9)

  // Add new recipient (other user)
  const addRecipient = () => {
    setRecipients([...recipients, {
      id: generateId(),
      usernameOrEmail: '',
      verifiedUser: null,
      productCode: 'kyc',
      amount: 10,
      isVerifying: false,
      error: null
    }])
  }

  // Remove recipient
  const removeRecipient = (id: string) => {
    setRecipients(recipients.filter(r => r.id !== id))
  }

  // Update recipient field
  const updateRecipient = (id: string, field: keyof Recipient, value: any) => {
    setRecipients(recipients.map(r => {
      if (r.id !== id) return r
      
      const updated = { ...r, [field]: value }
      
      // Auto-set amount based on product
      if (field === 'productCode') {
        updated.amount = value === 'kyc' ? 10 : 100
      }
      
      // Clear verification when username changes
      if (field === 'usernameOrEmail') {
        updated.verifiedUser = null
        updated.error = null
      }
      
      return updated
    }))
  }

  // Verify user exists
  const verifyUser = async (id: string) => {
    const recipient = recipients.find(r => r.id === id)
    if (!recipient || !recipient.usernameOrEmail.trim()) return

    const token = localStorage.getItem('access_token')
    if (!token) return

    updateRecipient(id, 'isVerifying', true)
    updateRecipient(id, 'error', null)

    try {
      const user = await paymentService.verifyUser(token, recipient.usernameOrEmail.trim())
      setRecipients(prev => prev.map(r => 
        r.id === id ? { ...r, verifiedUser: user, isVerifying: false, error: null } : r
      ))
    } catch (error) {
      setRecipients(prev => prev.map(r => 
        r.id === id ? { ...r, verifiedUser: null, isVerifying: false, error: t('payment.user_not_found') || 'Utilisateur non trouvé' } : r
      ))
    }
  }

  // Calculate total (including myself if checked)
  const myselfTotal = includeMyself ? myselfAmount : 0
  const othersTotal = recipients.reduce((sum, r) => sum + r.amount, 0)
  const totalAmount = myselfTotal + othersTotal

  // Check if payment is valid
  const othersValid = recipients.every(r => r.verifiedUser !== null && r.amount > 0)
  const hasAtLeastOne = includeMyself || recipients.length > 0
  const allRecipientsValid = hasAtLeastOne && othersValid && 
    (!includeMyself || myselfAmount >= (myselfProduct === 'efm_membership' ? 100 : 10))

  // Copy to clipboard
  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  // Check payment status manually
  const checkPaymentStatus = async () => {
    if (!cryptoPayment?.deposit_id) return
    
    setIsCheckingPayment(true)
    setPaymentError(null)
    
    try {
      const token = localStorage.getItem('access_token')
      if (!token) {
        setPaymentError(t('common.login_required') || 'Veuillez vous connecter')
        return
      }
      
      const result = await paymentService.checkDepositStatus(token, cryptoPayment.deposit_id)
      
      if (result.is_confirmed) {
        setPaymentConfirmed(true)
        setStep('success')
        // onPaymentInitiated will be called when user clicks "Continue"
      } else if (result.payment_status === 'waiting' || result.payment_status === 'confirming') {
        setPaymentError(t('payment.waiting_confirmation') || 'Paiement en attente de confirmation...')
      } else if (result.error) {
        setPaymentError(result.error)
      } else {
        setPaymentError(t('payment.not_received') || 'Paiement non encore reçu. Veuillez réessayer.')
      }
    } catch (error) {
      setPaymentError(error instanceof Error ? error.message : 'Erreur lors de la vérification')
    } finally {
      setIsCheckingPayment(false)
    }
  }

  // Handle method selection and create payment
  const handleMethodSelect = async (methodId: string) => {
    setSelectedMethod(methodId)
    setPaymentError(null)

    const method = paymentMethods.find(m => m.id === methodId)
    
    if (method?.category === 'crypto') {
      setIsLoading(true)
      try {
        const token = localStorage.getItem('access_token')
        if (!token) {
          setPaymentError(t('common.login_required') || 'Veuillez vous connecter')
          setIsLoading(false)
          return
        }

        // Prepare recipients for API (include myself + others)
        const apiRecipients: PaymentRecipient[] = []
        
        // Add myself first if included
        if (includeMyself && user) {
          apiRecipients.push({
            username_or_email: user.username || user.email,
            product_code: myselfProduct,
            amount: myselfAmount
          })
        }
        
        // Add other recipients
        recipients.forEach(r => {
          if (r.verifiedUser) {
            apiRecipients.push({
              username_or_email: r.verifiedUser.username,
              product_code: r.productCode,
              amount: r.amount
            })
          }
        })

        const payment = await paymentService.createPayment(token, {
          amount: totalAmount,
          currency: 'usd',
          pay_currency: methodId,
          product_code: apiRecipients[0]?.product_code || 'kyc',
          recipients: apiRecipients
        })

        setCryptoPayment(payment)
        setStep('payment')
      } catch (error) {
        console.error('Payment creation error:', error)
        setPaymentError(error instanceof Error ? error.message : 'Erreur lors de la création du paiement')
      } finally {
        setIsLoading(false)
      }
    } else if (method?.category === 'card') {
      alert(t('payment.card_coming_soon') || 'Paiement par carte bientôt disponible')
    } else if (method?.category === 'bank') {
      setStep('payment')
    }
  }

  // Handle close with confirmation
  const handleClose = () => {
    // Allow direct close from success step (also trigger callback)
    if (step === 'success') {
      onPaymentInitiated?.()
      resetAndClose()
      return
    }
    if (step !== 'recipients' || recipients.length > 0) {
      setShowCloseConfirm(true)
    } else {
      resetAndClose()
    }
  }

  // Reset state and close
  const resetAndClose = () => {
    // Clear polling interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    
    setStep('recipients')
    setRecipients([])
    setSelectedMethod(null)
    setCryptoPayment(null)
    setPaymentError(null)
    setShowCloseConfirm(false)
    setIncludeMyself(true)
    setMyselfProduct(initialProductCode as 'kyc' | 'efm_membership')
    setMyselfAmount(initialProductCode === 'kyc' ? 10 : 100)
    setIsCheckingPayment(false)
    setPaymentConfirmed(false)
    setLastCheckTime(null)
    onOpenChange(false)
  }

  // Handle back
  const handleBack = () => {
    if (step === 'payment') {
      setStep('method')
      setCryptoPayment(null)
    } else if (step === 'method') {
      setStep('recipients')
      setSelectedMethod(null)
    }
  }

  // Get product name
  const getProductName = (code: string) => {
    return code === 'kyc' 
      ? (t('payment.kyc_verification') || 'Vérification KYC')
      : (t('payment.efm_membership') || 'Adhésion EFM')
  }

  return (
    <>
      <Dialog open={open} onOpenChange={() => handleClose()}>
        <DialogContent 
          className="sm:max-w-lg max-h-[90vh] overflow-y-auto"
          onPointerDownOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {step === 'success' ? (
                <Check className="w-5 h-5 text-green-500" />
              ) : (
                <Shield className="w-5 h-5 text-myfav-primary" />
              )}
              {step === 'recipients' && (t('payment.add_recipients') || 'Ajouter des bénéficiaires')}
              {step === 'method' && (t('payment.payment_method') || 'Méthode de paiement')}
              {step === 'payment' && (t('payment.payment_instructions') || 'Instructions de paiement')}
              {step === 'success' && (t('payment.success_title') || 'Paiement confirmé')}
            </DialogTitle>
            {step !== 'success' && (
              <DialogDescription>
                {step === 'recipients' && (t('payment.recipients_description') || 'Ajoutez les utilisateurs pour lesquels vous souhaitez payer')}
                {step === 'method' && (t('payment.method_description') || 'Choisissez votre méthode de paiement')}
                {step === 'payment' && (t('payment.instructions_description') || 'Envoyez le montant exact à l\'adresse indiquée')}
              </DialogDescription>
            )}
          </DialogHeader>

          {/* Step 1: Recipients */}
          {step === 'recipients' && (
            <div className="space-y-4 mt-4">
              {/* Current user section */}
              <div className={`p-4 rounded-xl border-2 transition-all ${includeMyself ? 'border-myfav-primary bg-myfav-primary/5' : 'border-gray-200 dark:border-gray-700'}`}>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeMyself}
                    onChange={(e) => setIncludeMyself(e.target.checked)}
                    className="w-5 h-5 rounded border-gray-300 text-myfav-primary focus:ring-myfav-primary"
                  />
                  <div className="flex items-center gap-2 flex-1">
                    <div className="w-10 h-10 rounded-full bg-myfav-primary/20 flex items-center justify-center">
                      <User className="w-5 h-5 text-myfav-primary" />
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">
                        {t('payment.pay_for_myself') || 'Payer pour moi'}
                      </p>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        @{user?.username || user?.email}
                      </p>
                    </div>
                  </div>
                </label>

                {includeMyself && (
                  <div className="grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <div>
                      <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">
                        {t('payment.product_type') || 'Produit'}
                      </label>
                      <Select
                        value={myselfProduct}
                        onValueChange={(value: 'kyc' | 'efm_membership') => {
                          setMyselfProduct(value)
                          setMyselfAmount(value === 'kyc' ? 10 : 100)
                        }}
                      >
                        <SelectTrigger className="bg-white dark:bg-gray-800">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="kyc">
                            <div className="flex items-center gap-2">
                              <Shield className="w-4 h-4 text-green-500" />
                              <span>KYC - 10 USD</span>
                            </div>
                          </SelectItem>
                          <SelectItem value="efm_membership">
                            <div className="flex items-center gap-2">
                              <Users className="w-4 h-4 text-blue-500" />
                              <span>EFM - Min 100 USD</span>
                            </div>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">
                        {t('payment.amount') || 'Montant'}
                      </label>
                      <div className="relative">
                        <Input
                          type="number"
                          min={myselfProduct === 'efm_membership' ? 100 : 10}
                          step={10}
                          value={myselfAmount}
                          onChange={(e) => setMyselfAmount(parseFloat(e.target.value) || 0)}
                          disabled={myselfProduct === 'kyc'}
                          className="pr-12 bg-white dark:bg-gray-800"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">USD</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Divider */}
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200 dark:border-gray-700"></div>
                </div>
                <div className="relative flex justify-center">
                  <span className="px-3 bg-white dark:bg-gray-900 text-sm text-gray-500">
                    {t('payment.pay_for_others') || 'Payer pour d\'autres'}
                  </span>
                </div>
              </div>

              {/* Other recipients list */}
              {recipients.map((recipient, index) => (
                <div key={recipient.id} className="p-4 border border-gray-200 dark:border-gray-700 rounded-xl space-y-3 bg-gray-50 dark:bg-gray-800/50">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
                        <Users className="w-4 h-4 text-gray-500" />
                      </div>
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        {t('payment.recipient') || 'Bénéficiaire'} #{index + 1}
                      </span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeRecipient(recipient.id)}
                      className="text-red-500 hover:text-red-700 hover:bg-red-50 h-8 w-8 p-0"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>

                  {/* Username/Email input */}
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <Input
                        placeholder={t('payment.username_or_email') || "Nom d'utilisateur ou email"}
                        value={recipient.usernameOrEmail}
                        onChange={(e) => updateRecipient(recipient.id, 'usernameOrEmail', e.target.value)}
                        onBlur={() => verifyUser(recipient.id)}
                        className={`bg-white dark:bg-gray-800 ${recipient.error ? 'border-red-500' : recipient.verifiedUser ? 'border-green-500' : ''}`}
                      />
                    </div>
                    {recipient.isVerifying && <Loader2 className="w-5 h-5 animate-spin text-gray-400 self-center" />}
                    {recipient.verifiedUser && <Check className="w-5 h-5 text-green-500 self-center" />}
                  </div>

                  {recipient.error && <p className="text-xs text-red-500">{recipient.error}</p>}

                  {recipient.verifiedUser && (
                    <div className="flex items-center gap-2 text-sm bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 p-2 rounded-lg">
                      <Check className="w-4 h-4" />
                      <span>{recipient.verifiedUser.display_name}</span>
                      <span className="text-xs opacity-70">(@{recipient.verifiedUser.username})</span>
                    </div>
                  )}

                  {/* Product selection */}
                  <div className="grid grid-cols-2 gap-3">
                    <Select
                      value={recipient.productCode}
                      onValueChange={(value) => updateRecipient(recipient.id, 'productCode', value)}
                    >
                      <SelectTrigger className="bg-white dark:bg-gray-800">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="kyc">KYC - 10 USD</SelectItem>
                        <SelectItem value="efm_membership">EFM - Min 100 USD</SelectItem>
                      </SelectContent>
                    </Select>
                    <div className="relative">
                      <Input
                        type="number"
                        min={recipient.productCode === 'efm_membership' ? 100 : 10}
                        value={recipient.amount}
                        onChange={(e) => updateRecipient(recipient.id, 'amount', parseFloat(e.target.value) || 0)}
                        disabled={recipient.productCode === 'kyc'}
                        className="pr-12 bg-white dark:bg-gray-800"
                      />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">USD</span>
                    </div>
                  </div>
                </div>
              ))}

              {/* Add recipient button */}
              <Button
                variant="outline"
                onClick={addRecipient}
                className="w-full border-dashed border-2 h-12 hover:border-myfav-primary hover:text-myfav-primary"
              >
                <Plus className="w-5 h-5 mr-2" />
                {t('payment.add_other_user') || 'Ajouter un autre utilisateur'}
              </Button>

              {/* Total */}
              {totalAmount > 0 && (
                <div className="flex items-center justify-between p-4 bg-gradient-to-r from-myfav-primary/10 to-myfav-primary/5 dark:from-myfav-primary/20 dark:to-myfav-primary/10 rounded-xl">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">{t('payment.total') || 'Total'}</p>
                    <p className="text-xs text-gray-500">
                      {(includeMyself ? 1 : 0) + recipients.length} {t('payment.recipients_count') || 'bénéficiaire(s)'}
                    </p>
                  </div>
                  <span className="text-3xl font-bold text-myfav-primary">
                    ${totalAmount.toFixed(2)}
                  </span>
                </div>
              )}

              {/* Continue button */}
              <div className="flex gap-3 pt-2">
                <Button variant="outline" onClick={handleClose} className="flex-1">
                  {t('common.cancel') || 'Annuler'}
                </Button>
                <Button
                  onClick={() => setStep('method')}
                  disabled={!allRecipientsValid}
                  className="flex-1 bg-myfav-primary hover:bg-myfav-primary/90 gap-2"
                >
                  {t('common.continue') || 'Continuer'}
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Payment Method */}
          {step === 'method' && (
            <div className="space-y-4 mt-4">
              {/* Summary */}
              <div className="p-3 bg-gray-100 dark:bg-gray-800 rounded-lg">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  {(includeMyself ? 1 : 0) + recipients.length} {t('payment.recipients_count') || 'bénéficiaire(s)'}
                </p>
                <p className="text-xl font-bold text-myfav-primary">
                  {totalAmount.toFixed(2)} USD
                </p>
              </div>

              {/* Loading */}
              {isLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-8 h-8 animate-spin text-myfav-primary" />
                  <span className="ml-3 text-gray-600 dark:text-gray-400">
                    {t('payment.creating_payment') || 'Création du paiement...'}
                  </span>
                </div>
              )}

              {/* Error */}
              {paymentError && (
                <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                  <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-red-700 dark:text-red-300">{paymentError}</p>
                </div>
              )}

              {/* Methods */}
              {!isLoading && (
                <>
                  <div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
                      {t('payment.cryptocurrencies') || 'Crypto-monnaies'}
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {paymentMethods.filter(m => m.category === 'crypto').map((method) => (
                        <button
                          key={method.id}
                          onClick={() => handleMethodSelect(method.id)}
                          disabled={isLoading}
                          className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-myfav-primary hover:bg-myfav-primary/5 transition-all text-left disabled:opacity-50"
                        >
                          {method.icon}
                          <span className="text-sm font-medium text-gray-900 dark:text-white">{method.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
                      {t('payment.other_methods') || 'Autres méthodes'}
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {paymentMethods.filter(m => m.category !== 'crypto').map((method) => (
                        <button
                          key={method.id}
                          onClick={() => handleMethodSelect(method.id)}
                          disabled={isLoading}
                          className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-myfav-primary hover:bg-myfav-primary/5 transition-all text-left disabled:opacity-50"
                        >
                          {method.icon}
                          <span className="text-sm font-medium text-gray-900 dark:text-white">{method.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Actions */}
              <div className="flex gap-3 pt-2">
                <Button variant="outline" onClick={handleBack} className="flex-1">
                  {t('common.back') || 'Retour'}
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Payment Instructions */}
          {step === 'payment' && cryptoPayment && (
            <div className="space-y-4 mt-4">
              {/* QR Code */}
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <QRCodeSVG 
                  value={cryptoPayment.pay_address}
                  size={180}
                  level="H"
                  includeMargin={true}
                />
              </div>

              {/* Amount */}
              <div className="bg-myfav-primary/10 dark:bg-myfav-primary/20 rounded-lg p-4 text-center">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                  {t('payment.amount_to_send') || 'Montant à envoyer'}
                </p>
                <p className="text-3xl font-bold text-myfav-primary">
                  {cryptoPayment.pay_amount} {cryptoPayment.pay_currency.toUpperCase()}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  ≈ {cryptoPayment.price_amount.toFixed(2)} {cryptoPayment.price_currency.toUpperCase()}
                </p>
              </div>

              {/* Address */}
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('payment.receiving_address') || 'Adresse de réception'}
                </p>
                <div className="flex items-center gap-2 p-3 bg-gray-100 dark:bg-gray-800 rounded-lg">
                  <code className="text-xs flex-1 break-all text-gray-900 dark:text-white font-mono">
                    {cryptoPayment.pay_address}
                  </code>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(cryptoPayment.pay_address)}
                    className="flex-shrink-0"
                  >
                    {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                  </Button>
                </div>
              </div>

              {/* Order ID */}
              <div className="text-center text-xs text-gray-500 dark:text-gray-400">
                {t('payment.order_id') || 'Référence'}: {cryptoPayment.order_id}
              </div>

              {/* Warning */}
              <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-red-700 dark:text-red-300">
                  {t('payment.network_warning') || "Assurez-vous d'envoyer le montant exact sur le bon réseau. Les erreurs peuvent entraîner une perte de fonds."}
                </p>
              </div>

              {/* Auto-check indicator */}
              <div className="flex items-center justify-center gap-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  {t('payment.auto_checking') || 'Vérification automatique active'}
                  {lastCheckTime && (
                    <span className="ml-1 text-blue-500">
                      ({t('payment.last_check') || 'Dernière vérif.'}: {lastCheckTime.toLocaleTimeString()})
                    </span>
                  )}
                </p>
              </div>

              {/* Status message */}
              {paymentError && (
                <div className={`flex items-start gap-2 p-3 rounded-lg ${
                  paymentError.includes('détecté') || paymentError.includes('detected') || paymentError.includes('detectado') || paymentError.includes('erkannt')
                    ? 'bg-green-50 dark:bg-green-900/20'
                    : paymentError.includes('attente') || paymentError.includes('waiting') || paymentError.includes('Esperando') || paymentError.includes('Warten')
                    ? 'bg-blue-50 dark:bg-blue-900/20'
                    : 'bg-yellow-50 dark:bg-yellow-900/20'
                }`}>
                  {paymentError.includes('détecté') || paymentError.includes('detected') || paymentError.includes('detectado') || paymentError.includes('erkannt') ? (
                    <Check className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                  ) : paymentError.includes('attente') || paymentError.includes('waiting') || paymentError.includes('Esperando') || paymentError.includes('Warten') ? (
                    <Loader2 className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0 animate-spin" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-yellow-500 mt-0.5 flex-shrink-0" />
                  )}
                  <p className={`text-sm ${
                    paymentError.includes('détecté') || paymentError.includes('detected') || paymentError.includes('detectado') || paymentError.includes('erkannt')
                      ? 'text-green-700 dark:text-green-300'
                      : paymentError.includes('attente') || paymentError.includes('waiting') || paymentError.includes('Esperando') || paymentError.includes('Warten')
                      ? 'text-blue-700 dark:text-blue-300'
                      : 'text-yellow-700 dark:text-yellow-300'
                  }`}>{paymentError}</p>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3 pt-2">
                <Button variant="outline" onClick={handleBack} className="flex-1" disabled={isCheckingPayment}>
                  {t('common.back') || 'Retour'}
                </Button>
                <Button
                  onClick={checkPaymentStatus}
                  disabled={isCheckingPayment}
                  className="flex-1 bg-myfav-primary hover:bg-myfav-primary/90"
                >
                  {isCheckingPayment ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      {t('payment.checking') || 'Vérification...'}
                    </>
                  ) : (
                    t('payment.payment_done') || "J'ai effectué le paiement"
                  )}
                </Button>
              </div>
            </div>
          )}

          {/* Step 4: Success */}
          {step === 'success' && (
            <div className="space-y-6 mt-4 py-8">
              {/* Success Icon */}
              <div className="flex justify-center">
                <div className="w-20 h-20 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                  <Check className="w-10 h-10 text-green-500" />
                </div>
              </div>

              {/* Success Message */}
              <div className="text-center">
                <h3 className="text-xl font-bold text-green-600 dark:text-green-400 mb-2">
                  {t('payment.success_title') || 'Paiement confirmé !'}
                </h3>
                <p className="text-gray-600 dark:text-gray-400">
                  {t('payment.success_description') || 'Votre paiement a été reçu et confirmé. Vous pouvez maintenant continuer.'}
                </p>
              </div>

              {/* Amount Summary */}
              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 text-center">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                  {t('payment.amount_paid') || 'Montant payé'}
                </p>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  ${totalAmount.toFixed(2)} USD
                </p>
              </div>

              {/* Close Button */}
              <Button
                onClick={() => {
                  onPaymentInitiated?.()
                  resetAndClose()
                }}
                className="w-full bg-green-600 hover:bg-green-700"
              >
                {t('common.continue') || 'Continuer'}
              </Button>
            </div>
          )}

        </DialogContent>
      </Dialog>

      {/* Close confirmation dialog */}
      <AlertDialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('payment.confirm_close_title') || 'Fermer le paiement ?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('payment.confirm_close_description') || 'Votre progression sera perdue. Êtes-vous sûr de vouloir fermer ?'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('common.cancel') || 'Annuler'}
            </AlertDialogCancel>
            <AlertDialogAction onClick={resetAndClose}>
              {t('common.confirm') || 'Confirmer'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
