'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Copy,
  Check,
  AlertCircle,
  Loader2,
  CreditCard,
  CheckCircle2,
  Clock
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'

interface ResumePaymentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  depositId: number
  externalPaymentId?: string
  productCode?: string
  amount: number
  onPaymentCompleted?: () => void
}

interface PaymentDetails {
  deposit_id: number
  payment_status: string
  pay_address: string
  pay_amount: string
  pay_currency: string
  price_amount: number
  price_currency: string
  order_id: string
  actually_paid?: string
  is_confirmed: boolean
}

export function ResumePaymentDialog({
  open,
  onOpenChange,
  depositId,
  externalPaymentId,
  productCode,
  amount,
  onPaymentCompleted
}: ResumePaymentDialogProps) {
  const { t } = useLanguage()
  const [isLoading, setIsLoading] = useState(true)
  const [paymentDetails, setPaymentDetails] = useState<PaymentDetails | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [isCheckingPayment, setIsCheckingPayment] = useState(false)
  const [paymentConfirmed, setPaymentConfirmed] = useState(false)
  const [lastCheckTime, setLastCheckTime] = useState<Date | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const POLLING_INTERVAL = 30000

  // Reset state when dialog opens or depositId changes
  useEffect(() => {
    if (open) {
      setIsLoading(true)
      setPaymentDetails(null)
      setError(null)
      setCopied(false)
      setIsCheckingPayment(false)
      setPaymentConfirmed(false)
      setLastCheckTime(null)
      setStatusMessage(null)
    }
  }, [open, depositId])

  // Fetch payment details
  const fetchPaymentDetails = useCallback(async () => {
    if (!externalPaymentId) {
      setError(t('payment.no_payment_id') || 'Aucun identifiant de paiement')
      setIsLoading(false)
      return
    }

    try {
      const token = localStorage.getItem('access_token')
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      const response = await fetch(
        `${apiUrl}/api/v1/payments/check-status/${depositId}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (!response.ok) {
        throw new Error('Failed to fetch payment details')
      }

      const data = await response.json()
      
      if (data.is_confirmed || data.status === 'validated') {
        setPaymentConfirmed(true)
        onPaymentCompleted?.()
      } else if (data.status === 'expired') {
        setError(t('payment.payment_expired') || 'Ce paiement a expiré')
      } else {
        setPaymentDetails(data)
      }
      
      setLastCheckTime(new Date())
    } catch (err) {
      console.error('Error fetching payment details:', err)
      setError(t('payment.fetch_error') || 'Erreur lors du chargement des détails')
    } finally {
      setIsLoading(false)
    }
  }, [depositId, externalPaymentId, t, onPaymentCompleted])

  // Check payment status
  const checkPaymentStatus = useCallback(async () => {
    if (!depositId || paymentConfirmed) return

    setIsCheckingPayment(true)
    try {
      const token = localStorage.getItem('access_token')
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      const response = await fetch(
        `${apiUrl}/api/v1/payments/check-status/${depositId}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (!response.ok) throw new Error('Check failed')

      const data = await response.json()
      setLastCheckTime(new Date())

      if (data.is_confirmed || data.status === 'validated') {
        setPaymentConfirmed(true)
        setStatusMessage(t('payment.confirming') || 'Paiement confirmé !')
        stopPolling()
        setTimeout(() => {
          onPaymentCompleted?.()
        }, 2000)
      } else if (data.status === 'expired') {
        setError(t('payment.payment_expired') || 'Ce paiement a expiré')
        stopPolling()
      } else if (data.payment_status === 'partially_paid') {
        setStatusMessage(t('payment.partially_paid') || 'Paiement partiel reçu')
      } else if (data.payment_status === 'waiting') {
        setStatusMessage(t('payment.waiting_payment') || 'En attente de paiement...')
      } else if (data.payment_status === 'confirming') {
        setStatusMessage(t('payment.confirming') || 'Paiement détecté, confirmation...')
      }
    } catch (err) {
      console.error('Error checking payment:', err)
    } finally {
      setIsCheckingPayment(false)
    }
  }, [depositId, paymentConfirmed, t, onPaymentCompleted])

  // Polling
  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) return
    pollingIntervalRef.current = setInterval(checkPaymentStatus, POLLING_INTERVAL)
  }, [checkPaymentStatus])

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
  }, [])

  useEffect(() => {
    if (open && !paymentConfirmed) {
      fetchPaymentDetails()
      startPolling()
    }
    return () => stopPolling()
  }, [open, depositId, paymentConfirmed, fetchPaymentDetails, startPolling, stopPolling])

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const getProductName = (code?: string) => {
    switch (code) {
      case 'kyc':
        return t('payment.kyc_verification') || 'KYC Service'
      case 'mfm_membership':
        return t('payment.mfm_membership') || 'MFM'
      case 'annual_membership':
        return t('payment.annual_membership') || 'Annual Membership'
      default:
        return code || 'Service'
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-md mx-auto max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base sm:text-lg">
            {paymentConfirmed ? (
              <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0" />
            ) : (
              <CreditCard className="w-5 h-5 text-myfav-primary flex-shrink-0" />
            )}
            <span className="truncate">
              {paymentConfirmed 
                ? (t('payment.success_title') || 'Paiement confirmé')
                : (t('payment.payment_instructions') || 'Instructions de paiement')
              }
            </span>
          </DialogTitle>
          <DialogDescription className="text-sm">
            {getProductName(productCode)} - ${amount.toFixed(2)} USD
          </DialogDescription>
        </DialogHeader>

        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-8 h-8 animate-spin text-myfav-primary" />
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
            <AlertCircle className="w-5 h-5 text-red-500 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        {paymentConfirmed && (
          <div className="space-y-4 py-4">
            <div className="flex justify-center">
              <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <CheckCircle2 className="w-8 h-8 text-green-600" />
              </div>
            </div>
            <div className="text-center">
              <p className="text-gray-600 dark:text-gray-400">
                {t('payment.success_description') || 'Votre paiement a été confirmé.'}
              </p>
            </div>
            <Button onClick={() => onOpenChange(false)} className="w-full">
              {t('common.close') || 'Fermer'}
            </Button>
          </div>
        )}

        {!isLoading && !error && !paymentConfirmed && paymentDetails && (
          <div className="space-y-3 sm:space-y-4">
            {/* QR Code */}
            <div className="flex justify-center">
              <div className="p-2 sm:p-3 bg-white rounded-xl border border-gray-200">
                <QRCodeSVG 
                  value={paymentDetails.pay_address}
                  size={140}
                  level="H"
                  includeMargin={true}
                  className="w-[120px] h-[120px] sm:w-[140px] sm:h-[140px]"
                />
              </div>
            </div>

            {/* Amount */}
            <div className="bg-myfav-primary/5 dark:bg-myfav-primary/10 rounded-xl p-3 sm:p-4 text-center border border-myfav-primary/20">
              <p className="text-xs sm:text-sm text-gray-600 dark:text-gray-400 mb-1">
                {t('payment.amount_to_send') || 'Montant à envoyer'}
              </p>
              <p className="text-xl sm:text-2xl font-bold text-myfav-primary break-all">
                {paymentDetails.pay_amount} {paymentDetails.pay_currency.toUpperCase()}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                ≈ ${paymentDetails.price_amount.toFixed(2)} USD
              </p>
            </div>

            {/* Address */}
            <div>
              <p className="text-xs sm:text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('payment.receiving_address') || 'Adresse de réception'}
              </p>
              <div className="flex items-start gap-2 p-2 sm:p-3 bg-gray-100 dark:bg-gray-800 rounded-lg">
                <code className="text-[10px] sm:text-xs flex-1 break-all text-gray-900 dark:text-white font-mono leading-relaxed">
                  {paymentDetails.pay_address}
                </code>
                <Button
                  variant="ghost"
                  size="sm"
                  className="flex-shrink-0 h-8 w-8 p-0"
                  onClick={() => copyToClipboard(paymentDetails.pay_address)}
                >
                  {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
            </div>

            {/* Order ID */}
            <div className="text-center text-[10px] sm:text-xs text-gray-500 truncate">
              {t('payment.order_id') || 'Réf'}: {paymentDetails.order_id}
            </div>

            {/* Warning */}
            <div className="flex items-start gap-2 p-2 sm:p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
              <AlertCircle className="w-3 h-3 sm:w-4 sm:h-4 text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-[10px] sm:text-xs text-red-700 dark:text-red-300">
                {t('payment.network_warning') || "Envoyez le montant exact sur le bon réseau."}
              </p>
            </div>

            {/* Auto-check indicator */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                <p className="text-[10px] sm:text-xs text-blue-700 dark:text-blue-300">
                  {t('payment.auto_checking') || 'Vérification auto'}
                </p>
              </div>
              {lastCheckTime && (
                <p className="text-[10px] sm:text-xs text-blue-500">
                  ({lastCheckTime.toLocaleTimeString()})
                </p>
              )}
            </div>

            {/* Status message */}
            {statusMessage && (
              <div className="flex items-center justify-center gap-2 p-2 bg-green-50 dark:bg-green-900/20 rounded-lg">
                <Clock className="w-3 h-3 sm:w-4 sm:h-4 text-green-500 flex-shrink-0" />
                <p className="text-[10px] sm:text-xs text-green-700 dark:text-green-300">{statusMessage}</p>
              </div>
            )}

            {/* Check button */}
            <Button
              onClick={checkPaymentStatus}
              disabled={isCheckingPayment}
              className="w-full bg-myfav-primary hover:bg-myfav-primary/90 text-sm sm:text-base"
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
        )}
      </DialogContent>
    </Dialog>
  )
}
