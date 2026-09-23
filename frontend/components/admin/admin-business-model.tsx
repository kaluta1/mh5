'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'

type Json = Record<string, any>
const BASE = '/api/v1/admin/business-model'
const usd = (n: number | undefined) => `$${Number(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail)
  }
  return e instanceof Error ? e.message : 'Request failed'
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 space-y-3 overflow-x-auto">
      <h2 className="font-semibold text-gray-900 dark:text-white">{title}</h2>
      {children}
    </section>
  )
}

function Table({ rows, cols }: { rows: Json[]; cols: string[] }) {
  if (!rows.length) return <p className="text-sm text-gray-500">No rows.</p>
  return (
    <table className="w-full text-xs sm:text-sm">
      <thead className="text-left text-gray-500">
        <tr>{cols.map((c) => <th key={c} className="py-1 pr-3 whitespace-nowrap">{c}</th>)}</tr>
      </thead>
      <tbody className="text-gray-800 dark:text-gray-200">
        {rows.map((r, i) => (
          <tr key={i} className="border-t border-gray-100 dark:border-gray-700 align-top">
            {cols.map((c) => (
              <td key={c} className="py-1 pr-3">
                {Array.isArray(r[c]) ? r[c].join(', ') : typeof r[c] === 'object' && r[c] !== null ? JSON.stringify(r[c]) : String(r[c] ?? '')}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const TABS = ['Overview', 'Referral Pool', 'Leaders', 'Marketplace'] as const

export default function AdminBusinessModel() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Overview')
  const [overview, setOverview] = useState<Json | null>(null)
  const [members, setMembers] = useState<Json[]>([])
  const [assignments, setAssignments] = useState<Json[]>([])
  const [migration, setMigration] = useState<Json | null>(null)
  const [runs, setRuns] = useState<Json[]>([])
  const [periods, setPeriods] = useState<Json[]>([])
  const [period, setPeriod] = useState<Json | null>(null)
  const [preview, setPreview] = useState<Json | null>(null)
  const [orders, setOrders] = useState<Json[]>([])
  const now = new Date()
  const last = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1))
  const [year, setYear] = useState(last.getUTCFullYear())
  const [month, setMonth] = useState(last.getUTCMonth() + 1)
  const [message, setMessage] = useState<string | null>(null)

  const run = useCallback(async (fn: () => Promise<void>) => {
    setMessage(null)
    try {
      await fn()
    } catch (e) {
      setMessage(errorDetail(e))
    }
  }, [])

  const loadTab = useCallback(() => {
    if (tab === 'Overview') run(async () => setOverview((await api.get(`${BASE}/overview`)).data))
    if (tab === 'Referral Pool')
      run(async () => {
        setMembers((await api.get(`${BASE}/referral-pool/members`)).data)
        setAssignments((await api.get(`${BASE}/referral-pool/assignments`)).data)
        setMigration((await api.get(`${BASE}/referral-pool/legacy-migration/preview`)).data)
        setRuns((await api.get(`${BASE}/referral-pool/legacy-migration/runs`)).data)
      })
    if (tab === 'Leaders') run(async () => setPeriods((await api.get(`${BASE}/leaders/periods`)).data))
    if (tab === 'Marketplace')
      run(async () => {
        setOverview((await api.get(`${BASE}/overview`)).data)
        setOrders((await api.get(`${BASE}/marketplace/orders`)).data)
      })
  }, [tab, run])

  useEffect(() => {
    loadTab()
  }, [loadTab])

  const leadersAction = (path: string, body?: Json) =>
    run(async () => {
      const res = await api.post(`${BASE}${path}`, body ?? {})
      setPeriod(res.data)
      setPeriods((await api.get(`${BASE}/leaders/periods`)).data)
      setMessage('Done.')
    })

  const manifest = migration?.manifest
  const manual = (manifest?.candidates ?? []).filter((c: Json) => c.classification === 'MANUAL_REVIEW')

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Business model (NEW_V2)</h1>
        <p className="text-sm text-gray-500">Direct affiliate, Referral Pool, MyHigh5 Leaders and marketplace custody. All financial actions are audited.</p>
      </div>
      <div className="flex flex-wrap gap-2" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${tab === t ? 'bg-myhigh5-primary text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200'}`}>
            {t}
          </button>
        ))}
      </div>
      {message && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{message}</p>}

      {tab === 'Overview' && overview && (
        <>
          <Card title="Version">
            <p className="text-sm">{overview.version} effective {overview.effective_at} · legacy model enabled: {String(overview.legacy_business_model_enabled)}</p>
          </Card>
          <Card title="Referral Pool">
            <p className="text-sm">Seats {overview.referral_pool.seats_in_use} / {overview.referral_pool.capacity} · assignments {overview.referral_pool.assignments} · method {overview.referral_pool.assignment_method}</p>
            <p className="text-sm">By status: {JSON.stringify(overview.referral_pool.by_status)} · active by source: {JSON.stringify(overview.referral_pool.active_by_source)}</p>
          </Card>
          <Card title="Revenue & commission policies">
            <Table rows={overview.revenue_policies} cols={['product_code', 'category', 'revenue_account', 'provider_cost_rate', 'commission_eligible', 'commission_rate', 'leaders_revenue_eligible', 'notes']} />
          </Card>
        </>
      )}

      {tab === 'Referral Pool' && (
        <>
          {manifest && (
            <Card title="Legacy $100 Founding migration (read-only dry run)">
              <p className="text-sm">Manifest SHA-256: <code className="break-all">{migration?.sha256}</code></p>
              <p className="text-sm">Counts: {JSON.stringify(manifest.counts)} · to insert: {manifest.to_insert_deposit_ids.length} · capacity overflow: {manifest.would_exceed_capacity_by}</p>
              <p className="text-sm">Execution runs only on the server with the reviewed hash (scripts/referral_pool_legacy_migration.py).</p>
              <h3 className="text-sm font-semibold mt-2">Manual review cases</h3>
              <Table rows={manual} cols={['deposit_id', 'user_id', 'product_code', 'amount', 'reasons']} />
              <h3 className="text-sm font-semibold mt-2">All evidence</h3>
              <Table rows={manifest.candidates} cols={['deposit_id', 'user_id', 'product_code', 'amount', 'deposit_status', 'classification', 'reasons', 'cash_journal_entry_id']} />
            </Card>
          )}
          <Card title="Migration runs"><Table rows={runs} cols={['run_id', 'inserted', 'automatic_eligible', 'manual_review', 'not_eligible', 'operator', 'created_at']} /></Card>
          <Card title="Members"><Table rows={members} cols={['id', 'user_id', 'username', 'status', 'seat_number', 'source', 'source_deposit_id', 'joined_at', 'assignments_count', 'notes']} /></Card>
          <Card title="Assignments"><Table rows={assignments} cols={['referred_user_id', 'pool_member_user_id', 'method', 'candidate_count', 'min_assignment_count', 'assigned_at']} /></Card>
        </>
      )}

      {tab === 'Leaders' && (
        <>
          <Card title="Month">
            <div className="flex flex-wrap items-end gap-2 text-sm">
              <label className="flex flex-col">Year<input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} className="rounded border px-2 py-1 w-24 dark:bg-gray-700" /></label>
              <label className="flex flex-col">Month<input type="number" min={1} max={12} value={month} onChange={(e) => setMonth(Number(e.target.value))} className="rounded border px-2 py-1 w-20 dark:bg-gray-700" /></label>
              <button className="rounded bg-gray-100 dark:bg-gray-700 px-3 py-1.5" onClick={() => run(async () => setPreview((await api.get(`${BASE}/leaders/preview`, { params: { year, month } })).data))}>Preview</button>
              <button className="rounded bg-myhigh5-primary text-white px-3 py-1.5" onClick={() => leadersAction('/leaders/prepare', { year, month })}>Prepare draft</button>
            </div>
            {preview && (
              <>
                <p className="text-sm">Revenue {usd(preview.eligible_company_revenue)} × {preview.pool_rate} = pool {usd(preview.pool_amount)} · qualifying {preview.qualifying_count} · allocated {usd(preview.allocated_amount)}</p>
                <Table rows={preview.lines.slice(0, 50)} cols={['rank', 'user_id', 'direct_commission', 'ratio', 'reward']} />
              </>
            )}
          </Card>
          <Card title="Periods">
            <Table rows={periods} cols={['id', 'period', 'status', 'eligible_company_revenue', 'pool_amount', 'qualifying_count', 'allocated_amount', 'prepared_by', 'approved_by', 'journal_entry_id']} />
            <div className="flex flex-wrap gap-2">
              {periods.filter((p) => ['DRAFT', 'APPROVED', 'POSTED'].includes(p.status)).map((p) => (
                <span key={p.id} className="flex gap-1 text-sm">
                  <button className="rounded bg-gray-100 dark:bg-gray-700 px-2 py-1" onClick={() => run(async () => setPeriod((await api.get(`${BASE}/leaders/periods/${p.id}`)).data))}>#{p.id} details</button>
                  {p.status === 'DRAFT' && <button className="rounded bg-gray-100 dark:bg-gray-700 px-2 py-1" onClick={() => leadersAction(`/leaders/periods/${p.id}/approve`)}>Approve</button>}
                  {p.status === 'APPROVED' && <button className="rounded bg-myhigh5-primary text-white px-2 py-1" onClick={() => leadersAction(`/leaders/periods/${p.id}/post`)}>Post</button>}
                </span>
              ))}
            </div>
          </Card>
          {period?.lines && (
            <Card title={`Period ${period.period} (${period.status}) · snapshot ${period.snapshot_sha256?.slice(0, 16)}…`}>
              <Table rows={period.lines} cols={['rank', 'user_id', 'direct_commission', 'ratio', 'reward', 'payout_status']} />
            </Card>
          )}
        </>
      )}

      {tab === 'Marketplace' && overview && (
        <>
          <Card title="Custody reconciliation (internal mirror)">
            <p className="text-sm">Custodian: {overview.marketplace.custodian} · enabled: {String(overview.marketplace.enabled)} · held at custodian: {usd(overview.marketplace.funds_held_at_custodian)} · markup released not yet remitted: {usd(overview.marketplace.markup_released_not_yet_remitted)}</p>
            <Table rows={overview.marketplace.by_state} cols={['state', 'orders', 'buyer_total', 'markup']} />
          </Card>
          <Card title="Orders & disputes"><Table rows={orders} cols={['id', 'state', 'seller_base_amount', 'markup_amount', 'buyer_total_amount', 'custodian', 'disputes']} /></Card>
        </>
      )}
    </div>
  )
}
