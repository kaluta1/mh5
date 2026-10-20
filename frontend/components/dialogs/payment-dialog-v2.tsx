'use client'

import { useState, useEffect, useRef } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { logger } from '@/lib/logger'
import { kycService } from '@/services/kyc-service'
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
  ChevronRight,
  Crown,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { paymentService, PaymentResponse, VerifiedUser, PaymentRecipient } from '@/services/payment-service'
import { isFinalState, isSoncoPay, paymentStateText, safeCheckoutUrl, type CheckoutGateway } from '@/lib/payment-gateway'

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
  productCode: 'kyc' | 'mfm_membership' | 'annual_membership'
  amount: number
  isVerifying: boolean
  error: string | null
}

// Until the server's member KYC fee has arrived (the server refuses any other amount).
const DEFAULT_KYC_PRICE_USD = 10

const PREFERRED_PAY_CURRENCIES = ['usdtbsc', 'usdterc20', 'usdttrc20', 'usdt', 'btc', 'eth']

function formatPayCurrencyLabel(code: string): string {
  const labels: Record<string, string> = {
    usdtbsc: 'USDT (BSC / BEP20)',
    usdterc20: 'USDT (Ethereum / ERC20)',
    usdttrc20: 'USDT (Tron / TRC20)',
    usdt: 'USDT',
    btc: 'Bitcoin',
    eth: 'Ethereum',
  }
  return labels[code.toLowerCase()] || code.toUpperCase()
}

function sortPayCurrencies(currencies: string[]): string[] {
  const lower = currencies.map((c) => c.toLowerCase())
  const preferred = PREFERRED_PAY_CURRENCIES.filter((c) => lower.includes(c))
  const rest = lower.filter((c) => !PREFERRED_PAY_CURRENCIES.includes(c)).sort()
  return [...preferred, ...rest]
}

const getPaymentMethods = (t: (key: string) => string | undefined): PaymentMethod[] => [
  {
    id: 'crypto',
    name: t('payment.crypto_nowpayments') || 'USDT (BEP20)',
    icon: <Bitcoin className="w-5 h-5 text-orange-500" />,
    category: 'crypto',
    network: 'BNB Smart Chain (BSC)'
  },
  {
    id: 'card',
    name: t('payment.card') || 'Carte bancaire',
    icon: <CreditCard className="w-5 h-5 text-blue-500" />,
    category: 'card'
  },
  {
    id: 'bank',
    name: t('payment.bank_transfer') || 'Virement bancaire',
    icon: <Building2 className="w-5 h-5 text-gray-500" />,
    category: 'bank'
  }
]

interface PaymentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialProductCode?: string
  /** Fires once after NOWPayments confirms payment (may be async). */
  onPaymentInitiated?: () => void | Promise<void>
}

