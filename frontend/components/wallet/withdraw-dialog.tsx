'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Loader2, Wallet, AlertTriangle } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { getEffectiveApiUrl } from '@/lib/config'
import { apiErrorText, financialHoldMessage, isFinancialActionAvailable } from '@/lib/financial-eligibility'

type WithdrawPreview = {
  available_to_withdraw: number
  minimum_withdrawal: number
  fee: number
  net_amount: number
  eligibility_status?: string | null
  eligibility_next_step?: string | null
  cashout_method?: string | null
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

/** USD Cashout request: the whole available balance, the existing fee, the net. */
export function WithdrawDialog({ open, onOpenChange, onSuccess }: Props) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [preview, setPreview] = useState<WithdrawPreview | null>(null)
  // The fee rule and what a request needs come from the server's configuration.
  const [rules, setRules] = useState<{ feeRule: string; destinationRequired: boolean; destinationNote: string | null }>({
    feeRule: '', destinationRequired: false, destinationNote: null,
  })
  const [destination, setDestination] = useState('')
  const idempotencyKeyRef = useRef<string | null>(null)

  const loadPreview = useCallback(async () => {
    setLoading(true)
    try {
      const token = localStorage.getItem('access_token')
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
      const [res, summaryRes] = await Promise.all([
        fetch(`${getEffectiveApiUrl()}/api/v1/wallet/withdraw/preview`, { headers }),
        fetch(`${getEffectiveApiUrl()}/api/v1/wallet/cashout`, { headers }),
      ])
      if (res.ok) {
        setPreview((await res.json()) as WithdrawPreview)
      }
      if (summaryRes.ok) {
        const summary = await summaryRes.json()
        setRules({
          feeRule: summary?.fees?.USD?.rule ?? '',
          destinationRequired: Boolean(summary?.methods?.USD?.destination_required),
          destinationNote: summary?.methods?.USD?.destination_note ?? null,
        })
      }
    } catch {
      addToast(t('common.error') || 'Error loading cashout preview', 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    if (open) {
      void loadPreview()
    } else {
      idempotencyKeyRef.current = null
    }
  }, [open, loadPreview])

  const amount = preview?.available_to_withdraw ?? 0
  const min = preview?.minimum_withdrawal ?? 100
  const eligible = isFinancialActionAvailable(preview?.eligibility_status)
  const holdMessage = financialHoldMessage(preview?.eligibility_status, preview?.eligibility_next_step)
  const usdChosen = preview?.cashout_method === 'USD'
  const canSubmit =
    eligible && usdChosen && amount >= min && (!rules.destinationRequired || destination.trim().length > 0)

  const handleRequest = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const token = localStorage.getItem('access_token')
      if (!idempotencyKeyRef.current) {
        idempotencyKeyRef.current = crypto.randomUUID()
      }
      const res = await fetch(`${getEffectiveApiUrl()}/api/v1/wallet/cashout/usd`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKeyRef.current,
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ amount, destination: destination.trim() || undefined }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(apiErrorText(data.detail, 'The cashout request could not be made'))
      }
      addToast(
        `USD Cashout requested: $${Number(data.net_amount).toFixed(2)} after a $${Number(data.fee).toFixed(2)} fee.`,
        'success'
      )
      onOpenChange(false)
      setDestination('')
      idempotencyKeyRef.current = null
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
            Request USD Cashout
          </DialogTitle>
          <DialogDescription>
            Your whole available balance is requested. Minimum ${min}
            {rules.feeRule ? `; fee ${rules.feeRule}` : ''}. The amount is reserved until the MyHigh5 team has paid it
            or the request is cancelled.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
          </div>
        ) : (
          <div className="space-y-4">
            {holdMessage && (
              <div
                role="status"
                data-testid="withdraw-held"
                className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/20 p-3 text-sm text-amber-900 dark:text-amber-100"
              >
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                {holdMessage}
              </div>
            )}
            {!holdMessage && !usdChosen && (
              <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/20 p-3 text-sm text-amber-900 dark:text-amber-100">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                Choose USD Cashout as your cashout method first.
              </div>
            )}
            {!holdMessage && usdChosen && amount < min && (
              <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/20 p-3 text-sm text-amber-900 dark:text-amber-100">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                USD Cashout needs an available balance of at least ${min}.
              </div>
            )}

            <div className="rounded-lg bg-gray-50 dark:bg-gray-800/50 p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Amount requested</span>
                <span className="font-semibold tabular-nums">${amount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">{t('dashboard.wallet.estimated_fee') || 'Fee'}</span>
                <span className="tabular-nums">${(preview?.fee ?? 0).toFixed(2)}</span>
              </div>
              <div className="flex justify-between border-t border-gray-200 dark:border-gray-700 pt-2">
                <span className="text-gray-500">{t('dashboard.wallet.you_receive') || 'You receive (net)'}</span>
                <span className="font-bold text-myhigh5-primary tabular-nums">
                  ${(preview?.net_amount ?? 0).toFixed(2)}
                </span>
              </div>
            </div>

            {(rules.destinationRequired || rules.destinationNote) && (
              <div className="space-y-1">
                <label htmlFor="usd-destination" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Payout destination{rules.destinationRequired ? '' : ' (optional)'}
                </label>
                {rules.destinationNote && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">{rules.destinationNote}</p>
                )}
                <textarea
                  id="usd-destination"
                  rows={3}
                  maxLength={500}
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Stored encrypted and shown only to the MyHigh5 team member who pays your request.
                </p>
              </div>
            )}

            <Button
              className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary/90"
              disabled={submitting || !canSubmit}
              onClick={() => void handleRequest()}
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t('common.processing') || 'Processing…'}
                </>
              ) : (
                'Confirm request'
              )}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
