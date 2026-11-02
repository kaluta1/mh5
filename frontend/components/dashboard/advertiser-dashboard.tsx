'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'
import { normalizeMediaUrl } from '@/lib/media-url'
import { MissedEarnings } from '@/components/dashboard/missed-earnings'

type Json = Record<string, any>

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return typeof detail === 'string' ? detail : (detail as Json).message || JSON.stringify(detail)
  }
  return e instanceof Error ? e.message : 'Request failed'
}

async function call(method: 'get' | 'post' | 'patch', url: string, body?: unknown) {
  const res = await api.request({ method, url: `/api/v1/advertising${url}`, data: body })
  if (res.status >= 400) throw { response: res }
  return res.data
}

const PLACEMENTS: [string, string][] = [['IN_FEED', 'In-feed'], ['IN_CONTENT', 'Contest-entry pages'], ['SIDEBAR', 'Desktop sidebar']]
const PAGE_TYPES: [string, string][] = [['CONTEST_LISTING', 'Contest listings'], ['CONTEST_ENTRY', 'Contest-entry pages'],
  ['FEED', 'Feeds'], ['DISCOVERY', 'Discovery']]
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

export function AdPreview({ creative }: { creative: Json }) {
  const image = normalizeMediaUrl(creative.image_url)
  return (
    <div data-testid="ad-preview" className="max-w-sm rounded-lg border border-gray-200 bg-white p-3 text-sm dark:border-gray-700 dark:bg-gray-900">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Sponsored</p>
      <div className="flex items-start gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {image ? <img src={image} alt="" className="h-16 w-16 flex-shrink-0 rounded object-cover" /> : null}
        <div className="min-w-0">
          <p className="truncate font-semibold">{creative.headline || 'Headline'}</p>
          {creative.body ? <p className="line-clamp-2 text-gray-600 dark:text-gray-300">{creative.body}</p> : null}
          <p className="truncate text-xs text-blue-600">{creative.destination_url || 'https://'}</p>
        </div>
      </div>
    </div>
  )
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

export function AdvertiserDashboard() {
  const [data, setData] = useState<Json | null>(null)
  const [message, setMessage] = useState('')
  const [form, setForm] = useState({ name: '', budget: '', daily_cap: '', start_at: '', end_at: '', countries: '',
    placements: ['IN_FEED'] as string[], page_types: [] as string[] })
  const [creative, setCreative] = useState<Record<number, Json>>({})
  const [rename, setRename] = useState<Record<number, string>>({})

  const load = useCallback(async () => {
    try {
      setData(await call('get', '/advertiser/overview'))
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

  const upload = (campaignId: number, creativeId: number, file: File | undefined) => {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    run(() => call('post', `/advertiser/campaigns/${campaignId}/creatives/${creativeId}/image`, fd), 'Image uploaded; the creative goes back to review')
  }

  if (!data) return <p className="text-sm text-gray-500">{message || 'Loading…'}</p>
  const pending = data.pricing_state !== 'CONFIGURED'
  const estimate = estimateImpressions(form.budget, data.cpm_rate_usd)
  const belowMinimum = Boolean(data.min_campaign_budget_usd && form.budget
    && Number(form.budget) < Number(data.min_campaign_budget_usd))
  return (
    <div className="space-y-6">
      {message ? <p role="status" className="rounded bg-gray-100 p-2 text-sm dark:bg-gray-700">{message}</p> : null}
      {pending ? (
        <p className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          MyHigh5 advertising prices are pending approval. You can prepare draft campaigns; they can be funded and
          submitted once prices are published.
        </p>
      ) : (
        <p data-testid="ad-price" className="text-sm text-gray-600 dark:text-gray-300">
          Price: {data.cpm_rate_usd} USD per 1,000 valid, viewable impressions (at least half of the ad visible for one
          second). Minimum campaign budget: {data.min_campaign_budget_usd ?? '—'} USD. You are charged only for validated impressions.
        </p>
      )}
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
        <p className="text-sm">Add credit from Payments using the product “MyHigh5 advertiser credit” (1 unit = 1.00 USD).</p>
      ) : null}

      <Packages packages={data.packages || []} />

      <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 className="font-semibold">New campaign</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {([['name', 'Name', 'text'], ['budget', 'Total budget (USD)', 'number'], ['daily_cap', 'Daily limit (USD, optional)', 'number'],
            ['start_at', 'Start', 'datetime-local'], ['end_at', 'End', 'datetime-local'],
            ['countries', 'Countries (two-letter codes, optional)', 'text']] as const).map(([key, label, type]) => (
            <label key={key} className="text-sm">{label}
              <input type={type} value={(form as Json)[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                aria-label={label} className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
            </label>
          ))}
        </div>
        <p data-testid="ad-estimate" className="text-sm text-gray-600 dark:text-gray-300">
          {estimate != null
            ? `Up to ${estimate.toLocaleString('en-US')} billable impressions at ${data.cpm_rate_usd} USD CPM (an estimate, not a delivery promise).`
            : 'Enter a budget to see the estimated number of billable impressions.'}
          {belowMinimum ? <span className="ml-1 text-red-600">The minimum campaign budget is {data.min_campaign_budget_usd} USD.</span> : null}
        </p>
        <fieldset className="flex flex-wrap gap-4 text-sm"><legend className="mb-1 w-full text-xs text-gray-500">Placements</legend>
          {PLACEMENTS.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2">
              <input type="checkbox" checked={form.placements.includes(key)}
                onChange={(e) => setForm({ ...form, placements: e.target.checked ? [...form.placements, key]
                  : form.placements.filter((p) => p !== key) })} />{label}
            </label>
          ))}
        </fieldset>
        <fieldset className="flex flex-wrap gap-4 text-sm"><legend className="mb-1 w-full text-xs text-gray-500">Pages (none = every eligible page)</legend>
          {PAGE_TYPES.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2">
              <input type="checkbox" checked={form.page_types.includes(key)}
                onChange={(e) => setForm({ ...form, page_types: e.target.checked ? [...form.page_types, key]
                  : form.page_types.filter((p) => p !== key) })} />{label}
            </label>
          ))}
        </fieldset>
        <button className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50" disabled={belowMinimum}
          onClick={() => run(() => call('post', '/advertiser/campaigns', {
            name: form.name, budget: form.budget, daily_cap: form.daily_cap || null,
            start_at: form.start_at ? new Date(form.start_at).toISOString() : null,
            end_at: form.end_at ? new Date(form.end_at).toISOString() : null,
            placements: form.placements, page_types: form.page_types,
            countries: form.countries.split(',').map((c) => c.trim().toUpperCase()).filter(Boolean),
          }), 'Draft campaign created')}>Create draft</button>
      </section>

      <h2 className="font-semibold">Your campaigns</h2>
      {(data.campaigns || []).length === 0 ? <p className="text-sm text-gray-500">No campaigns yet.</p> : null}
      {(data.campaigns || []).map((c: Json) => {
        const editable = ['DRAFT', 'CHANGES_REQUESTED'].includes(c.status)
        const draftCreative = creative[c.id] || {}
        return (
          <section key={c.id} data-testid={`campaign-${c.id}`}
            className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold">{c.name}</h3>
              <span data-testid={`campaign-status-${c.id}`} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs dark:bg-gray-700">
                {STATUS_TEXT[c.status] || c.status}</span>
              <span className="text-xs text-gray-500">{FUNDING_TEXT[c.funding] || ''}</span>
            </div>
            <p>Budget {c.budget_total} USD · daily limit {c.daily_cap ?? '—'}{c.cpm_rate_usd ? ` · CPM ${c.cpm_rate_usd} USD (fixed at submission)` : ''}
              {c.estimated_impressions != null ? ` · up to ${c.estimated_impressions.toLocaleString('en-US')} impressions` : ''}</p>
            {c.review_note ? <p data-testid={`campaign-note-${c.id}`} className={c.status === 'CHANGES_REQUESTED' || c.status === 'REJECTED'
              ? 'text-amber-700 dark:text-amber-400' : 'text-gray-500'}>Review: {c.review_note}</p> : null}
            <Analytics c={c} />

            <div className="space-y-2">
              {(c.creatives || []).map((cr: Json) => (
                <div key={cr.id} className="flex flex-wrap items-start gap-3 rounded border border-gray-100 p-2 dark:border-gray-700">
                  <AdPreview creative={cr} />
                  <div className="space-y-1 text-xs">
                    <p>Review: {cr.review_status}{cr.review_note && cr.review_status === 'REJECTED' ? ` — ${cr.review_note}` : ''}</p>
                    {cr.image ? <p>Image {cr.image.width}×{cr.image.height}, {Math.round((cr.image.bytes || 0) / 1024)} KB</p> : null}
                    {!['COMPLETED', 'REJECTED', 'CANCELLED'].includes(c.status) ? (
                      <label className="block">Upload image (JPEG, PNG, WebP or GIF, up to 2 MB, 100–4000 px)
                        <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" aria-label={`Upload image for creative ${cr.id}`}
                          onChange={(e) => upload(c.id, cr.id, e.target.files?.[0])} className="mt-1 block text-xs" />
                      </label>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>

            {editable ? (
              <div className="space-y-2 rounded border border-dashed border-gray-300 p-2 dark:border-gray-600">
                <p className="text-xs font-medium">Add a creative</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {([['headline', 'Headline'], ['body', 'Text (optional)'], ['destination_url', 'Destination URL (https://…)'],
                    ['image_url', 'Image URL (https, optional — or upload after adding)']] as const).map(([k, label]) => (
                    <input key={k} placeholder={label} aria-label={label} value={draftCreative[k] || ''}
                      onChange={(e) => setCreative({ ...creative, [c.id]: { ...draftCreative, [k]: e.target.value } })}
                      className="rounded border px-2 py-1 dark:bg-gray-900" />
                  ))}
                </div>
                {draftCreative.headline || draftCreative.destination_url ? <AdPreview creative={draftCreative} /> : null}
                <button className="rounded border px-2 py-1"
                  onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/creatives`, {
                    headline: draftCreative.headline || '', body: draftCreative.body || null,
                    image_url: draftCreative.image_url || null, destination_url: draftCreative.destination_url || '',
                  }), 'Creative added')}>Add creative</button>
                <div className="flex flex-wrap items-center gap-2">
                  <input placeholder="New campaign name" aria-label="New campaign name" value={rename[c.id] || ''}
                    onChange={(e) => setRename({ ...rename, [c.id]: e.target.value })} className="rounded border px-2 py-1 dark:bg-gray-900" />
                  <button className="rounded border px-2 py-1" disabled={!rename[c.id]}
                    onClick={() => run(() => call('patch', `/advertiser/campaigns/${c.id}`, { name: rename[c.id] }), 'Campaign updated')}>Rename</button>
                </div>
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
                onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/complete`), 'Campaign stopped')}>Stop campaign</button> : null}
            </div>
          </section>
        )
      })}
    </div>
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
