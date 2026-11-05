'use client'

import { useCallback, useEffect, useState } from 'react'
import { AdPlacementPreviews } from '@/components/ads/ad-creative-card'
import { MissedEarnings } from '@/components/dashboard/missed-earnings'
import { PayWithEarnings } from '@/components/wallet/pay-with-earnings'
import { call, errorDetail, type Json } from './ad-api'
import { CampaignForm } from './ad-campaign-form'
import { CreativeEditor } from './ad-creative-editor'

const STATUS_TEXT: Record<string, string> = {
  DRAFT: 'Draft', PENDING_REVIEW: 'Pending review', CHANGES_REQUESTED: 'Changes requested', ACTIVE: 'Active',
  PAUSED: 'Paused', COMPLETED: 'Completed', REJECTED: 'Rejected', CANCELLED: 'Cancelled',
}
const FUNDING_TEXT: Record<string, string> = {
  NOT_FUNDED: 'Not funded yet (the budget moves from your credit when you submit)',
  FUNDED: 'Funded from your advertiser credit', UNSPENT_RETURNED: 'Unspent budget returned to your credit',
}

/** Theoretical maximum of billable impressions for a budget at a CPM (never a delivery promise). */
export function estimateImpressions(budget: string | number, cpm: string | number | null | undefined): number | null {
  const b = Number(budget)
  const c = Number(cpm)
  if (!Number.isFinite(b) || !Number.isFinite(c) || b <= 0 || c <= 0) return null
  // cents x 1000 x 100 / (CPM in 1/10000 USD): exact for prices with up to 4 decimals
  return Math.floor((Math.round(b * 100) * 100000) / Math.round(c * 10000))
}

/** Placement previews of a creative (same markup as the live slot; renders only, never records an event). */
export function AdPreview({ creative, placements }: { creative: Json; placements?: string[] }) {
  return <AdPlacementPreviews creative={creative} placements={placements} />
}

