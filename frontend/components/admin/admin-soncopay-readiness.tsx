'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { financeErrorText } from '@/lib/finance-admin'

/**
 * Admin > Finance & Payments > SoncoPay Payouts: readiness of SoncoPay payments and automatic payouts, item by
 * item (READY / BLOCKED / NOT VERIFIED / NOT APPLICABLE) with its evidence, the money switches, and the SoncoPay
 * payment reconciliation. Read-only (/api/v1/admin/finance/soncopay/readiness): nothing here activates
 * anything, even when every item is READY.
 */

export type ReadinessItem = { key: string; label: string; status: string; kind: string; evidence: string }
type Problem = { type: string; severity: string; message: string }
export type Readiness = {
  checked_at: string
  provider_read: boolean
  items: ReadinessItem[]
  counts: Record<string, number>
  switches: Record<string, boolean>
  payment_reconciliation: {
    deposits: { by_status: Record<string, number>; validated: number; with_processed_webhook: number }
    webhooks: { total: number; last_received_at: string | null; by_outcome: Record<string, number> }
    problems: Problem[]
    critical: number
  }
}

const TONE: Record<string, string> = {
  READY: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  BLOCKED: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  NOT_VERIFIED: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  NOT_APPLICABLE: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
}

const SWITCH_LABEL: Record<string, string> = {
  automatic_payout_activated: 'Automatic payouts activated (server)',
  crypto_auto_payout_enabled: 'Crypto payout engine (server)',
  advertising_funding_enabled: 'Advertising funding',
  advertising_campaigns_enabled: 'Advertising campaigns',
  annual_ads_enabled: 'Annual Ads',
  marketplace_enabled: 'Marketplace',
}

export function statusText(status: string): string {
  return status.replace('_', ' ')
}

export default function AdminSoncoPayReadiness() {
  const [data, setData] = useState<Readiness | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (provider = false) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get(`/api/v1/admin/finance/soncopay/readiness${provider ? '?provider=true' : ''}`)
      if (res.status === 200) setData(res.data as Readiness)
      else setError(financeErrorText(res, 'The readiness could not be loaded.'))
    } catch {
      setError('The readiness could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  return (
    <Card data-testid="sp-readiness">
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">Payment and payout readiness</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Read-only. Nothing is activated from here, even when every item is ready.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={loading} onClick={() => void load(false)}>Refresh</Button>
            <Button variant="outline" size="sm" disabled={loading} onClick={() => void load(true)}>
              Read SoncoPay (read-only)
            </Button>
          </div>
        </div>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        {loading && !data && <p className="text-sm text-gray-500">Loading…</p>}
        {data && (
          <>
            <p className="text-xs text-gray-500 dark:text-gray-400" data-testid="sp-readiness-counts">
              {Object.entries(data.counts).filter(([, n]) => n > 0).map(([s, n]) => `${n} ${statusText(s)}`).join(' · ')}
              {data.provider_read ? ' · SoncoPay read' : ' · SoncoPay not read'}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm" data-testid="sp-readiness-table">
                <thead className="text-xs uppercase text-gray-500">
                  <tr><th className="py-1 pr-3">Item</th><th className="py-1 pr-3">Status</th><th className="py-1 pr-3">Type</th><th className="py-1">Evidence</th></tr>
                </thead>
                <tbody>
                  {data.items.map((i) => (
                    <tr key={i.key} className="border-t border-gray-100 align-top dark:border-gray-700">
                      <td className="py-2 pr-3 font-medium text-gray-900 dark:text-white">{i.label}</td>
                      <td className="py-2 pr-3">
                        <span data-testid={`sp-ready-${i.key}`} className={`rounded px-2 py-0.5 text-xs font-semibold ${TONE[i.status] ?? TONE.NOT_APPLICABLE}`}>
                          {statusText(i.status)}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-xs text-gray-500">{i.kind}</td>
                      <td className="py-2 text-xs text-gray-600 dark:text-gray-300">{i.evidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid gap-2 sm:grid-cols-3" data-testid="sp-readiness-switches">
              {Object.entries(data.switches).map(([k, on]) => (
                <div key={k} className="rounded-lg bg-gray-50 p-2 text-xs dark:bg-gray-900/40">
                  <span className="text-gray-500">{SWITCH_LABEL[k] ?? k}: </span>
                  <span className={on ? 'font-semibold text-amber-700' : 'font-semibold text-gray-700 dark:text-gray-200'}>
                    {on ? 'ON' : 'OFF'}
                  </span>
                </div>
              ))}
            </div>
            <div data-testid="sp-payment-reconciliation" className="space-y-1 text-sm">
              <p className="font-medium text-gray-900 dark:text-white">SoncoPay payment reconciliation</p>
              <p className="text-xs text-gray-500">
                Confirmed SoncoPay payments: {data.payment_reconciliation.deposits.validated} · signed webhook deliveries:{' '}
                {data.payment_reconciliation.webhooks.total} (last {data.payment_reconciliation.webhooks.last_received_at ?? 'never'})
              </p>
              {data.payment_reconciliation.problems.length === 0 ? (
                <p className="text-xs text-green-700">No mismatch between local payments and SoncoPay events.</p>
              ) : (
                <ul className="list-disc pl-5 text-xs">
                  {data.payment_reconciliation.problems.map((p, n) => (
                    <li key={n} className={p.severity === 'critical' ? 'text-red-700' : 'text-amber-700'}>{p.message}</li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
