'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'
import { Percent, BookOpen, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react'

type FmpMe = {
  user_fmp: string | number
  global_fmp: string | number
  fmr: string | number
}

function toNum(v: string | number): number {
  const n = typeof v === 'number' ? v : parseFloat(v)
  return Number.isFinite(n) ? n : 0
}

export default function FmrPage() {
  const [data, setData] = useState<FmpMe | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<FmpMe>('/api/v1/fmr/fmp/me')
      if (res.status >= 400) {
        setError(res.data?.detail ?? `Error ${res.status}`)
        setData(null)
        return
      }
      setData(res.data)
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? String((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? '')
          : ''
      setError(msg || 'Could not load FMP / FMR. Check that you are logged in and the API is deployed.')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const userFmp = data ? toNum(data.user_fmp) : 0
  const globalFmp = data ? toNum(data.global_fmp) : 0
  const fmr = data ? toNum(data.fmr) : 0
  const fmrPct = fmr * 100

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-myhigh5-primary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
              <Percent className="w-5 h-5 text-white" />
            </div>
            Founding Membership Points &amp; ratio
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2 max-w-2xl">
            Your FMP (Founding Membership Points) determine your share of the monthly Founding pool:{' '}
            <span className="font-medium text-gray-800 dark:text-gray-200">FMR = your FMP ÷ global FMP</span>
            {globalFmp > 0 && (
              <span>
                . Pool distributions use these weights for the 10% website-revenue Founding Member allocation
                when applicable.
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => load()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/80 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <Link
            href="/dashboard/founding-member"
            className="inline-flex items-center gap-2 rounded-lg bg-myhigh5-primary text-white px-4 py-2 text-sm font-medium shadow shadow-myhigh5-primary/25 hover:opacity-95"
          >
            <BookOpen className="w-4 h-4" />
            Founding Membership info
          </Link>
        </div>
      </div>

      {error && (
        <div
          className="flex items-start gap-3 rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 px-4 py-3 text-amber-900 dark:text-amber-100"
          role="alert"
        >
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {loading && !data && !error && (
        <div className="grid gap-4 sm:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-28 rounded-2xl bg-gray-200/80 dark:bg-gray-700/50 animate-pulse"
            />
          ))}
        </div>
      )}

      {data && (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-6 shadow-sm">
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Your FMP</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900 dark:text-white">
              {userFmp.toLocaleString(undefined, { maximumFractionDigits: 6 })}
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">Founding points you have earned</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-6 shadow-sm">
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Global FMP</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900 dark:text-white">
              {globalFmp.toLocaleString(undefined, { maximumFractionDigits: 6 })}
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">All members combined</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-6 shadow-sm sm:col-span-1">
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Your FMR</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-myhigh5-primary">
              {globalFmp > 0 ? `${fmrPct.toFixed(4)}%` : '—'}
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-500 font-mono">
              ratio {globalFmp > 0 ? fmr.toFixed(12) : '0'}
            </p>
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm overflow-hidden">
        <div className="p-6 sm:p-8 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-myhigh5-primary" />
            How you earn FMP
          </h2>
          <ul className="space-y-3 text-gray-600 dark:text-gray-300 text-sm sm:text-base">
            <li className="flex gap-2">
              <span className="text-myhigh5-primary font-bold">+1</span>
              <span>When you pay the Founding / MFM joining fee (credited per completed payment).</span>
            </li>
            <li className="flex gap-2">
              <span className="text-myhigh5-primary font-bold">+1</span>
              <span>Each time a direct referral completes account verification (KYC), to you as their sponsor.</span>
            </li>
          </ul>
          <p className="text-sm text-gray-500 dark:text-gray-500 pt-2 border-t border-gray-100 dark:border-gray-700">
            If your FMP and global FMP are zero, complete Founding membership and help your referrals verify — then
            refresh this page.
          </p>
        </div>
      </div>
    </div>
  )
}
