'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ShieldCheck } from 'lucide-react'
import api from '@/lib/api'

type MissedItem = {
  id: number
  category: string
  source: string
  contest_entry_id?: number | null
  original_submission_type?: string | null
  percentage?: string | null
  amount: string
  currency: string
  kyc_status_at_event: string
  date: string
  status: string
}

type MissedPage = {
  total: string
  currency: string
  count: number
  kyc_status: string
  kyc_url: string
  message: string
  items: MissedItem[]
}

const PAGE = 20

const KYC_LABELS: Record<string, string> = {
  none: 'Not started',
  pending: 'Pending',
  in_progress: 'In progress',
  pending_proof_of_address: 'Proof of address pending',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired',
  requires_review: 'Under review',
  not_approved: 'Not approved',
}

const CATEGORY_LABELS: Record<string, string> = {
  REFERRAL_COMMISSION: 'Referral commission',
  AD_CREATIVE_SHARE: 'Creative ad share',
  AD_SPONSOR_SHARE: 'Sponsor ad share (1%)',
}

export const kycLabel = (status?: string) => KYC_LABELS[status || 'none'] || status || 'Not started'

/** Missed earnings (KYC not approved at the earning event). Read-only: never payable, never in a balance. */
export function MissedEarnings({ endpoint, title, emptyText }: { endpoint: string; title: string; emptyText: string }) {
  const [data, setData] = useState<MissedPage | null>(null)
  const [skip, setSkip] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    api
      .get<MissedPage>(endpoint, { params: { skip, limit: PAGE } })
      .then((res) => alive && setData(res.data))
      .catch(() => alive && setError('Missed earnings could not be loaded.'))
    return () => {
      alive = false
    }
  }, [endpoint, skip])

  if (error) return <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
  if (!data) return null
  const verified = data.kyc_status === 'approved'

  return (
    <section
      className="rounded-xl sm:rounded-2xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 p-4 sm:p-5"
      aria-labelledby="missed-earnings-title"
    >
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h2 id="missed-earnings-title" className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
            <AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />
            {title}
          </h2>
          <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{data.message}</p>
          <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
            Missed amounts are not payable and are not part of your available balance.
          </p>
        </div>
        <div className="shrink-0 text-left sm:text-right">
          <p className="text-xs text-gray-600 dark:text-gray-400">Total missed</p>
          <p className="text-xl font-bold text-gray-900 dark:text-white">
            {data.total} {data.currency}
          </p>
          <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
            Verification status: <span className="font-medium">{kycLabel(data.kyc_status)}</span>
          </p>
        </div>
      </div>

      {!verified && (
        <Link
          href={data.kyc_url || '/dashboard/kyc'}
          className="mt-3 inline-flex items-center gap-2 rounded-lg bg-myhigh5-primary px-3 py-2 text-sm font-medium text-white hover:bg-myhigh5-primary/90"
        >
          <ShieldCheck className="h-4 w-4" aria-hidden />
          Complete KYC verification
        </Link>
      )}

      {data.items.length === 0 ? (
        <p className="mt-3 text-sm text-gray-600 dark:text-gray-400">{emptyText}</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-xs sm:text-sm">
            <thead className="text-left text-gray-500 dark:text-gray-400">
              <tr>
                {['Date', 'Type', 'Source', 'Rate %', 'Amount', 'KYC at the time'].map((h) => (
                  <th key={h} className="whitespace-nowrap py-1 pr-3 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((m) => (
                <tr key={m.id} className="border-t border-amber-100 dark:border-amber-900/40">
                  <td className="whitespace-nowrap py-1 pr-3">{new Date(m.date).toLocaleDateString()}</td>
                  <td className="pr-3">{CATEGORY_LABELS[m.category] || m.category}</td>
                  <td className="pr-3">
                    {m.source}
                    {m.contest_entry_id ? ` · entry #${m.contest_entry_id}` : ''}
                  </td>
                  <td className="pr-3">{m.percentage ?? '—'}</td>
                  <td className="whitespace-nowrap pr-3">
                    {m.amount} {m.currency}
                    {m.status === 'REVERSED' ? ' (refunded)' : ''}
                  </td>
                  <td className="pr-3">{kycLabel(m.kyc_status_at_event)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.count > PAGE && (
            <div className="mt-3 flex items-center gap-3 text-sm">
              <button
                type="button"
                disabled={skip === 0}
                onClick={() => setSkip(Math.max(0, skip - PAGE))}
                className="rounded border px-2 py-1 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-gray-600 dark:text-gray-400">
                {skip + 1}–{Math.min(skip + PAGE, data.count)} of {data.count}
              </span>
              <button
                type="button"
                disabled={skip + PAGE >= data.count}
                onClick={() => setSkip(skip + PAGE)}
                className="rounded border px-2 py-1 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
