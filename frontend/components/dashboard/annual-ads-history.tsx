'use client'

import { useEffect, useState } from 'react'
import api from '@/lib/api'

type Purchase = { id: number; date: string | null; gross_amount: string; payment_status: string; refund_status: string | null }
type Commission = {
  id: number; date: string | null; gross_amount: string; rate_percent: string | null; amount: string | null
  status: string; commission_status: string | null; refund_status: string | null
}

const STATUS: Record<string, string> = {
  RECORDED: 'Earned', MISSED_KYC: 'Missed — KYC not approved (not payable)', REVERSED: 'Reversed (purchase refunded)',
  FINANCE_REVIEW: 'Under finance review', NO_SPONSOR: '—', BUYER_UNIDENTIFIED: '—',
}

/** The member's own Annual Ads purchases and the direct-sponsor commissions they earned on them
 * (20% of the gross purchase, 40% once qualified). Hidden when there is nothing to show. */
export function AnnualAdsHistory() {
  const [data, setData] = useState<{ purchases: Purchase[]; sponsor_commissions: Commission[] } | null>(null)
  useEffect(() => {
    api.get('/api/v1/annual-ads/history')
      .then((res) => { if (res.status < 400) setData(res.data) })
      .catch(() => undefined)
  }, [])
  if (!data || (data.purchases.length === 0 && data.sponsor_commissions.length === 0)) return null
  return (
    <section data-testid="annual-ads-history" className="space-y-3 rounded-2xl border border-gray-100 bg-white p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
      <h2 className="text-lg font-semibold">Annual Ads</h2>
      {data.sponsor_commissions.length ? (
        <div className="overflow-x-auto">
          <p className="mb-1 text-xs text-gray-500">As the buyer&apos;s direct sponsor: 20% of the gross purchase (40% once qualified).</p>
          <table className="w-full text-xs sm:text-sm">
            <thead className="text-left text-gray-500"><tr>
              {['Date', 'Purchase (gross)', 'Rate', 'Commission', 'Status'].map((h) => <th key={h} className="py-1 pr-3">{h}</th>)}
            </tr></thead>
            <tbody>
              {data.sponsor_commissions.map((c) => (
                <tr key={c.id} className="border-t border-gray-100 dark:border-gray-700">
                  <td className="pr-3">{(c.date || '').slice(0, 10)}</td>
                  <td className="pr-3">{c.gross_amount} USD</td>
                  <td className="pr-3">{c.rate_percent ? `${Number(c.rate_percent).toFixed(0)}%` : '—'}</td>
                  <td className="pr-3">{c.amount ? `${c.amount} USD` : '—'}</td>
                  <td className="pr-3">{STATUS[c.status] || c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {data.purchases.length ? (
        <div>
          <p className="mb-1 text-xs text-gray-500">Your Annual Ads purchases</p>
          <ul className="space-y-1">
            {data.purchases.map((p) => (
              <li key={p.id}>{(p.date || '').slice(0, 10)} — {p.gross_amount} USD — {p.refund_status ? `refund ${p.refund_status.toLowerCase()}` : 'paid'}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
