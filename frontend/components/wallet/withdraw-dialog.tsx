'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Loader2, Wallet, AlertTriangle } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { getEffectiveApiUrl } from '@/lib/config'

type WithdrawPreview = {
  available_to_withdraw: number
  minimum_withdrawal: number
  fee: number
  net_amount: number
  wallet_configured: boolean
  payout_currency?: string
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

export function WithdrawDialog({ open, onOpenChange, onSuccess }: Props) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [preview, setPreview] = useState<WithdrawPreview | null>(null)
  const [amount, setAmount] = useState('')

  const loadPreview = useCallback(async () => {
    setLoading(true)
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`${getEffectiveApiUrl()}/api/v1/wallet/withdraw/preview`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (res.ok) {
        const data = (await res.json()) as WithdrawPreview
        setPreview(data)
        if (data.available_to_withdraw >= data.minimum_withdrawal) {
          setAmount(String(Math.floor(data.available_to_withdraw * 100) / 100))
        }
      }
    } catch {
      addToast(t('common.error') || 'Error loading withdrawal preview', 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    if (open) void loadPreview()
  }, [open, loadPreview])

  const parsedAmount = parseFloat(amount) || 0
  const min = preview?.minimum_withdrawal ?? 100

  const handleWithdraw = async () => {
    if (!preview?.wallet_configured) {
      addToast(t('dashboard.wallet.setup_wallet_first') || 'Add a payout wallet in Settings first.', 'error')
      return
    }
    if (parsedAmount < min) {
      addToast(t('dashboard.wallet.min_withdrawal') || `Minimum withdrawal is $${min}.`, 'error')
      return
    }
    if (parsedAmount > (preview?.available_to_withdraw ?? 0)) {
      addToast(t('dashboard.wallet.insufficient_balance') || 'Insufficient approved balance.', 'error')
      return
    }

    setSubmitting(true)
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`${getEffectiveApiUrl()}/api/v1/wallet/withdraw`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ amount: parsedAmount }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || 'Withdrawal failed')
      }
      addToast(
        t('dashboard.wallet.withdraw_success') ||
          `Withdrawal submitted. $${Number(data.net_amount).toFixed(2)} USDT sent (fee $${Number(data.fee).toFixed(2)}).`,
        'success'
      )
      onOpenChange(false)
      onSuccess?.()
    } catch (e) {
      addToast(e instanceof Error ? e.message : t('common.error') || 'Error', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet className="w-5 h-5 text-myhigh5-primary" />
            {t('dashboard.wallet.withdraw_title') || 'Withdraw commissions'}
          </DialogTitle>
          <DialogDescription>
            {t('dashboard.wallet.withdraw_desc') ||
              'Batch withdraw approved commissions to your crypto wallet. Minimum $100; 1% fee (min $20, max $1,000).'}
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
          </div>
        ) : (
          <div className="space-y-4">
            {!preview?.wallet_configured && (
              <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/20 p-3 text-sm text-amber-900 dark:text-amber-100">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                {t('dashboard.wallet.setup_wallet_first') || 'Add a payout wallet in Settings before withdrawing.'}
              </div>
            )}

            <div className="rounded-lg bg-gray-50 dark:bg-gray-800/50 p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">{t('dashboard.wallet.approved_balance') || 'Approved balance'}</span>
                <span className="font-semibold">${(preview?.available_to_withdraw ?? 0).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">{t('dashboard.wallet.estimated_fee') || 'Estimated fee'}</span>
                <span>${(preview?.fee ?? 0).toFixed(2)}</span>
              </div>
              <div className="flex justify-between border-t border-gray-200 dark:border-gray-700 pt-2">
                <span className="text-gray-500">{t('dashboard.wallet.you_receive') || 'You receive (net)'}</span>
                <span className="font-bold text-myhigh5-primary">
                  ${Math.max(0, parsedAmount - (preview?.fee ?? 0)).toFixed(2)}
                </span>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('dashboard.wallet.withdraw_amount') || 'Amount (USD)'}
              </label>
              <Input
                type="number"
                min={min}
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="mt-1"
              />
              <p className="text-xs text-gray-500 mt-1">
                {t('dashboard.wallet.min_withdrawal_hint') || `Minimum $${min}. Auto-payout also sends each commission instantly when configured.`}
              </p>
            </div>

            <Button
              className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary/90"
              disabled={submitting || !preview?.wallet_configured || parsedAmount < min}
              onClick={() => void handleWithdraw()}
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t('common.processing') || 'Processing…'}
                </>
              ) : (
                t('dashboard.wallet.confirm_withdraw') || 'Confirm withdrawal'
              )}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