function Packages({ packages }: { packages: Json[] }) {
  if (!packages?.length) return null
  return (
    <section data-testid="ad-packages" className="overflow-x-auto rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <h2 className="mb-2 font-semibold">Advertising products</h2>
      <table className="w-full text-xs sm:text-sm">
        <thead className="text-left text-gray-500"><tr>
          {['Product', 'Price', 'Minimum', 'Placements', 'Payment', 'Status'].map((h) => <th key={h} className="py-1 pr-3">{h}</th>)}
        </tr></thead>
        <tbody>
          {packages.map((p) => (
            <tr key={p.code} data-testid={`ad-package-${p.code}`} className="border-t border-gray-100 align-top dark:border-gray-700">
              <td className="py-1 pr-3 font-medium">{p.name}</td>
              <td className="pr-3">{p.price ? `${p.price} ${p.currency || ''} — ${p.price_unit}` : (p.price_unit || '—')}</td>
              <td className="pr-3">{p.minimum_budget ? `${p.minimum_budget} USD` : '—'}
                {p.estimated_impressions_at_minimum ? ` (up to ${p.estimated_impressions_at_minimum.toLocaleString('en-US')} impressions)` : ''}</td>
              <td className="pr-3">{(p.placements || []).join(', ') || '—'}</td>
              <td className="pr-3">{p.payment || '—'}</td>
              <td className="pr-3">{p.purchasable ? 'Available' : String(p.state || '').replace(/_/g, ' ').toLowerCase()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Analytics({ c }: { c: Json }) {
  const rows: [string, string][] = [
    ['Served', String(c.served_impressions ?? 0)], ['Valid (billable) impressions', String(c.valid_impressions ?? 0)],
    ['Rejected events', String(c.invalid_events ?? 0)], ['Spent', `${c.spent} USD`],
    ['Remaining budget', `${c.remaining_budget} USD`], ['Delivery progress', `${c.delivery_progress_percent ?? '0.0'}%`],
    ['Estimated remaining impressions', c.estimated_remaining_impressions != null
      ? c.estimated_remaining_impressions.toLocaleString('en-US') : 'unavailable'],
    ['Clicks', c.clicks == null ? 'Not tracked' : String(c.clicks)],
  ]
  return (
    <div data-testid={`campaign-analytics-${c.id}`} className="space-y-2">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        {rows.map(([k, v]) => (<div key={k}><dt className="text-xs text-gray-500">{k}</dt><dd>{v}</dd></div>))}
      </dl>
      {(c.by_placement || []).length ? (
        <p className="text-xs text-gray-500">By placement: {(c.by_placement || []).map((r: Json) =>
          `${r.key}: ${r.valid_impressions} (${r.spend} USD)`).join(' · ')}</p>
      ) : null}
      {(c.daily || []).length ? (
        <p className="text-xs text-gray-500">Daily spend: {(c.daily || []).map((d: Json) => `${d.day}: ${d.spent}`).join(' · ')}</p>
      ) : null}
    </div>
  )
}

const DISPLAY_TEXT: Record<string, string> = {
  DRAFT: 'Draft', SUBMITTED: 'Submitted for review', CHANGES_REQUIRED: 'Changes required', SCHEDULED: 'Approved — scheduled',
  ACTIVE: 'Active', PAUSED: 'Paused', ENDED: 'Ended', REJECTED: 'Rejected', CANCELLED: 'Cancelled',
}

function DailyReport({ campaignId }: { campaignId: number }) {
  const [report, setReport] = useState<Json | null>(null)
  const [error, setError] = useState('')
  const load = () => call('get', `/advertiser/campaigns/${campaignId}/daily-report`).then(setReport).catch((e) => setError(errorDetail(e)))
  if (!report) {
    return (<div className="text-xs">
      <button type="button" className="rounded border px-2 py-1" onClick={load}>Show daily report</button>
      {error ? <span className="ml-2 text-red-600">{error}</span> : null}
    </div>)
  }
  return (
    <div data-testid={`daily-report-${campaignId}`} className="space-y-2 overflow-x-auto text-xs">
      <table className="w-full">
        <thead className="text-left text-gray-500"><tr>{['Day (UTC)', 'Spend', 'Charged events', 'Other charges', 'Recognized']
          .map((h) => <th key={h} className="pr-3">{h}</th>)}</tr></thead>
        <tbody>{(report.daily || []).map((d: Json) => (
          <tr key={d.day} className="border-t border-gray-100 dark:border-gray-700">
            <td className="pr-3">{d.day}</td><td className="pr-3">{d.spend} USD</td><td className="pr-3">{d.charged_events}</td>
            <td className="pr-3">{d.direct_charges}</td><td className="pr-3">{d.recognized ? 'Yes' : 'Pending'}</td>
          </tr>))}</tbody>
      </table>
      <table className="w-full">
        <thead className="text-left text-gray-500"><tr>{['Day', 'Creative', 'Placement', 'Billing metric', 'Events', 'Charged']
          .map((h) => <th key={h} className="pr-3">{h}</th>)}</tr></thead>
        <tbody>{(report.activity || []).map((a: Json, i: number) => (
          <tr key={i} className="border-t border-gray-100 dark:border-gray-700">
            <td className="pr-3">{a.day}</td><td className="pr-3">#{a.creative_id}</td><td className="pr-3">{a.placement}</td>
            <td className="pr-3">{a.billing_metric}</td><td className="pr-3">{a.events}</td><td className="pr-3">{a.charged}</td>
          </tr>))}</tbody>
      </table>
      {(report.adjustments || []).length ? (
        <p>Adjustments (reversed invalid activity): {(report.adjustments || []).map((a: Json) =>
          `${a.day} ${a.billing_metric} ×${a.events} (−${a.reversed})`).join(' · ')}</p>
      ) : null}
      <p data-testid={`reconciliation-${campaignId}`} className={report.reconciliation?.ok ? 'text-green-700' : 'text-red-600'}>
        {report.reconciliation?.ok ? 'Reconciled' : 'Does not reconcile'}: campaign spend {report.reconciliation?.campaign_spent} =
        sum of days {report.reconciliation?.sum_of_days}. Remaining budget {report.remaining_budget} USD.</p>
    </div>
  )
}

export function AdvertiserDashboard() {
  const [data, setData] = useState<Json | null>(null)
  const [catalog, setCatalog] = useState<Json | null>(null)
  const [message, setMessage] = useState('')
  const [rename, setRename] = useState<Record<number, string>>({})
  const [creditUnits, setCreditUnits] = useState('10')
  const [formKey, setFormKey] = useState(0)

  const load = useCallback(async () => {
    try {
      const [overview, cat] = await Promise.all([call('get', '/advertiser/overview'), call('get', '/advertiser/catalog')])
      setData(overview)
      setCatalog(cat)
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
  const saved = (msg: string) => {
    setMessage(msg)
    load()
  }

  if (!data || !catalog) return <p className="text-sm text-gray-500">{message || 'Loading…'}</p>
  const pending = data.pricing_state !== 'CONFIGURED'
  return (
    <div className="space-y-6">
      {message ? <p role="status" className="rounded bg-gray-100 p-2 text-sm dark:bg-gray-700">{message}</p> : null}
      {pending ? (
        <p className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          MyHigh5 advertising prices are pending approval. You can prepare draft campaigns; they can be funded and
          submitted once prices are published.
        </p>
      ) : null}
      {!data.campaigns_enabled ? (
        <p data-testid="ad-not-open" className="rounded border border-gray-300 bg-gray-50 p-3 text-sm text-gray-700 dark:bg-gray-900 dark:text-gray-300">
          MyHigh5 campaigns are not open yet: drafts can be prepared, but nothing can be bought, submitted or shown.
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border p-3 dark:border-gray-700"><p className="text-xs text-gray-500">Available credit</p>
          <p className="text-xl font-semibold">{data.available_credit} USD</p></div>
        <div className="rounded-xl border p-3 dark:border-gray-700"><p className="text-xs text-gray-500">In active campaigns</p>
          <p className="text-xl font-semibold">{data.credit_in_campaigns} USD</p></div>
        <div className="rounded-xl border p-3 text-xs text-gray-600 dark:border-gray-700 dark:text-gray-300">{data.refund_policy}</div>
      </div>
      {data.funding_enabled && !pending ? (
        <div className="space-y-2">
          <p className="text-sm">Add credit from Payments using the product “MyHigh5 advertiser credit” (1 unit = 1.00 USD).</p>
          <label className="text-sm">Credit to add with earnings (USD)
            <input value={creditUnits} onChange={(e) => setCreditUnits(e.target.value.replace(/[^0-9]/g, ''))} aria-label="Credit to add with earnings"
              className="ml-2 w-24 rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          {Number(creditUnits) >= 1 ? <PayWithEarnings productCode="advertising_credit" quantity={Number(creditUnits)} onPaid={load} /> : null}
        </div>
      ) : null}

      <CampaignForm key={formKey} catalog={catalog} onCreated={(msg) => { setFormKey(formKey + 1); saved(msg) }} />

      <Packages packages={(data.packages || []).filter((p: Json) => !p.package_code || p.code === 'MYHIGH5_CPM_CAMPAIGN')} />

      <h2 className="font-semibold">Your campaigns</h2>
      {(data.campaigns || []).length === 0 ? <p className="text-sm text-gray-500">No campaigns yet.</p> : null}
      {(data.campaigns || []).map((c: Json) => {
        const editable = ['DRAFT', 'CHANGES_REQUESTED'].includes(c.status)
        const closed = ['COMPLETED', 'REJECTED', 'CANCELLED'].includes(c.status)
        const schedule: Json = c.schedule || {}
        return (
          <section key={c.id} data-testid={`campaign-${c.id}`}
            className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold">{c.name}</h3>
              <span data-testid={`campaign-status-${c.id}`} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs dark:bg-gray-700">
                {DISPLAY_TEXT[c.display_status] || STATUS_TEXT[c.status] || c.status}</span>
              <span className="text-xs text-gray-500">{FUNDING_TEXT[c.funding] || ''}</span>
            </div>
            <p>{c.package ? `${(catalog.packages || []).find((p: Json) => p.code === c.package)?.name || c.package} · ` : ''}
              Budget {c.budget_total} USD · daily limit {c.daily_cap ?? '—'}{c.cpm_rate_usd ? ` · CPM ${c.cpm_rate_usd} USD (fixed at submission)` : ''}
              {c.unit_rate_usd ? ` · rate ${c.unit_rate_usd} USD` : ''}</p>
            <p data-testid={`campaign-schedule-${c.id}`} className="text-xs text-gray-500">
              {schedule.starts_after_approval ? 'Starts after approval' : `Starts ${schedule.start_at_local || '—'}`}
              {' · '}Ends {schedule.end_at_local || '—'} ({schedule.timezone || 'UTC'})</p>
            {c.review_note || (c.review_issues || []).length ? (
              <div data-testid={`campaign-note-${c.id}`} className={c.status === 'CHANGES_REQUESTED' || c.status === 'REJECTED'
                ? 'text-amber-700 dark:text-amber-400' : 'text-gray-500'}>
                {c.review_note ? <p>Review: {c.review_note}</p> : null}
                {(c.review_issues || []).map((i: Json, n: number) => <p key={n}>{i.category}: {i.note || 'needs changes'}</p>)}
              </div>
            ) : null}
            {(c.non_delivery_reasons || []).length ? (
              <ul data-testid={`not-serving-${c.id}`} className="list-disc pl-5 text-xs text-amber-700 dark:text-amber-400">
                {(c.non_delivery_reasons || []).map((r: Json) => <li key={r.code}>Not serving: {r.message}</li>)}
              </ul>
            ) : null}
            <Analytics c={c} />
            <DailyReport campaignId={c.id} />

            <div className="space-y-2">
              {(c.creatives || []).filter((cr: Json) => cr.review_status !== 'ARCHIVED').map((cr: Json) => (
                <CreativeEditor key={`${cr.id}-${cr.review_status}`} campaignId={c.id} creative={cr} placements={c.placements}
                  closed={closed} onSaved={saved} />
              ))}
              {!closed ? <CreativeEditor key={`new-${c.id}-${(c.creatives || []).length}`} campaignId={c.id}
                placements={c.placements} onSaved={saved} /> : null}
            </div>

            {editable ? (
              <div className="flex flex-wrap items-center gap-2">
                <input placeholder="New campaign name" aria-label="New campaign name" value={rename[c.id] || ''}
                  onChange={(e) => setRename({ ...rename, [c.id]: e.target.value })} className="rounded border px-2 py-1 dark:bg-gray-900" />
                <button className="rounded border px-2 py-1" disabled={!rename[c.id]}
                  onClick={() => run(() => call('patch', `/advertiser/campaigns/${c.id}`, { name: rename[c.id] }), 'Campaign updated')}>Rename</button>
              </div>
            ) : null}

            <div className="flex flex-wrap gap-2">
              {editable ? <button className="rounded bg-blue-600 px-2 py-1 text-white disabled:opacity-50" disabled={pending || !data.campaigns_enabled}
                onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/submit`), 'Submitted for review')}>
                {c.status === 'CHANGES_REQUESTED' ? 'Resubmit for review' : 'Submit for review'}</button> : null}
              {['DRAFT', 'CHANGES_REQUESTED', 'PENDING_REVIEW'].includes(c.status) ? <button className="rounded border px-2 py-1"
                onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/cancel`), 'Campaign cancelled')}>Cancel campaign</button> : null}
              {c.status === 'ACTIVE' ? <button className="rounded border px-2 py-1"
                onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/pause`), 'Paused')}>Pause</button> : null}
              {c.status === 'PAUSED' ? <button className="rounded border px-2 py-1"
                onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/resume`), 'Resumed')}>Resume</button> : null}
              {['ACTIVE', 'PAUSED'].includes(c.status) ? <button className="rounded border px-2 py-1"
                onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/complete`), 'Campaign ended')}>End campaign</button> : null}
            </div>
            {editable ? <p className="text-xs text-gray-500">{catalog.launch}</p> : null}
          </section>
        )
      })}
    </div>
  )
}

function DailyEarnings() {
  const [rows, setRows] = useState<Json[] | null>(null)
  useEffect(() => {
    call('get', '/earnings/daily').then((r) => setRows(r.days || [])).catch(() => setRows([]))
  }, [])
  if (rows == null) return null
  return (
    <section data-testid="daily-earnings" className="overflow-x-auto rounded-xl border border-gray-200 p-4 dark:border-gray-700">
      <h2 className="mb-1 font-semibold">Daily estimates (not withdrawable)</h2>
      <p className="mb-2 text-xs text-gray-500">Estimated from valid MyHigh5 ads on your contest-entry pages at the entry&apos;s
        original rate. Google AdSense days show activity only until Google finalizes and pays the month.</p>
      {rows.length === 0 ? <p className="text-sm text-gray-500">No advertising activity in the last 31 days.</p> : (
        <table className="w-full text-xs sm:text-sm">
          <thead className="text-left text-gray-500"><tr>
            {['Day (UTC)', 'Role', 'Entry', 'Source', 'Rate', 'Valid impressions', 'Estimate', 'Status'].map((h) =>
              <th key={h} className="whitespace-nowrap py-1 pr-3">{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-gray-100 dark:border-gray-700">
                <td className="pr-3">{r.day}</td><td className="pr-3">{r.role === 'CREATIVE' ? 'Creative' : 'Direct sponsor'}</td>
                <td className="pr-3">#{r.contest_entry_id}</td><td className="pr-3">{r.source === 'MYHIGH5' ? 'MyHigh5 ads' : 'Google AdSense'}</td>
                <td className="pr-3">{r.rate ? `${(Number(r.rate) * 100).toFixed(0)}%` : '—'}</td><td className="pr-3">{r.valid_impressions}</td>
                <td className="pr-3">{r.estimated_amount ? `${r.estimated_amount} USD` : '—'}</td>
                <td className="pr-3">{r.status === 'ESTIMATED' ? 'Estimated' : r.status === 'AWAITING_GOOGLE' ? 'Awaiting Google' : 'Origin under review'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export function AdEarnings() {
  const [summary, setSummary] = useState<Json | null>(null)
  const [lines, setLines] = useState<Json[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([call('get', '/earnings/summary'), call('get', '/earnings/lines')])
      .then(([s, l]) => {
        setSummary(s)
        setLines(l.lines || [])
      })
      .catch((e) => setError(errorDetail(e)))
  }, [])
  if (!summary) return <p className="text-sm text-gray-500">{error || 'Loading…'}</p>
  const Card = ({ title, v }: { title: string; v: Json }) => (
    <div className="rounded-xl border border-gray-200 p-4 dark:border-gray-700">
      <h2 className="mb-2 font-semibold">{title}</h2>
      <dl className="grid grid-cols-2 gap-1 text-sm">
        <dt>Estimated (not withdrawable)</dt><dd>{v.estimated} USD</dd>
        <dt>Held (pending account link or review)</dt><dd>{v.held} USD</dd>
        <dt>Available</dt><dd>{v.available} USD</dd>
        <dt>Paid</dt><dd>{v.paid} USD</dd>
        <dt>Adjusted (superseded)</dt><dd>{v.adjustments_superseded} USD</dd>
        <dt className="text-amber-700 dark:text-amber-400">Missed — KYC not approved (not payable)</dt>
        <dd className="text-amber-700 dark:text-amber-400">{v.missed ?? '0.00'} USD</dd>
        {v.missed_estimated && v.missed_estimated !== '0.00' && (<>
          <dt className="text-amber-700 dark:text-amber-400">Estimated missed this period (not payable)</dt>
          <dd className="text-amber-700 dark:text-amber-400">{v.missed_estimated} USD</dd>
        </>)}
      </dl>
    </div>
  )
  return (
    <div className="space-y-6">
      <p className="text-sm text-gray-600 dark:text-gray-300">{summary.note}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="As the creative (20% personal submission / 10% nomination)" v={summary.creative} />
        <Card title="As the direct sponsor (1%)" v={summary.sponsor} />
      </div>
      <DailyEarnings />
      <MissedEarnings
        endpoint="/api/v1/advertising/earnings/missed"
        title="Missed advertising earnings — KYC Verification Required"
        emptyText="You have no missed advertising earnings."
      />
      <section className="overflow-x-auto rounded-xl border border-gray-200 p-4 dark:border-gray-700">
        <h2 className="mb-2 font-semibold">Monthly releases</h2>
        {lines.length === 0 ? <p className="text-sm text-gray-500">No released months yet.</p> : (
          <table className="w-full text-xs sm:text-sm">
            <thead className="text-left text-gray-500"><tr>
              {['Month', 'Role', 'Entry', 'Original type', 'Level', 'Source', 'Rate %', 'Amount', 'Status', 'Payout'].map((h) =>
                <th key={h} className="whitespace-nowrap py-1 pr-3">{h}</th>)}</tr></thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.id} className="border-t border-gray-100 dark:border-gray-700">
                  <td className="pr-3">{l.period}</td><td className="pr-3">{l.role}</td><td className="pr-3">#{l.contest_entry_id}</td>
                  <td className="pr-3">{l.original_submission_type || 'under review'}</td><td className="pr-3">{l.contest_level || '—'}</td>
                  <td className="pr-3">{l.source === 'MYHIGH5' ? 'MyHigh5 ads' : 'Google AdSense'}</td>
                  <td className="pr-3">{l.applied_percentage}</td><td className="pr-3">{l.amount} USD</td>
                  <td className="pr-3">{l.status === 'MISSED_KYC' ? 'Missed (KYC) — not payable' : l.status}</td><td className="pr-3">{l.payout_status || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
