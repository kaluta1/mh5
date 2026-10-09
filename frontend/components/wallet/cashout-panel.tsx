'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, Banknote, CheckCircle2, Coins, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { getEffectiveApiUrl } from '@/lib/config'
import { apiErrorText } from '@/lib/financial-eligibility'
import {
  canCancel,
  canRequestUsd,
  cashoutStatusText,
  formatDate,
  formatUsd,
  methodAvailable,
  methodLabel,
  needsAttention,
  recordStatusLabel,
  walletStatusLabel,
  type CashoutMethod,
  type CashoutRecord,
  type CashoutSummary,
} from '@/lib/cashout'

type Props = {
  /** Opens the USD Cashout confirmation dialog. */
  onRequestUsd: () => void
  /** Changes when the page reloads its data, so the panel reloads too. */
  refreshKey?: number
}

function authHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function CashoutPanel({ onRequestUsd, refreshKey = 0 }: Props) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [summary, setSummary] = useState<CashoutSummary | null>(null)
  const [history, setHistory] = useState<CashoutRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<CashoutMethod | null>(null)
  const [cancelling, setCancelling] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      const api = getEffectiveApiUrl()
      const [summaryRes, historyRes] = await Promise.all([
        fetch(`${api}/api/v1/wallet/cashout`, { headers: authHeaders() }),
        fetch(`${api}/api/v1/wallet/cashout/history?limit=20`, { headers: authHeaders() }),
      ])
      if (summaryRes.ok) setSummary((await summaryRes.json()) as CashoutSummary)
      if (historyRes.ok) setHistory((await historyRes.json()) as CashoutRecord[])
    } catch {
      // The rest of the wallet page still works; the panel simply stays empty.
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  const chooseMethod = async (method: CashoutMethod) => {
    if (!summary || summary.cashout_method === method) return
    setSaving(method)
    try {
      const res = await fetch(`${getEffectiveApiUrl()}/api/v1/wallet/cashout/method`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ method }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(apiErrorText(data.detail, 'Could not save your cashout method'))
      setSummary(data as CashoutSummary)
      addToast(`${methodLabel(method)} selected.`, 'success')
    } catch (e) {
      addToast(e instanceof Error ? e.message : t('common.error') || 'Error', 'error')
    } finally {
      setSaving(null)
    }
  }

  const cancel = async (record: CashoutRecord) => {
    setCancelling(record.id)
    try {
      const res = await fetch(`${getEffectiveApiUrl()}/api/v1/wallet/cashout/${record.id}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ reason: 'Cancelled by member' }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(apiErrorText(data.detail, 'Could not cancel the request'))
      addToast('Request cancelled. The amount is back in your available balance.', 'success')
      await load()
    } catch (e) {
      addToast(e instanceof Error ? e.message : t('common.error') || 'Error', 'error')
    } finally {
      setCancelling(null)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center rounded-2xl border border-gray-100 bg-white p-8 dark:border-gray-700 dark:bg-gray-800">
        <Loader2 className="h-6 w-6 animate-spin text-myhigh5-primary" />
      </div>
    )
  }
  if (!summary) return null

  const b = summary.balances
  const tiles: Array<[string, number]> = [
    ['Total earned', b.total_earned],
    ['Pending', b.pending],
    ['Available', b.available],
    ['Reserved', b.reserved],
    ['Paid', b.paid],
  ]
  const method = summary.cashout_method
  const attention = !['AUTOMATIC_PAYOUT_PENDING', 'READY_TO_REQUEST'].includes(summary.status)

  return (
    <section
      data-testid="cashout-panel"
      className="space-y-5 rounded-2xl border border-gray-100 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800"
    >
      <div>
        <h2 className="text-lg font-bold text-gray-900 dark:text-white">Commission cashout</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Your commissions are kept in full until they are paid. Choose one cashout method.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {tiles.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-gray-50 p-3 dark:bg-gray-900/40">
            <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
            <p className="mt-1 text-base font-semibold tabular-nums text-gray-900 dark:text-white">
              {formatUsd(value)}
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {(
          [
            {
              key: 'CRYPTO' as const,
              icon: Coins,
              lines: [
                `Minimum ${formatUsd(summary.minimums.CRYPTO)}`,
                `Paid automatically to your ${summary.destination.network ?? 'USDT BSC'} wallet`,
                summary.fees.CRYPTO.network_fee_policy === 'MEMBER_PAYS'
                  ? 'No MyHigh5 fee; the network fee is deducted'
                  : 'No MyHigh5 fee',
              ],
            },
            {
              key: 'USD' as const,
              icon: Banknote,
              lines: [`Minimum ${formatUsd(summary.minimums.USD)}`, 'You request each cashout', `Fee: ${summary.fees.USD.rule}`],
            },
          ]
        ).map(({ key, icon: Icon, lines }) => {
          const selected = method === key
          const offered = methodAvailable(summary, key)
          return (
            <button
              key={key}
              type="button"
              aria-pressed={selected}
              disabled={saving !== null || (!offered && !selected)}
              onClick={() => void chooseMethod(key)}
              className={`rounded-xl border-2 p-4 text-left transition-colors ${
                selected
                  ? 'border-myhigh5-primary bg-myhigh5-primary/5'
                  : 'border-gray-200 hover:border-gray-300 dark:border-gray-700 dark:hover:border-gray-600'
              }`}
            >
              <div className="flex items-center gap-2">
                <Icon className="h-5 w-5 text-myhigh5-primary" />
                <span className="font-semibold text-gray-900 dark:text-white">{methodLabel(key)}</span>
                {saving === key && <Loader2 className="h-4 w-4 animate-spin text-myhigh5-primary" />}
                {selected && saving !== key && <CheckCircle2 className="ml-auto h-5 w-5 text-myhigh5-primary" />}
              </div>
              <ul className="mt-2 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                {lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
                {!offered && <li className="font-medium text-amber-700 dark:text-amber-300">Not available at the moment</li>}
              </ul>
            </button>
          )
        })}
      </div>

      <div
        role="status"
        className={`flex gap-2 rounded-lg border p-3 text-sm ${
          attention
            ? 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-100'
            : 'border-green-200 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-900/20 dark:text-green-100'
        }`}
      >
        {attention ? (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        ) : (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
        )}
        <span>{cashoutStatusText(summary)}</span>
      </div>

      {method && (
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div className="flex justify-between gap-3">
            <dt className="text-gray-500 dark:text-gray-400">Selected method</dt>
            <dd className="font-medium text-gray-900 dark:text-white">{methodLabel(method)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-gray-500 dark:text-gray-400">Minimum</dt>
            <dd className="font-medium tabular-nums text-gray-900 dark:text-white">{formatUsd(summary.minimum)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-gray-500 dark:text-gray-400">Next cashout amount</dt>
            <dd className="font-medium tabular-nums text-gray-900 dark:text-white">
              {formatUsd(summary.payable_amount)}
            </dd>
          </div>
          {method === 'CRYPTO' ? (
            <>
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500 dark:text-gray-400">Fee</dt>
                <dd className="text-right font-medium text-gray-900 dark:text-white">{summary.fees.CRYPTO.note}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500 dark:text-gray-400">Payout wallet</dt>
                <dd className="text-right font-medium text-gray-900 dark:text-white">
                  {summary.destination.wallet ? (
                    <span className="font-mono">{summary.destination.wallet}</span>
                  ) : (
                    'Not set'
                  )}{' '}
                  <Link href="/dashboard/settings?tab=wallet" className="text-myhigh5-primary underline">
                    {summary.destination.wallet ? 'Change' : 'Add'}
                  </Link>
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500 dark:text-gray-400">Network</dt>
                <dd className="text-right font-medium text-gray-900 dark:text-white">
                  {summary.destination.network ?? summary.destination.payout_currency.toUpperCase()}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500 dark:text-gray-400">Wallet verification</dt>
                <dd className="text-right font-medium text-gray-900 dark:text-white" data-testid="wallet-verification">
                  {walletStatusLabel(summary.destination.wallet_status)}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500 dark:text-gray-400">Security hold</dt>
                <dd className="text-right font-medium text-gray-900 dark:text-white" data-testid="wallet-hold">
                  {summary.destination.wallet_status === 'ON_HOLD'
                    ? `Payouts start on ${formatDate(summary.destination.payable_from)}`
                    : summary.destination.wallet_status === 'VERIFIED'
                      ? 'Completed'
                      : `${summary.destination.hold_hours ?? 72} hours after the wallet is confirmed`}
                </dd>
              </div>
              {summary.destination.pending_wallet && (
                <div className="sm:col-span-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-900/20 dark:text-amber-100">
                  A change to <span className="font-mono">{summary.destination.pending_wallet.wallet}</span> is waiting
                  for the confirmation link we sent to your email address.
                </div>
              )}
            </>
          ) : (
            <>
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500 dark:text-gray-400">Fee</dt>
                <dd className="text-right font-medium tabular-nums text-gray-900 dark:text-white">
                  {summary.fees.USD.fee !== null ? formatUsd(summary.fees.USD.fee) : summary.fees.USD.rule}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-gray-500 dark:text-gray-400">You receive</dt>
                <dd className="font-medium tabular-nums text-gray-900 dark:text-white">
                  {summary.fees.USD.net_amount !== null ? formatUsd(summary.fees.USD.net_amount) : '-'}
                </dd>
              </div>
            </>
          )}
        </dl>
      )}

      {method === 'USD' && (
        <div>
          <Button
            onClick={onRequestUsd}
            disabled={!canRequestUsd(summary)}
            className="bg-myhigh5-primary hover:bg-myhigh5-primary/90"
          >
            Request USD Cashout
          </Button>
          {!summary.usd_settlement_active && (
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              Your request is recorded and reserved. USD payments are made by the MyHigh5 team and are not automatic.
            </p>
          )}
        </div>
      )}

      <div>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Cashout history</h3>
        {history.some(needsAttention) && (
          <p className="mt-1 text-xs text-amber-700 dark:text-amber-300" data-testid="history-attention">
            {history.filter(needsAttention).length} cashout(s) were not paid or are still being verified. Nothing is
            lost: an amount that was not paid is back in your available balance.
          </p>
        )}
        {history.length === 0 ? (
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No cashouts yet.</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="text-xs text-gray-500 dark:text-gray-400">
                <tr>
                  <th className="py-2 pr-3 font-medium">Date</th>
                  <th className="py-2 pr-3 font-medium">Method</th>
                  <th className="py-2 pr-3 text-right font-medium">Amount</th>
                  <th className="py-2 pr-3 text-right font-medium">Fee</th>
                  <th className="py-2 pr-3 text-right font-medium">Net</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {history.map((row) => (
                  <tr key={row.id}>
                    <td className="py-2 pr-3 text-gray-700 dark:text-gray-200">{formatDate(row.requested_at)}</td>
                    <td className="py-2 pr-3 text-gray-700 dark:text-gray-200">{methodLabel(row.method)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{formatUsd(row.gross_amount)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {formatUsd(row.fee)}
                      {row.network_fee_policy === 'MEMBER_PAYS' && row.network_fee ? (
                        <span className="block text-xs text-gray-500">+ {formatUsd(row.network_fee)} network</span>
                      ) : null}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">{formatUsd(row.net_amount)}</td>
                    <td className="py-2 pr-3 text-gray-700 dark:text-gray-200">
                      {recordStatusLabel(row.status)}
                      {row.reference ? <span className="block font-mono text-xs text-gray-500">{row.reference}</span> : null}
                    </td>
                    <td className="py-2 text-right">
                      {canCancel(row, summary) && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={cancelling === row.id}
                          onClick={() => void cancel(row)}
                        >
                          {cancelling === row.id ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Cancel'}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
