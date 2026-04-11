'use client'

import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { logger } from '@/lib/logger'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  CreditCard,
  Wallet,
  Building2,
  Bitcoin,
  Copy,
  Check,
  ExternalLink,
  AlertCircle,
  Shield,
  Plus,
  Minus,
  Loader2,
  CheckCircle2
} from 'lucide-react'
import { paymentService, PaymentResponse } from '@/services/payment-service'
import { useWalletPayment } from '@/hooks/use-wallet-payment'
import { CONTRACTS } from '@/lib/config'

interface PaymentMethod {
  id: string
  nameKey: string
  icon: React.ReactNode
  category: 'crypto' | 'card' | 'bank'
  network?: string
  address?: string
}

interface Product {
  code: string
  nameKey: string
  price: number
  minAmount?: number
  maxQuantity?: number
  isQuantityBased: boolean // true = sélecteur de quantité, false = montant libre
  description?: string
}

const products: Product[] = [
  {
    code: 'kyc',
    nameKey: 'payment.kyc_verification',
    price: 1,
    maxQuantity: 10,
    isQuantityBased: true,
    description: 'payment.kyc_description'
  },
  {
    code: 'efm_membership',
    nameKey: 'payment.efm_membership',
    price: 100,
    minAmount: 100,
    isQuantityBased: false,
    description: 'payment.efm_description'
  }
]

interface PaymentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  productCode?: string
  productName?: string
  price?: number
  currency?: string
  onPaymentInitiated?: () => void
}

const paymentMethods: PaymentMethod[] = [
  {
    id: 'usdt',
    nameKey: 'USDT (BSC)',
    icon: <Wallet className="w-5 h-5 text-yellow-500" />,
    category: 'crypto',
    network: 'BNB Smart Chain'
  },
  {
    id: 'card',
    nameKey: 'payment.card',
    icon: <CreditCard className="w-5 h-5 text-blue-500" />,
    category: 'card'
  },
  {
    id: 'bank_transfer',
    nameKey: 'payment.bank_transfer',
    icon: <Building2 className="w-5 h-5 text-green-600" />,
    category: 'bank'
  }
]

