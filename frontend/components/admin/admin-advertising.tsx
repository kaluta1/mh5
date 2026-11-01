'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'

type Json = Record<string, any>
const BASE = '/api/v1/admin/advertising'

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return typeof detail === 'string' ? detail : (detail as Json).message || JSON.stringify(detail)
  }
  return e instanceof Error ? e.message : 'Request failed'
}

async function call(method: 'get' | 'post' | 'put', url: string, body?: unknown) {
  const res = await api.request({ method, url: `${BASE}${url}`, data: body })
  if (res.status >= 400) throw { response: res }
  return res.data
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 overflow-x-auto rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <h2 className="font-semibold text-gray-900 dark:text-white">{title}</h2>
      {children}
    </section>
  )
}

function Table({ rows, cols }: { rows: Json[]; cols: string[] }) {
  if (!rows?.length) return <p className="text-sm text-gray-500">No rows.</p>
  return (
    <table className="w-full text-xs sm:text-sm">
      <thead className="text-left text-gray-500">
        <tr>{cols.map((c) => <th key={c} className="whitespace-nowrap py-1 pr-3">{c}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-t border-gray-100 dark:border-gray-700">
            {cols.map((c) => (
              <td key={c} className="whitespace-nowrap py-1 pr-3">
                {typeof r[c] === 'object' && r[c] !== null ? JSON.stringify(r[c]) : String(r[c] ?? '')}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const MONEY_SWITCHES: [string, string][] = [
  ['campaigns_enabled', 'Serve MyHigh5 campaigns'],
  ['funding_enabled', 'Advertisers may buy credit'],
  ['adsense_fallback_enabled', 'AdSense fallback in placements'],
  ['contest_sharing_enabled', 'Contest-entry revenue sharing'],
  ['adsense_sharing_enabled', 'AdSense revenue sharing (policy confirmed)'],
]

export default function AdminAdvertising() {
  const [overview, setOverview] = useState<Json | null>(null)
  const [campaigns, setCampaigns] = useState<Json[]>([])
  const [origins, setOrigins] = useState<Json[]>([])
  const [message, setMessage] = useState<string>('')
  const [password, setPassword] = useState('')
  const [cpm, setCpm] = useState('')
  const [minBudget, setMinBudget] = useState('')
  const [period, setPeriod] = useState('')
  const [adsenseTotal, setAdsenseTotal] = useState('')
  const [evidence, setEvidence] = useState('')

  const load = useCallback(async () => {
    try {
      const [o, c, g] = await Promise.all([call('get', '/overview'), call('get', '/campaigns'), call('get', '/origins')])
      setOverview(o)
      setCampaigns(c.campaigns || [])
      setOrigins(g.origins || [])
      setCpm(o.settings?.cpm_rate_usd ?? '')
      setMinBudget(o.settings?.min_campaign_budget_usd ?? '')
    } catch (e) {
      setMessage(errorDetail(e))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setMessage('')
    try {
      await fn()
      setMessage(ok)
      await load()
    } catch (e) {
      setMessage(errorDetail(e))
    }
  }

  const s = overview?.settings || {}
  return (
    <div className="space-y-6">
      {message ? <p className="rounded bg-gray-100 p-2 text-sm dark:bg-gray-700">{message}</p> : null}
      <label className="block text-sm">
        Current password (required for every change)
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full max-w-sm rounded border px-2 py-1 dark:bg-gray-900" autoComplete="current-password" />
      </label>

      <Section title={`Pricing and switches — ${s.pricing_state || ''}`}>
        <p className="text-sm text-gray-600 dark:text-gray-300">
          No price is set until it is approved. While pricing is pending no campaign can be submitted, funded or served.
          Currency: USD. A campaign keeps the CPM rate it was submitted with.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">CPM (USD per 1,000 valid viewable impressions)
            <input value={cpm} onChange={(e) => setCpm(e.target.value)} className="mt-1 block rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <label className="text-sm">Minimum campaign budget (USD, optional)
            <input value={minBudget} onChange={(e) => setMinBudget(e.target.value)} className="mt-1 block rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <button className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
            onClick={() => run(() => call('put', '/settings', { changes: { cpm_rate_usd: cpm || null, min_campaign_budget_usd: minBudget || null },
              current_password: password }), 'Prices saved')}>Save prices</button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {MONEY_SWITCHES.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!s[key]}
                onChange={(e) => run(() => call('put', '/settings', { changes: { [key]: e.target.checked }, current_password: password }),
                  `${label}: ${e.target.checked ? 'on' : 'off'}`)} />
              {label}
            </label>
          ))}
        </div>
      </Section>

      <Section title="Campaigns">
        {campaigns.length === 0 ? <p className="text-sm text-gray-500">No campaigns.</p> : null}
        {campaigns.map((c) => (
          <div key={c.id} className="rounded border border-gray-200 p-3 text-sm dark:border-gray-700">
            <p className="font-medium">#{c.id} {c.name} — {c.status} — budget {c.budget_total} USD, spent {c.spent}, CPM {c.cpm_rate_usd ?? '—'}
              , valid impressions {c.valid_impressions}</p>
            {(c.creatives || []).map((cr: Json) => (
              <div key={cr.id} className="mt-1 flex flex-wrap items-center gap-2">
                <span>Creative #{cr.id}: “{cr.headline}” → {cr.destination_url} ({cr.review_status})</span>
                {cr.review_status === 'PENDING' ? (
                  <>
                    <button className="rounded bg-green-600 px-2 py-0.5 text-white"
                      onClick={() => run(() => call('post', `/creatives/${cr.id}/review`, { approve: true, note: 'approved' }), 'Creative approved')}>Approve</button>
                    <button className="rounded bg-red-600 px-2 py-0.5 text-white"
                      onClick={() => run(() => call('post', `/creatives/${cr.id}/review`, { approve: false, note: 'rejected by review' }), 'Creative rejected')}>Reject</button>
                  </>
                ) : null}
              </div>
            ))}
            <div className="mt-2 flex gap-2">
              {c.status === 'PENDING_REVIEW' ? (
                <>
                  <button className="rounded bg-green-600 px-2 py-0.5 text-white"
                    onClick={() => run(() => call('post', `/campaigns/${c.id}/review`, { approve: true, note: 'approved' }), 'Campaign approved')}>Approve campaign</button>
                  <button className="rounded bg-red-600 px-2 py-0.5 text-white"
                    onClick={() => run(() => call('post', `/campaigns/${c.id}/review`, { approve: false, note: 'rejected by review' }), 'Campaign rejected')}>Reject campaign</button>
                </>
              ) : null}
              {c.status === 'ACTIVE' ? (
                <button className="rounded bg-gray-600 px-2 py-0.5 text-white"
                  onClick={() => run(() => call('post', `/campaigns/${c.id}/pause`), 'Campaign paused')}>Pause</button>
              ) : null}
            </div>
          </div>
        ))}
      </Section>

      <Section title="Impressions and allocations">
        <p className="text-sm">Impression events: {JSON.stringify(overview?.impression_events || {})}</p>
        <Table rows={overview?.allocations || []} cols={['status', 'count', 'amount']} />
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">Month (YYYY-MM)
            <input value={period} onChange={(e) => setPeriod(e.target.value)} className="mt-1 block rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          {(['MYHIGH5', 'ADSENSE'] as const).map((source) => (
            <button key={source} className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
              onClick={() => run(() => call('post', '/finalize', { period, source, current_password: password }),
                `${source} ${period} finalized`)}>Release {source} month</button>
          ))}
        </div>
      </Section>

      <Section title={`Original submission type under review (${origins.length})`}>
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Revenue of these entries is held: the original type could not be proven from the submission records.
        </p>
        {origins.map((o) => (
          <div key={o.contestant_id} className="flex flex-wrap items-center gap-2 text-sm">
            <span>Entry #{o.contestant_id}: {JSON.stringify(o.evidence)}</span>
            {(['PERSONAL_SUBMISSION', 'NOMINATION'] as const).map((kind) => (
              <button key={kind} className="rounded border px-2 py-0.5"
                onClick={() => {
                  const note = window.prompt?.(`Evidence for ${kind}`) || ''
                  if (note) run(() => call('post', `/origins/${o.contestant_id}/resolve`, { origin_kind: kind, note, current_password: password }), 'Origin resolved')
                }}>{kind}</button>
            ))}
          </div>
        ))}
      </Section>

      <Section title="Google AdSense reconciliation">
        <p className="text-sm">
          Missing credentials: {(overview?.adsense?.credentials_missing || []).join(', ') || 'none'}. Without them nothing is imported;
          no AdSense earnings are ever invented.
        </p>
        <Table rows={overview?.adsense?.imports || []} cols={['id', 'status', 'rows', 'period_start', 'period_end', 'detail']} />
        <Table rows={overview?.adsense?.months || []} cols={['period', 'finalized_total', 'estimated_total']} />
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">Finalized Google earnings for the month above (USD)
            <input value={adsenseTotal} onChange={(e) => setAdsenseTotal(e.target.value)} className="mt-1 block rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <label className="text-sm">Evidence (AdSense Payments report reference)
            <input value={evidence} onChange={(e) => setEvidence(e.target.value)} className="mt-1 block rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <button className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
            onClick={() => run(() => call('post', '/adsense/months', { period, finalized_total: adsenseTotal, evidence_note: evidence,
              current_password: password }), 'Finalized AdSense month recorded')}>Record finalized month</button>
        </div>
      </Section>

      <Section title="Annual Ads">
        <p className="text-sm">
          Integration {overview?.annual_ads?.enabled ? 'enabled' : 'disabled'}. Payments by buyer match:{' '}
          {JSON.stringify(overview?.annual_ads?.payments_by_buyer_match || {})}. Sponsor commission: {overview?.annual_ads?.sponsor_commission}.
          Annual Ads never enters contest-entry revenue sharing.
        </p>
      </Section>
    </div>
  )
}
