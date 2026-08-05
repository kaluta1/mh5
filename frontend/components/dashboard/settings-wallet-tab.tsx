'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Wallet, AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { getEffectiveApiUrl } from '@/lib/config'

type WalletInfo = {
  usdt_wallet_address?: string | null
  payout_currency?: string | null
  wallet_configured?: boolean
  supported_currencies?: string[]
}

const CURRENCY_META: Record<string, { label: string; placeholder: string; hint: string }> = {
  usdtbsc: {
    label: 'USDT BSC (BEP20)',
    placeholder: '0x…',
    hint: 'Address must start with 0x and be 42 characters.',
  },
  usdterc20: {
    label: 'USDT Ethereum (ERC20)',
    placeholder: '0x…',
    hint: 'Address must start with 0x and be 42 characters.',
  },
  usdttrc20: {
    label: 'USDT Tron (TRC20)',
    placeholder: 'T…',
    hint: 'Address must start with T and be 34 characters.',
  },
}

function maskAddress(addr: string): string {
  if (addr.length < 12) return addr
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`
}

function formatApiError(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : JSON.stringify(item))).join(', ')
  }
  return fallback
}

function clientValidateAddress(address: string, currency: string): string | null {
  const trimmed = address.trim()
  if (currency === 'usdttrc20') {
    return /^T[a-zA-Z0-9]{33}$/.test(trimmed) ? null : CURRENCY_META.usdttrc20.hint
  }
  return /^0x[a-fA-F0-9]{40}$/.test(trimmed) ? null : CURRENCY_META.usdtbsc.hint
}

export function SettingsWalletTab() {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [walletInfo, setWalletInfo] = useState<WalletInfo | null>(null)
  const [address, setAddress] = useState('')
  const [payoutCurrency, setPayoutCurrency] = useState('usdtbsc')

  const supportedCurrencies = useMemo(
    () => walletInfo?.supported_currencies?.length ? walletInfo.supported_currencies : ['usdtbsc', 'usdterc20', 'usdttrc20'],
    [walletInfo?.supported_currencies],
  )

  const currencyMeta = CURRENCY_META[payoutCurrency] ?? CURRENCY_META.usdtbsc

  const loadWallet = useCallback(async () => {
    setLoading(true)
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`${getEffectiveApiUrl()}/api/v1/users/me/wallet`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (res.ok) {
        const data = (await res.json()) as WalletInfo
        setWalletInfo(data)
        setAddress(data.usdt_wallet_address || '')
        setPayoutCurrency(data.payout_currency || 'usdtbsc')
      }
    } catch {
      addToast(t('common.error') || 'Error loading wallet', 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    void loadWallet()
  }, [loadWallet])

  const handleSave = async () => {
    const trimmed = address.trim()
    const validationError = clientValidateAddress(trimmed, payoutCurrency)
    if (validationError) {
      addToast(t('settings.wallet.invalid_address') || validationError, 'error')
      return
    }

    setSaving(true)
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`${getEffectiveApiUrl()}/api/v1/users/me/wallet`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          usdt_wallet_address: trimmed,
          payout_currency: payoutCurrency,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(formatApiError(err.detail, 'Failed to save wallet'))
      }
      const data = await res.json()
      setWalletInfo(data)
      setAddress(data.usdt_wallet_address || trimmed)
      setPayoutCurrency(data.payout_currency || payoutCurrency)
      const paid = data.pending_commissions_paid ?? 0
      addToast(
        paid > 0
          ? (t('settings.wallet.saved_with_payout') || `Wallet saved. ${paid} pending commission(s) paid.`)
          : (t('settings.wallet.saved') || 'Payout wallet saved.'),
        'success'
      )
    } catch (e) {
      addToast(e instanceof Error ? e.message : t('common.error') || 'Error', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
      </div>
    )
  }

  const configured = Boolean(walletInfo?.wallet_configured && walletInfo?.usdt_wallet_address)

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Wallet className="w-5 h-5 text-myhigh5-primary" />
          {t('settings.wallet.title') || 'Payout wallet'}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {t('settings.wallet.subtitle') ||
            'Affiliate commissions are sent automatically to your crypto wallet after each validated payment.'}
        </p>
      </div>

      {configured && (
        <div className="flex items-start gap-3 rounded-xl border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-4">
          <CheckCircle2 className="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-green-800 dark:text-green-200">
              {t('settings.wallet.configured') || 'Wallet configured'}
            </p>
            <p className="text-sm text-green-700 dark:text-green-300 font-mono mt-1">
              {maskAddress(walletInfo!.usdt_wallet_address!)}
            </p>
            <p className="text-xs text-green-600 dark:text-green-400 mt-1">
              {(CURRENCY_META[walletInfo!.payout_currency || 'usdtbsc'] ?? CURRENCY_META.usdtbsc).label}
            </p>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-4 flex gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <p className="text-sm text-amber-900 dark:text-amber-100">
          {t('settings.wallet.network_warning') ||
            'Choose the correct USDT network. Funds sent to the wrong network cannot be recovered.'}
        </p>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('settings.wallet.currency_label') || 'Payout network'}
        </label>
        <Select value={payoutCurrency} onValueChange={setPayoutCurrency}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {supportedCurrencies.map((code) => (
              <SelectItem key={code} value={code}>
                {(CURRENCY_META[code] ?? { label: code.toUpperCase() }).label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('settings.wallet.address_label') || 'Wallet address'}
        </label>
        <Input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder={currencyMeta.placeholder}
          className="font-mono"
          autoComplete="off"
          spellCheck={false}
        />
        <p className="text-xs text-gray-500 dark:text-gray-400">{currencyMeta.hint}</p>
      </div>

      <Button
        onClick={() => void handleSave()}
        disabled={saving || !address.trim()}
        className="bg-myhigh5-primary hover:bg-myhigh5-primary/90"
      >
        {saving ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            {t('common.saving') || 'Saving…'}
          </>
        ) : (
          t('settings.wallet.save') || 'Save wallet'
        )}
      </Button>
    </div>
  )
}