export function PaymentDialog({
  open,
  onOpenChange,
  productCode = 'kyc',
  productName,
  price,
  currency = 'USD',
  onPaymentInitiated
}: PaymentDialogProps) {
  const { t } = useLanguage()
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [step, setStep] = useState<'product' | 'select' | 'instructions'>('product')
  const [quantity, setQuantity] = useState(1)
  const [customAmount, setCustomAmount] = useState<number>(100)
  const [selectedProductCode, setSelectedProductCode] = useState<string>(productCode)
  const [amountError, setAmountError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [payment, setPayment] = useState<PaymentResponse | null>(null)
  const [paymentError, setPaymentError] = useState<string | null>(null)
  const [txHash, setTxHash] = useState<string | null>(null)
  
  // Wallet payment hook
  const {
    isConnecting,
    isProcessing,
    connectedAddress,
    error: walletError,
    connectWallet,
    executePayment
  } = useWalletPayment()

  const selectedProduct = products.find(p => p.code === selectedProductCode) || products[0]
  const selectedPaymentMethod = paymentMethods.find(m => m.id === selectedMethod)
  
  // Calcul du montant total selon le type de produit
  const totalAmount = selectedProduct.isQuantityBased 
    ? (price || selectedProduct.price) * quantity 
    : customAmount

  const getMethodName = (method: PaymentMethod) => {
    // Pour les crypto, utiliser le nom directement
    if (method.category === 'crypto') return method.nameKey
    // Pour les autres, utiliser la traduction
    return t(method.nameKey) || method.nameKey
  }

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      logger.error('Failed to copy to clipboard', err)
    }
  }

  const handleProductSelect = (code: string) => {
    setSelectedProductCode(code)
    const product = products.find(p => p.code === code)
    if (product) {
      if (product.isQuantityBased) {
        setQuantity(1)
      } else {
        setCustomAmount(product.minAmount || product.price)
      }
    }
  }

  const validateAndContinue = () => {
    if (!selectedProduct.isQuantityBased && selectedProduct.minAmount) {
      if (customAmount < selectedProduct.minAmount) {
        setAmountError(t('payment.min_amount_error')?.replace('{amount}', `${selectedProduct.minAmount}`) 
          || `Le montant minimum est de ${selectedProduct.minAmount} ${currency}`)
        return
      }
    }
    setAmountError(null)
    setStep('select')
  }

  const handleMethodSelect = async (methodId: string) => {
    setSelectedMethod(methodId)
    setPaymentError(null)
    const method = paymentMethods.find(m => m.id === methodId)
    
    if (method?.category === 'crypto') {
      // Créer le paiement crypto via l'API
      setIsLoading(true)
      try {
        const token = localStorage.getItem('access_token')
        if (!token) {
          setPaymentError(t('common.login_required') || 'Veuillez vous connecter')
          setIsLoading(false)
          return
        }

        // Create payment order for smart contract payment
        const paymentOrder = await paymentService.createPayment(token, {
          amount: totalAmount,
          currency: currency.toLowerCase(),
          product_code: selectedProductCode
        })
        
        setPayment(paymentOrder)
        setStep('instructions')
      } catch (error) {
        logger.error('Payment creation error', error)
        setPaymentError(error instanceof Error ? error.message : 'Erreur lors de la création du paiement')
      } finally {
        setIsLoading(false)
      }
    } else if (method?.category === 'card') {
      alert(t('payment.card_coming_soon') || 'Paiement par carte bientôt disponible')
    } else if (method?.category === 'bank') {
      setStep('instructions')
    }
  }

  const handleWalletPayment = async () => {
    if (!payment) {
      setPaymentError(t('payment.no_payment_order') || 'Aucun ordre de paiement')
      return
    }

    const token = localStorage.getItem('access_token')
    if (!token) {
      setPaymentError(t('common.login_required') || 'Veuillez vous connecter')
      return
    }

    try {
      const hash = await executePayment(payment, token)
      setTxHash(hash)
    } catch (error) {
      logger.error('Wallet payment error', error)
      setPaymentError(error instanceof Error ? error.message : 'Erreur lors du paiement')
    }
  }

  const handleBack = () => {
    if (step === 'instructions') {
      setStep('select')
      setSelectedMethod(null)
      setPayment(null)
    } else if (step === 'select') {
      setStep('product')
    }
  }

  const handleClose = () => {
    setStep('product')
    setSelectedMethod(null)
    setSelectedProductCode(productCode)
    setQuantity(1)
    setCustomAmount(100)
    setAmountError(null)
    setPayment(null)
    setPaymentError(null)
    setTxHash(null)
    onOpenChange(false)
  }

  const getProductName = (product: Product) => {
    return t(product.nameKey) || product.nameKey
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-myhigh5-primary" />
            {step === 'product' && (t('payment.choose_product') || 'Choisir un produit')}
            {step === 'select' && (t('payment.payment_method') || 'Méthode de paiement')}
            {step === 'instructions' && (t('payment.payment_instructions') || 'Instructions de paiement')}
          </DialogTitle>
          <DialogDescription>
            {step === 'product' && (t('payment.choose_product_description') || 'Sélectionnez le produit que vous souhaitez acheter.')}
            {step === 'select' && (t('payment.choose_method') || 'Choisissez votre méthode de paiement')}
            {step === 'instructions' && (
              t('payment.send_exact_amount')?.replace('{amount}', `${totalAmount} ${currency}`)
                || `Envoyez exactement ${totalAmount} ${currency} à l'adresse ci-dessous.`
            )}
          </DialogDescription>
        </DialogHeader>

        {/* Step 1: Product Selection */}
        {step === 'product' && (
          <div className="space-y-4 mt-4">
            {/* Product selector */}
            <div className="space-y-2">
              {products.map((product) => (
                <button
                  key={product.code}
                  onClick={() => handleProductSelect(product.code)}
                  className={`w-full flex items-center justify-between p-4 rounded-lg border transition-all text-left ${
                    selectedProductCode === product.code
                      ? 'border-myhigh5-primary bg-myhigh5-primary/10'
                      : 'border-gray-200 dark:border-gray-700 hover:border-myhigh5-primary/50'
                  }`}
                >
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{getProductName(product)}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {product.isQuantityBased 
                        ? `${product.price} ${currency} / ${t('payment.unit') || 'unité'}`
                        : `${t('payment.min') || 'Min'}: ${product.minAmount} ${currency}`
                      }
                    </p>
                  </div>
                  <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                    selectedProductCode === product.code
                      ? 'border-myhigh5-primary bg-myhigh5-primary'
                      : 'border-gray-300 dark:border-gray-600'
                  }`}>
                    {selectedProductCode === product.code && (
                      <Check className="w-3 h-3 text-white" />
                    )}
                  </div>
                </button>
              ))}
            </div>

            {/* Amount input based on product type */}
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
              {selectedProduct.isQuantityBased ? (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm text-gray-600 dark:text-gray-400">{t('payment.quantity') || 'Quantité'}:</span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setQuantity(Math.max(1, quantity - 1))}
                        disabled={quantity <= 1}
                        className="w-8 h-8 rounded-lg bg-gray-200 dark:bg-gray-700 flex items-center justify-center hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Minus className="w-4 h-4" />
                      </button>
                      <span className="w-12 text-center font-bold text-lg">{quantity}</span>
                      <button
                        onClick={() => setQuantity(Math.min(selectedProduct.maxQuantity || 10, quantity + 1))}
                        disabled={quantity >= (selectedProduct.maxQuantity || 10)}
                        className="w-8 h-8 rounded-lg bg-gray-200 dark:bg-gray-700 flex items-center justify-center hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('payment.validity_one_year') || 'Validité: 1 an par unité'}
                  </p>
                </>
              ) : (
                <>
                  <label className="block text-sm text-gray-600 dark:text-gray-400 mb-2">
                    {t('payment.enter_amount') || 'Entrez le montant'} ({currency}):
                  </label>
                  <input
                    type="number"
                    value={customAmount}
                    onChange={(e) => {
                      setCustomAmount(Number(e.target.value))
                      setAmountError(null)
                    }}
                    min={selectedProduct.minAmount || 1}
                    className="w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-lg font-bold text-center focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
                  />
                  {amountError && (
                    <p className="text-sm text-red-500 mt-2 flex items-center gap-1">
                      <AlertCircle className="w-4 h-4" />
                      {amountError}
                    </p>
                  )}
                  {selectedProduct.minAmount && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                      {t('payment.min_amount') || 'Montant minimum'}: {selectedProduct.minAmount} {currency}
                    </p>
                  )}
                </>
              )}
              
              {/* Total */}
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                <span className="font-medium text-gray-700 dark:text-gray-300">{t('payment.total') || 'Total'}:</span>
                <span className="text-2xl font-bold text-myhigh5-primary">{totalAmount} {currency}</span>
              </div>
            </div>

            {/* Continue button */}
            <Button 
              onClick={validateAndContinue}
              className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary/90"
            >
              {t('common.continue') || 'Continuer'}
            </Button>
          </div>
        )}

        {step === 'select' && (
          <div className="space-y-4 mt-4">
            {/* Order summary */}
            <div className="bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">{getProductName(selectedProduct)}</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {selectedProduct.isQuantityBased 
                      ? `${quantity} × ${selectedProduct.price} ${currency}`
                      : t('payment.custom_amount') || 'Montant personnalisé'
                    }
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-500 dark:text-gray-400">{t('payment.total') || 'Total'}</p>
                  <p className="text-2xl font-bold text-myhigh5-primary">{totalAmount} {currency}</p>
                </div>
              </div>
              <button 
                onClick={() => setStep('product')}
                className="text-sm text-myhigh5-primary hover:underline mt-2"
              >
                {t('common.modify') || 'Modifier'}
              </button>
            </div>

            {/* Loading state */}
            {isLoading && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-8 h-8 animate-spin text-myhigh5-primary" />
                <span className="ml-3 text-gray-600 dark:text-gray-400">
                  {t('payment.creating_payment') || 'Création du paiement...'}
                </span>
              </div>
            )}

            {/* Error message */}
            {paymentError && (
              <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg mb-4">
                <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-red-700 dark:text-red-300">{paymentError}</p>
              </div>
            )}

            {/* Payment methods */}
            {!isLoading && (
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                {t('payment.choose_method') || 'Choisissez votre méthode de paiement'}
              </p>
              
              {/* Crypto methods */}
              <div className="mb-4">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
                  {t('payment.cryptocurrencies') || 'Crypto-monnaies'}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {paymentMethods.filter(m => m.category === 'crypto').map((method) => (
                    <button
                      key={method.id}
                      onClick={() => handleMethodSelect(method.id)}
                      disabled={isLoading}
                      className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-myhigh5-primary hover:bg-myhigh5-primary/5 transition-all text-left disabled:opacity-50"
                    >
                      {method.icon}
                      <span className="text-sm font-medium text-gray-900 dark:text-white">{getMethodName(method)}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Other methods */}
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
                  {t('payment.other_methods') || 'Autres méthodes'}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {paymentMethods.filter(m => m.category !== 'crypto').map((method) => (
                    <button
                      key={method.id}
                      onClick={() => handleMethodSelect(method.id)}
                      className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-myhigh5-primary hover:bg-myhigh5-primary/5 transition-all text-left"
                    >
                      {method.icon}
                      <span className="text-sm font-medium text-gray-900 dark:text-white">{getMethodName(method)}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
            )}

            {/* Info */}
            {!isLoading && (
              <div className="flex items-start gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <AlertCircle className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  {t('payment.validation_time_info') || 'Après votre paiement, la validation peut prendre quelques minutes à quelques heures selon la méthode choisie.'}
                </p>
              </div>
            )}
          </div>
        )}

        {step === 'instructions' && selectedPaymentMethod && (
          <div className="space-y-4 mt-4">
            {/* Selected method */}
            <div className="flex items-center gap-3 p-3 bg-gray-100 dark:bg-gray-800 rounded-lg">
              {selectedPaymentMethod.icon}
              <div>
                <p className="font-medium text-gray-900 dark:text-white">{getMethodName(selectedPaymentMethod)}</p>
                {selectedPaymentMethod.network && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">{t('payment.network') || 'Réseau'}: {selectedPaymentMethod.network}</p>
                )}
              </div>
            </div>

            {/* Wallet Payment Flow */}
            {selectedPaymentMethod.category === 'crypto' && payment && (
              <>
                {/* Payment Amount */}
                <div className="bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 rounded-lg p-4 text-center">
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{t('Amount to pay') || 'Montant à payer'}</p>
                  <p className="text-3xl font-bold text-myhigh5-primary">
                    ${payment.price_amount.toFixed(2)} {payment.price_currency.toUpperCase()}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    ≈ {(parseFloat(payment.amount_wei) / 1e18).toFixed(6)} USDT
                  </p>
                </div>

                {/* Wallet Connection Status */}
                {connectedAddress ? (
                  <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-green-700 dark:text-green-300">
                        {t('wallet connected') || 'Portefeuille connecté'}
                      </p>
                      <p className="text-xs text-green-600 dark:text-green-400 font-mono">
                        {connectedAddress.slice(0, 6)}...{connectedAddress.slice(-4)}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                    <p className="text-sm text-blue-700 dark:text-blue-300 text-center">
                      {t('connect wallet first') || 'Connectez votre portefeuille pour continuer'}
                    </p>
                  </div>
                )}

                {/* Network Info */}
                <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                    {t('payment.network') || 'Réseau'}
                  </p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    BNB Smart Chain (BSC)
                  </p>
                </div>

                {/* Order ID */}
                <div className="text-center text-xs text-gray-500 dark:text-gray-400">
                  {t('payment.order_id') || 'Référence'}: {payment.order_id}
                </div>

                {/* Transaction Hash (if payment completed) */}
                {txHash && (
                  <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                      {t('payment.transaction_hash') || 'Hash de transaction'}
                    </p>
                    <div className="flex items-center gap-2">
                      <code className="text-xs flex-1 break-all text-gray-900 dark:text-white font-mono">
                        {txHash}
                      </code>
                      <a
                        href={`${CONTRACTS.EXPLORER_URL}/tx/${txHash}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-shrink-0"
                      >
                        <ExternalLink className="w-4 h-4 text-blue-500" />
                      </a>
                    </div>
                  </div>
                )}

                {/* Error Messages */}
                {(paymentError || walletError) && (
                  <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                    <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                    <p className="text-sm text-red-700 dark:text-red-300">
                      {paymentError || walletError}
                    </p>
                  </div>
                )}
              </>
            )}

            {/* Bank instructions */}
            {selectedPaymentMethod.category === 'bank' && (
              <div className="space-y-3">
                <div className="p-3 bg-gray-100 dark:bg-gray-800 rounded-lg">
                  <p className="text-sm font-medium text-gray-900 dark:text-white mb-2">{t('payment.bank_details') || 'Coordonnées bancaires'}</p>
                  <div className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
                    <p><span className="font-medium">IBAN:</span> FR76 XXXX XXXX XXXX XXXX XXXX XXX</p>
                    <p><span className="font-medium">BIC:</span> XXXXXXXX</p>
                    <p><span className="font-medium">{t('payment.beneficiary') || 'Bénéficiaire'}:</span> MyHigh5 SAS</p>
                  </div>
                </div>
                <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                  <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-amber-700 dark:text-amber-300">
                    {t('payment.bank_reference_info') || "Indiquez votre email en référence du virement pour faciliter l'identification."}
                  </p>
                </div>
              </div>
            )}

            {/* Warning */}
            <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
              <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-red-700 dark:text-red-300">
                {t('payment.network_warning') || "Assurez-vous d'envoyer le montant exact sur le bon réseau. Les erreurs de réseau peuvent entraîner une perte de fonds."}
              </p>
            </div>

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={handleBack} className="flex-1" disabled={isProcessing || isConnecting}>
                {t('common.back') || 'Retour'}
              </Button>
              {selectedPaymentMethod?.category === 'crypto' && payment ? (
                !connectedAddress ? (
                  <Button
                    onClick={connectWallet}
                    disabled={isConnecting}
                    className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary/90"
                  >
                    {isConnecting ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        {t('payment.connecting') || 'Connexion...'}
                      </>
                    ) : (
                      <>
                        <Wallet className="w-4 h-4 mr-2" />
                        {t('connect wallet first') || 'Connecter le portefeuille'}
                      </>
                    )}
                  </Button>
                ) : (
                  <Button
                    onClick={handleWalletPayment}
                    disabled={isProcessing || !!txHash}
                    className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary/90"
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        {t('processing') || 'Traitement...'}
                      </>
                    ) : txHash ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 mr-2" />
                        {t('payment.completed') || 'Terminé'}
                      </>
                    ) : (
                      <>
                        <Wallet className="w-4 h-4 mr-2" />
                        {t('pay now') || 'Payer maintenant'}
                      </>
                    )}
                  </Button>
                )
              ) : (
                <Button 
                  onClick={() => {
                    onPaymentInitiated?.()
                    handleClose()
                  }}
                  className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary/90"
                >
                  {t('common.close') || 'Fermer'}
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