export function PaymentDialog({
  open,
  onOpenChange,
  initialProductCode = 'kyc',
  onPaymentInitiated
}: PaymentDialogProps) {
  const { t } = useLanguage()
  const { user } = useAuth()
  
  // Get payment methods with translations
  const paymentMethods = getPaymentMethods(t)
  
  // Ref for polling interval
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const paymentIdempotencyKeyRef = useRef<string | null>(null)
  
  // Steps: 'recipients' | 'method' | 'payment' | 'success'
  const [step, setStep] = useState<'recipients' | 'method' | 'payment' | 'success'>('recipients')
  const [recipients, setRecipients] = useState<Recipient[]>([])
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [payment, setPayment] = useState<PaymentResponse | null>(null)
  const [paymentError, setPaymentError] = useState<string | null>(null)
  const [isCheckingPayment, setIsCheckingPayment] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  
  const [copied, setCopied] = useState(false)
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [includeMyself, setIncludeMyself] = useState(true)
  const [myselfProduct, setMyselfProduct] = useState<'kyc' | 'mfm_membership' | 'annual_membership'>(initialProductCode as 'kyc' | 'mfm_membership' | 'annual_membership')
  // The member KYC fee is set by an administrator; the server's figure replaces the default.
  const [kycPriceUsd, setKycPriceUsd] = useState(DEFAULT_KYC_PRICE_USD)
  const [myselfAmount, setMyselfAmount] = useState(
    initialProductCode === 'kyc' ? kycPriceUsd : 
    initialProductCode === 'annual_membership' ? 50 : 100
  )
  const myselfProductRef = useRef(myselfProduct)
  myselfProductRef.current = myselfProduct
  const [paymentConfirmed, setPaymentConfirmed] = useState(false)
  const [payCurrencies, setPayCurrencies] = useState<string[]>(['usdtbsc'])
  const [loadingCurrencies, setLoadingCurrencies] = useState(false)
  // The gateway of a NEW payment, decided by the server (NOWPayments unless SoncoPay is the ready default).
  const [gateway, setGateway] = useState<CheckoutGateway>('nowpayments')

  useEffect(() => {
    if (!open) return
    const token = localStorage.getItem('access_token')
    if (!token) return
    let cancelled = false
    void paymentService.getCheckoutGateway(token).then((g) => { if (!cancelled) setGateway(g) })
    return () => { cancelled = true }
  }, [open])

  useEffect(() => {
    if (!open) return
    const token = localStorage.getItem('access_token')
    if (!token) return
    let cancelled = false
    void kycService.getKycFee(token).then((fee) => {
      if (cancelled || !fee || fee.is_free) return
      setKycPriceUsd(fee.amount)
      setMyselfAmount((current) => (myselfProductRef.current === 'kyc' ? fee.amount : current))
      setRecipients((rows) => rows.map((r) => (r.productCode === 'kyc' ? { ...r, amount: fee.amount } : r)))
    })
    return () => { cancelled = true }
  }, [open])

  // Poll NOWPayments while on payment step
  useEffect(() => {
    if (!open || step !== 'payment' || !payment?.deposit_id || paymentConfirmed) {
      return
    }

    const token = localStorage.getItem('access_token')
    if (!token) return

    const poll = async () => {
      try {
        const status = await paymentService.getPaymentStatus(token, payment.deposit_id)
        if (status.is_confirmed) {
          setPaymentConfirmed(true)
          setStep('success')
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
          try {
            await Promise.resolve(onPaymentInitiated?.())
          } catch (callbackErr) {
            logger.error('onPaymentInitiated error', callbackErr)
          }
        } else if (status.provider === 'soncopay') {
          setStatusMessage(paymentStateText(status.payment_state))
          if (isFinalState(status.payment_state) && pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)                // expired/failed: nothing more will happen
            pollingIntervalRef.current = null
          }
        } else if (status.payment_status === 'confirming') {
          setStatusMessage(t('payment.confirming') || 'Payment detected, confirming...')
        } else if (status.payment_status === 'partially_paid') {
          setStatusMessage(t('payment.partially_paid') || 'Partial payment received')
        }
      } catch (err) {
        logger.error('Payment polling error', err)
      }
    }

    poll()
    pollingIntervalRef.current = setInterval(poll, 30000)
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }
    }
  }, [open, step, payment?.deposit_id, paymentConfirmed, onPaymentInitiated, t])

  // Load NOWPayments pay currencies on method step (SoncoPay offers its methods on its own page)
  useEffect(() => {
    if (!open || step !== 'method' || gateway === 'soncopay') return

    const token = localStorage.getItem('access_token')
    if (!token) return

    let cancelled = false
    setLoadingCurrencies(true)
    paymentService
      .getAvailableCurrencies(token)
      .then((all) => {
        if (cancelled) return
        const usdtFirst = all.filter((c) => c.toLowerCase().includes('usdt'))
        const sorted = sortPayCurrencies(usdtFirst.length ? usdtFirst : all)
        setPayCurrencies(sorted.length ? sorted : ['usdtbsc'])
      })
      .catch((err) => {
        logger.error('Failed to load pay currencies', err)
        if (!cancelled) setPayCurrencies(['usdtbsc'])
      })
      .finally(() => {
        if (!cancelled) setLoadingCurrencies(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, step, gateway])

  const checkPaymentNow = async () => {
    if (!payment?.deposit_id) return
    const token = localStorage.getItem('access_token')
    if (!token) return

    setIsCheckingPayment(true)
    setPaymentError(null)
    try {
      const status = await paymentService.syncPayment(token, payment.deposit_id)
      if (status.is_confirmed) {
        setPaymentConfirmed(true)
        setStep('success')
        try {
          await Promise.resolve(onPaymentInitiated?.())
        } catch (callbackErr) {
          logger.error('onPaymentInitiated error', callbackErr)
        }
      } else if (status.provider === 'soncopay') {
        setStatusMessage(paymentStateText(status.payment_state))
      } else {
        setStatusMessage(
          status.payment_status === 'waiting'
            ? (t('payment.waiting_payment') || 'Waiting for payment...')
            : (t('payment.confirming') || 'Checking payment status...')
        )
      }
    } catch (error) {
      setPaymentError(error instanceof Error ? error.message : 'Failed to check payment')
    } finally {
      setIsCheckingPayment(false)
    }
  }

  // Generate unique ID
  const generateId = () => Math.random().toString(36).substr(2, 9)

  // Add new recipient (other user)
  const addRecipient = () => {
    setRecipients([...recipients, {
      id: generateId(),
      usernameOrEmail: '',
      verifiedUser: null,
      productCode: 'kyc',
      amount: kycPriceUsd,
      isVerifying: false,
      error: null
    }])
  }

  // Remove recipient
  const removeRecipient = (id: string) => {
    setRecipients(recipients.filter(r => r.id !== id))
  }

  // Update recipient field
  const updateRecipient = (id: string, field: keyof Recipient, value: string | number | boolean | null) => {
    setRecipients(recipients.map(r => {
      if (r.id !== id) return r
      
      const updated = { ...r, [field]: value }
      
      // Auto-set amount based on product
      if (field === 'productCode') {
        updated.amount = value === 'kyc' ? kycPriceUsd : value === 'annual_membership' ? 50 : 100
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
        r.id === id ? { ...r, verifiedUser: null, isVerifying: false, error: t('payment.user_not_found') || 'User not found' } : r
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
    (!includeMyself || myselfAmount >= (myselfProduct === 'mfm_membership' ? 100 : myselfProduct === 'annual_membership' ? 50 : kycPriceUsd))

  // Copy to clipboard
  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      logger.error('Failed to copy to clipboard', err)
    }
  }


  // Handle method selection and create payment
  const handleMethodSelect = async (methodId: string, payCurrency = 'usdtbsc') => {
    if (isLoading) return
    setSelectedMethod(methodId)
    setPaymentError(null)

    const method = paymentMethods.find((m) => m.id === methodId)
    if (method?.category === 'card') {
      alert(t('payment.card_coming_soon') || 'Card payments coming soon')
      return
    }
    if (method?.category === 'bank') {
      alert(t('payment.bank_coming_soon') || 'Bank transfer coming soon')
      return
    }

    setIsLoading(true)
    try {
      const token = localStorage.getItem('access_token')
      if (!token) {
        setPaymentError(t('common.login_required') || 'Login Required')
        return
      }

      const apiRecipients: PaymentRecipient[] = []

      if (includeMyself && user) {
        apiRecipients.push({
          username_or_email: user.username || user.email,
          product_code: myselfProduct,
          amount: myselfAmount,
        })
      }

      recipients.forEach((r) => {
        if (r.verifiedUser) {
          apiRecipients.push({
            username_or_email: r.verifiedUser.username,
            product_code: r.productCode,
            amount: r.amount,
          })
        }
      })

      if (!paymentIdempotencyKeyRef.current) {
        paymentIdempotencyKeyRef.current = crypto.randomUUID()
      }
      const paymentOrder = await paymentService.createPayment(
        token,
        {
          amount: totalAmount,
          currency: 'usd',
          product_code: apiRecipients[0]?.product_code || 'kyc',
          // SoncoPay: the member picks crypto, mobile money or card on SoncoPay's own page.
          pay_currency: gateway === 'soncopay' ? undefined : payCurrency,
          recipients: apiRecipients,
        },
        paymentIdempotencyKeyRef.current
      )

      setPayment(paymentOrder)
      setStep('payment')
    } catch (error) {
      logger.error('Payment creation error', error)
      setPaymentError(error instanceof Error ? error.message : 'Error creating the payment')
    } finally {
      setIsLoading(false)
    }
  }

  // Handle close with confirmation
  const handleClose = () => {
    // Allow direct close from success step (also trigger callback)
    if (step === 'success') {
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
    paymentIdempotencyKeyRef.current = null
    // Clear polling interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    
    setStep('recipients')
    setRecipients([])
    setSelectedMethod(null)
    setPayment(null)
    setPaymentError(null)
    setStatusMessage(null)
    setIsCheckingPayment(false)
    setPaymentConfirmed(false)
    setShowCloseConfirm(false)
    setIncludeMyself(true)
    setMyselfProduct(initialProductCode as 'kyc' | 'mfm_membership' | 'annual_membership')
    setMyselfAmount(
      initialProductCode === 'kyc' ? kycPriceUsd : 
      initialProductCode === 'annual_membership' ? 50 : 100
    )
    setPaymentConfirmed(false)
    setPayCurrencies(['usdtbsc'])
    setLoadingCurrencies(false)
    onOpenChange(false)
  }

  // Handle back
  const handleBack = () => {
    if (step === 'payment') {
      setStep('method')
      setPayment(null)
    } else if (step === 'method') {
      setStep('recipients')
      setSelectedMethod(null)
    }
  }

  // Get product name
  const getProductName = (code: string) => {
    switch (code) {
      case 'kyc':
        return t('payment.kyc_verification') || 'KYC Service'
      case 'mfm_membership':
        return t('payment.mfm_membership') || 'MFM'
      case 'annual_membership':
        return t('payment.annual_membership') || 'Annual Membership'
      default:
        return code
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={() => handleClose()}>
        <DialogContent 
          className="mx-auto w-[calc(100vw-1rem)] max-w-[calc(100vw-1rem)] sm:max-w-xl max-h-[90vh] overflow-x-hidden overflow-y-auto p-0"
          onPointerDownOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
        >
          {/* Header */}
          <div className="border-b border-gray-100 dark:border-gray-800 p-4 pb-4 sm:p-5 sm:pb-4">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-3 text-lg font-semibold text-gray-900 dark:text-white">
                {step === 'success' ? (
                  <div className="w-9 h-9 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                    <CheckCircle2 className="w-5 h-5 text-green-600" />
                  </div>
                ) : (
                  <div className="w-9 h-9 rounded-lg bg-myhigh5-primary/10 flex items-center justify-center">
                    <CreditCard className="w-5 h-5 text-myhigh5-primary" />
                  </div>
                )}
                {step === 'recipients' && (t('payment.buy_services') || 'Acheter des services')}
                {step === 'method' && (t('payment.payment_method') || 'Payment Method')}
                {step === 'payment' && (t('payment.payment_instructions') || 'Payment instructions')}
                {step === 'success' && (t('payment.success_title') || 'Payment confirmed!')}
              </DialogTitle>
              {step !== 'success' && (
                <DialogDescription className="mt-1 text-sm">
                  {step === 'recipients' && (t('payment.recipients_description') || 'Select the services you want to buy')}
                  {step === 'method' && (t('payment.method_description') || 'Choose your preferred payment method')}
                  {step === 'payment' && (t('payment.instructions_description') || 'Follow the instructions below to complete your payment.')}
                </DialogDescription>
              )}
            </DialogHeader>
            
            {/* Step indicator */}
            {step !== 'success' && (
              <div className="flex items-center justify-center gap-1 mt-4">
                {['recipients', 'method', 'payment'].map((s, i) => (
                  <div key={s} className="flex items-center">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all ${
                      step === s 
                        ? 'bg-myhigh5-primary text-white' 
                        : ['recipients', 'method', 'payment'].indexOf(step) > i
                          ? 'bg-myhigh5-secondary text-white'
                          : 'bg-gray-100 dark:bg-gray-800 text-gray-400'
                    }`}>
                      {['recipients', 'method', 'payment'].indexOf(step) > i ? (
                        <Check className="w-3.5 h-3.5" />
                      ) : (
                        i + 1
                      )}
                    </div>
                    {i < 2 && (
                      <div className={`w-6 h-0.5 mx-1 sm:w-10 ${
                        ['recipients', 'method', 'payment'].indexOf(step) > i
                          ? 'bg-myhigh5-secondary'
                          : 'bg-gray-200 dark:bg-gray-700'
                      }`} />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
          
          <div className="min-w-0 overflow-x-hidden p-4 sm:p-5">

          {/* Step 1: Recipients */}
          {step === 'recipients' && (
            <div className="space-y-4">
              {/* Section header */}
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('payment.select_for_myself') || 'For myself'} <span className="text-gray-400 font-normal">({t('common.optional') || 'optionnel'})</span>
                </p>
                {includeMyself && (
                  <button 
                    onClick={() => setIncludeMyself(false)}
                    className="text-xs text-gray-500 hover:text-red-500 transition-colors"
                  >
                    {t('common.clear') || 'Effacer'}
                  </button>
                )}
              </div>

              {/* Service cards */}
              <div className="space-y-2">
                {/* KYC Card */}
                <button
                  onClick={() => {
                    if (includeMyself && myselfProduct === 'kyc') {
                      setIncludeMyself(false)
                    } else {
                      setIncludeMyself(true)
                      setMyselfProduct('kyc')
                      setMyselfAmount(kycPriceUsd)
                    }
                  }}
                  className={`relative w-full p-3 rounded-lg border transition-all text-left ${
                    includeMyself && myselfProduct === 'kyc'
                      ? 'border-myhigh5-primary bg-myhigh5-primary/5'
                      : 'border-gray-200 dark:border-gray-700 hover:border-myhigh5-primary/50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                      includeMyself && myselfProduct === 'kyc'
                        ? 'border-myhigh5-primary bg-myhigh5-primary'
                        : 'border-gray-300 dark:border-gray-600'
                    }`}>
                      {includeMyself && myselfProduct === 'kyc' && (
                        <Check className="w-3 h-3 text-white" />
                      )}
                    </div>
                    <div className="w-8 h-8 rounded-lg bg-myhigh5-primary/10 flex items-center justify-center">
                      <Shield className="w-4 h-4 text-myhigh5-primary" />
                    </div>
                    <div className="flex-1">
                      <h4 className="text-sm font-medium text-gray-900 dark:text-white">KYC Service</h4>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {t('payment.kyc_description') || 'Identity verification'}
                      </p>
                    </div>
                    <span className="text-sm font-bold text-myhigh5-primary">${kycPriceUsd}</span>
                  </div>
                </button>

                {/* Annual Membership Card */}
                <button
                  onClick={() => {
                    if (includeMyself && myselfProduct === 'annual_membership') {
                      setIncludeMyself(false)
                    } else {
                      setIncludeMyself(true)
                      setMyselfProduct('annual_membership')
                      setMyselfAmount(50)
                    }
                  }}
                  className={`relative w-full p-3 rounded-lg border transition-all text-left ${
                    includeMyself && myselfProduct === 'annual_membership'
                      ? 'border-myhigh5-primary bg-myhigh5-primary/5'
                      : 'border-gray-200 dark:border-gray-700 hover:border-myhigh5-primary/50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                      includeMyself && myselfProduct === 'annual_membership'
                        ? 'border-myhigh5-primary bg-myhigh5-primary'
                        : 'border-gray-300 dark:border-gray-600'
                    }`}>
                      {includeMyself && myselfProduct === 'annual_membership' && (
                        <Check className="w-3 h-3 text-white" />
                      )}
                    </div>
                    <div className="w-8 h-8 rounded-lg bg-myhigh5-primary/10 flex items-center justify-center">
                      <Calendar className="w-4 h-4 text-myhigh5-primary" />
                    </div>
                    <div className="flex-1">
                      <h4 className="text-sm font-medium text-gray-900 dark:text-white">Annual Membership</h4>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {t('payment.annual_description') || 'Renouvellement FM'}
                      </p>
                    </div>
                    <span className="text-sm font-bold text-myhigh5-primary">$50</span>
                  </div>
                </button>
              </div>

              {/* Divider */}
              <div className="relative py-3">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200 dark:border-gray-700"></div>
                </div>
                <div className="relative flex justify-center">
                  <span className="px-3 bg-white dark:bg-gray-900 text-xs text-gray-400 uppercase tracking-wide">
                    {t('payment.pay_for_others') || 'Or pay for others'}
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
                        {t('payment.recipient') || 'Recipient'} #{index + 1}
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
                        placeholder={t('payment.username_or_email') || 'Username or email'}
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
                    <div className="flex min-w-0 items-center gap-2 text-sm bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 p-2 rounded-lg">
                      <Check className="w-4 h-4" />
                      <span className="min-w-0 break-words">{recipient.verifiedUser.display_name}</span>
                      <span className="min-w-0 break-all text-xs opacity-70">(@{recipient.verifiedUser.username})</span>
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
                        <SelectItem value="kyc">KYC Service - {kycPriceUsd} USD</SelectItem>
                        <SelectItem value="annual_membership">Annual Membership - 50 USD</SelectItem>
                      </SelectContent>
                    </Select>
                    <div className="relative">
                      <Input
                        type="number"
                        min={
                          recipient.productCode === 'mfm_membership' ? 100 : 
                          recipient.productCode === 'annual_membership' ? 50 : kycPriceUsd
                        }
                        value={recipient.amount}
                        onChange={(e) => updateRecipient(recipient.id, 'amount', parseFloat(e.target.value) || 0)}
                        disabled={true}
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
                disabled
                title="Third-party purchases require item-level payer and beneficiary accounting"
                className="w-full border-dashed border-2 h-12 hover:border-myhigh5-primary hover:text-myhigh5-primary"
              >
                <Plus className="w-5 h-5 mr-2" />
                {t('payment.add_other_user_unavailable') || 'Third-party purchases temporarily unavailable'}
              </Button>

              {/* Total */}
              {totalAmount > 0 && (
                <div className="flex items-center justify-between p-4 bg-gradient-to-r from-myhigh5-primary/10 to-myhigh5-primary/5 dark:from-myhigh5-primary/20 dark:to-myhigh5-primary/10 rounded-xl">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">{t('payment.total') || 'Total'}</p>
                    <p className="text-xs text-gray-500">
                      {(includeMyself ? 1 : 0) + recipients.length} {t('payment.recipients_count') || 'service(s)'}
                    </p>
                  </div>
                  <span className="text-3xl font-bold text-myhigh5-primary">
                    ${totalAmount.toFixed(2)}
                  </span>
                </div>
              )}

              {/* Continue button */}
              <div className="flex gap-3 pt-2">
                <Button variant="outline" onClick={handleClose} className="flex-1">
                  {t('common.cancel') || 'Cancel'}
                </Button>
                <Button
                  onClick={() => setStep('method')}
                  disabled={!allRecipientsValid}
                  className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary/90 gap-2"
                >
                  {t('common.continue') || 'Continuer'}
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Payment Method */}
          {step === 'method' && (
            <div className="space-y-4">
              {/* Summary Card */}
              <div className="bg-myhigh5-primary/5 dark:bg-myhigh5-primary/10 rounded-xl p-4 border border-myhigh5-primary/20">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t('payment.total_to_pay') || 'Total to pay'}
                    </p>
                    <p className="text-xs text-gray-500">
                      {(includeMyself ? 1 : 0) + recipients.length} {t('payment.recipients_count') || 'service(s)'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold text-myhigh5-primary">
                      ${totalAmount.toFixed(2)} USD
                    </p>
                  </div>
                </div>
              </div>

              {/* Loading */}
              {isLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-8 h-8 animate-spin text-myhigh5-primary" />
                  <span className="ml-3 text-gray-600 dark:text-gray-400">
                    {t('payment.creating_payment') || 'Creating Payment'}
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

              {/* SoncoPay: one choice; the methods are offered on SoncoPay's secure page */}
              {!isLoading && gateway === 'soncopay' && (
                <button
                  data-testid="pay-with-soncopay"
                  onClick={() => handleMethodSelect('soncopay')}
                  disabled={isLoading}
                  className="w-full flex items-center gap-3 p-4 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-myhigh5-primary hover:bg-myhigh5-primary/5 transition-all text-left disabled:opacity-50"
                >
                  <div className="w-9 h-9 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                    <Shield className="w-5 h-5 text-myhigh5-primary" />
                  </div>
                  <span>
                    <span className="block text-sm font-medium text-gray-900 dark:text-white">
                      {t('payment.pay_with_soncopay') || 'Pay with SoncoPay'}
                    </span>
                    <span className="block text-xs text-gray-500 dark:text-gray-400">
                      {t('payment.soncopay_methods') || 'Crypto, mobile money or card, on the secure SoncoPay page'}
                    </span>
                  </span>
                </button>
              )}

              {/* Methods */}
              {!isLoading && gateway !== 'soncopay' && (
                <>
                  <div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide font-medium">
                      {t('payment.cryptocurrencies') || 'Crypto-monnaies'}
                    </p>
                    {loadingCurrencies ? (
                      <div className="flex items-center justify-center py-6">
                        <Loader2 className="w-6 h-6 animate-spin text-myhigh5-primary" />
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {payCurrencies.map((currency) => (
                          <button
                            key={currency}
                            onClick={() => handleMethodSelect('crypto', currency)}
                            disabled={isLoading}
                            className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-myhigh5-primary hover:bg-myhigh5-primary/5 transition-all text-left disabled:opacity-50"
                          >
                            <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                              <Bitcoin className="w-5 h-5 text-orange-500" />
                            </div>
                            <span className="text-sm font-medium text-gray-900 dark:text-white">
                              {formatPayCurrencyLabel(currency)}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide font-medium">
                      {t('payment.other_methods') || 'Other Methods'}
                    </p>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {paymentMethods.filter(m => m.category !== 'crypto').map((method) => (
                        <button
                          key={method.id}
                          onClick={() => handleMethodSelect(method.id)}
                          disabled={true}
                          className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 text-left opacity-50 cursor-not-allowed relative"
                        >
                          <div className="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                            {method.icon}
                          </div>
                          <span className="text-sm font-medium text-gray-900 dark:text-white">{method.name}</span>
                          <span className="absolute top-1 right-1 text-[10px] bg-gray-200 dark:bg-gray-700 text-gray-500 px-1.5 py-0.5 rounded">
                            {t('common.coming_soon') || 'Coming Soon'}
                          </span>
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

          {/* Step 3: SoncoPay hosted checkout */}
          {step === 'payment' && payment && isSoncoPay(payment) && (
            <div className="space-y-4" data-testid="soncopay-payment-step">
              <div className="bg-myhigh5-primary/5 dark:bg-myhigh5-primary/10 rounded-xl p-4 text-center border border-myhigh5-primary/20">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                  {t('payment.amount_to_pay') || 'Amount to pay'}
                </p>
                <p className="text-2xl font-bold text-myhigh5-primary">
                  ${payment.price_amount.toFixed(2)} {payment.price_currency.toUpperCase()}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {t('payment.soncopay_fee_note') || 'SoncoPay shows the exact amount for the method you choose.'}
                </p>
              </div>

              {safeCheckoutUrl(payment.checkout_url) ? (
                <a
                  href={safeCheckoutUrl(payment.checkout_url) as string}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="soncopay-checkout-link"
                  className="flex w-full items-center justify-center gap-2 rounded-md bg-myhigh5-primary px-4 py-2 text-sm font-medium text-white hover:bg-myhigh5-primary/90"
                >
                  {t('payment.continue_to_soncopay') || 'Continue to the secure payment page'}
                  <ExternalLink className="w-4 h-4" />
                </a>
              ) : (
                <p className="text-sm text-red-700 dark:text-red-300">
                  {t('payment.checkout_unavailable') || 'The payment page is not available. Please try again in a few minutes.'}
                </p>
              )}

              <div className="break-all px-2 text-center text-xs text-gray-500 dark:text-gray-400">
                {t('payment.order_id') || 'Reference'}: {payment.order_id}
              </div>

              <div className="flex items-center justify-center gap-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <Clock className="w-4 h-4 text-blue-500" />
                <p className="text-xs text-blue-700 dark:text-blue-300" data-testid="soncopay-status">
                  {statusMessage || paymentStateText('pending')}
                </p>
              </div>

              {paymentError && (
                <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                  <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-red-700 dark:text-red-300">{paymentError}</p>
                </div>
              )}

              <div className="flex flex-col gap-3 pt-2 sm:flex-row">
                <Button variant="outline" onClick={handleBack} className="flex-1" disabled={isCheckingPayment}>
                  {t('common.back') || 'Back'}
                </Button>
                <Button
                  onClick={checkPaymentNow}
                  disabled={isCheckingPayment}
                  className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary/90"
                >
                  {isCheckingPayment ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      {t('payment.checking') || 'Checking...'}
                    </>
                  ) : (
                    t('payment.check_status') || 'Check status'
                  )}
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: NOWPayments checkout */}
          {step === 'payment' && payment && !isSoncoPay(payment) && (
            <div className="space-y-4">
              <div className="bg-myhigh5-primary/5 dark:bg-myhigh5-primary/10 rounded-xl p-4 text-center border border-myhigh5-primary/20">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                  {t('payment.amount_to_send') || 'Amount to send'}
                </p>
                <p className="text-2xl font-bold text-myhigh5-primary break-all">
                  {payment.pay_amount} {payment.pay_currency.toUpperCase()}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  ≈ ${payment.price_amount.toFixed(2)} {payment.price_currency.toUpperCase()}
                </p>
              </div>

              {payment.pay_address && (
                <div className="flex justify-center">
                  <div className="p-3 bg-white rounded-xl border border-gray-200">
                    <QRCodeSVG value={payment.pay_address} size={140} level="H" includeMargin />
                  </div>
                </div>
              )}

              {payment.pay_address && (
                <div>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {t('payment.receiving_address') || 'Receiving address'}
                  </p>
                  <div className="flex items-start gap-2 p-3 bg-gray-100 dark:bg-gray-800 rounded-lg">
                    <code className="text-xs flex-1 break-all text-gray-900 dark:text-white font-mono">
                      {payment.pay_address}
                    </code>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="flex-shrink-0 h-8 w-8 p-0"
                      onClick={() => copyToClipboard(payment.pay_address)}
                    >
                      {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                    </Button>
                  </div>
                </div>
              )}

              <div className="break-all px-2 text-center text-xs text-gray-500 dark:text-gray-400">
                {t('payment.order_id') || 'Reference'}: {payment.order_id}
              </div>

              {statusMessage && (
                <div className="flex items-center justify-center gap-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <Clock className="w-4 h-4 text-blue-500" />
                  <p className="text-xs text-blue-700 dark:text-blue-300">{statusMessage}</p>
                </div>
              )}

              {paymentError && (
                <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                  <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-red-700 dark:text-red-300">{paymentError}</p>
                </div>
              )}

              <div className="flex flex-col gap-3 pt-2 sm:flex-row">
                <Button variant="outline" onClick={handleBack} className="flex-1" disabled={isCheckingPayment}>
                  {t('common.back') || 'Back'}
                </Button>
                <Button
                  onClick={checkPaymentNow}
                  disabled={isCheckingPayment}
                  className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary/90"
                >
                  {isCheckingPayment ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      {t('payment.checking') || 'Checking...'}
                    </>
                  ) : (
                    t('payment.check_status') || 'Check status'
                  )}
                </Button>
              </div>
            </div>
          )}

          {/* Step 4: Success */}
          {step === 'success' && (
            <div className="space-y-5 py-6">
              {/* Success Icon */}
              <div className="flex justify-center">
                <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                  <CheckCircle2 className="w-8 h-8 text-green-600" />
                </div>
              </div>

              {/* Success Message */}
              <div className="text-center">
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-1">
                  {t('payment.success_title') || 'Payment confirmed!'}
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {t('payment.success_description') || 'Your payment has been received and confirmed.'}
                </p>
              </div>

              {/* Amount Summary */}
              <div className="bg-green-50 dark:bg-green-900/20 rounded-xl p-4 text-center border border-green-200 dark:border-green-800">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {t('payment.amount_paid') || 'Amount Paid'}
                </p>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  ${totalAmount.toFixed(2)} USD
                </p>
              </div>

              {/* Close Button */}
              <Button
                onClick={() => {
                  resetAndClose()
                }}
                className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary/90"
              >
                {t('common.continue') || 'Continuer'}
              </Button>
            </div>
          )}

          </div>
        </DialogContent>
      </Dialog>

      {/* Close confirmation dialog */}
      <AlertDialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('payment.confirm_close_title') || 'Close the payment?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('payment.confirm_close_description') || 'Your progress will be lost. Are you sure you want to close?'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('common.cancel') || 'Cancel'}
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
