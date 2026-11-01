'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'

type Json = Record<string, any>

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return typeof detail === 'string' ? detail : (detail as Json).message || JSON.stringify(detail)
  }
  return e instanceof Error ? e.message : 'Request failed'
}

async function call(method: 'get' | 'post', url: string, body?: unknown) {
  const res = await api.request({ method, url: `/api/v1/advertising${url}`, data: body })
  if (res.status >= 400) throw { response: res }
  return res.data
}

const PLACEMENTS: [string, string][] = [['IN_FEED', 'In-feed'], ['IN_CONTENT', 'Contest-entry pages'], ['SIDEBAR', 'Desktop sidebar']]

export function AdvertiserDashboard() {
  const [data, setData] = useState<Json | null>(null)
  const [message, setMessage] = useState('')
  const [form, setForm] = useState({ name: '', budget: '', daily_cap: '', start_at: '', end_at: '', countries: '',
    placements: ['IN_FEED'] as string[] })
  const [creative, setCreative] = useState<Record<number, Json>>({})

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

  if (!data) return <p className="text-sm text-gray-500">{message || 'Loading…'}</p>
  const pending = data.pricing_state !== 'CONFIGURED'
  return (
    <div className="space-y-6">
      {message ? <p className="rounded bg-gray-100 p-2 text-sm dark:bg-gray-700">{message}</p> : null}
      {pending ? (
        <p className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          MyHigh5 advertising prices are pending approval. You can prepare draft campaigns; they can be funded and
          submitted once prices are published.
        </p>
      ) : (
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Price: {data.cpm_rate_usd} USD per 1,000 valid, viewable impressions (at least half of the ad visible for one
          second). You are charged only for validated impressions.
        </p>
      )}
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

      <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 className="font-semibold">New campaign</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {([['name', 'Name', 'text'], ['budget', 'Total budget (USD)', 'number'], ['daily_cap', 'Daily limit (USD, optional)', 'number'],
            ['start_at', 'Start', 'datetime-local'], ['end_at', 'End', 'datetime-local'],
            ['countries', 'Countries (two-letter codes, optional)', 'text']] as const).map(([key, label, type]) => (
            <label key={key} className="text-sm">{label}
              <input type={type} value={(form as Json)[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          {PLACEMENTS.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2">
              <input type="checkbox" checked={form.placements.includes(key)}
                onChange={(e) => setForm({ ...form, placements: e.target.checked ? [...form.placements, key]
                  : form.placements.filter((p) => p !== key) })} />{label}
            </label>
          ))}
        </div>
        <button className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
          onClick={() => run(() => call('post', '/advertiser/campaigns', {
            name: form.name, budget: form.budget, daily_cap: form.daily_cap || null,
            start_at: form.start_at ? new Date(form.start_at).toISOString() : null,
            end_at: form.end_at ? new Date(form.end_at).toISOString() : null,
            placements: form.placements, countries: form.countries.split(',').map((c) => c.trim().toUpperCase()).filter(Boolean),
          }), 'Draft campaign created')}>Create draft</button>
      </section>

      {(data.campaigns || []).map((c: Json) => (
        <section key={c.id} className="space-y-2 rounded-xl border border-gray-200 bg-white p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="font-semibold">{c.name} — {c.status}</h3>
          <p>Budget {c.budget_total} USD · spent {c.spent} · remaining {c.remaining_budget} · daily limit {c.daily_cap ?? '—'} ·
            valid impressions {c.valid_impressions}{c.cpm_rate_usd ? ` · CPM ${c.cpm_rate_usd}` : ''}</p>
          {c.review_note ? <p className="text-gray-500">Review: {c.review_note}</p> : null}
          {(c.daily || []).length ? (
            <p className="text-gray-500">Daily spend: {(c.daily || []).map((d: Json) => `${d.day}: ${d.spent}`).join(' · ')}</p>
          ) : null}
          {c.status === 'DRAFT' ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {(['headline', 'body', 'image_url', 'destination_url'] as const).map((k) => (
                <input key={k} placeholder={k.replace('_', ' ')} value={creative[c.id]?.[k] || ''}
                  onChange={(e) => setCreative({ ...creative, [c.id]: { ...(creative[c.id] || {}), [k]: e.target.value } })}
                  className="rounded border px-2 py-1 dark:bg-gray-900" />
              ))}
              <button className="rounded border px-2 py-1"
                onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/creatives`, creative[c.id] || {}), 'Creative added')}>
                Add creative</button>
              <button className="rounded bg-blue-600 px-2 py-1 text-white" disabled={pending}
                onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/submit`), 'Submitted for review')}>
                Submit for review</button>
            </div>
          ) : null}
          <div className="flex gap-2">
            {c.status === 'ACTIVE' ? <button className="rounded border px-2 py-1"
              onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/pause`), 'Paused')}>Pause</button> : null}
            {c.status === 'PAUSED' ? <button className="rounded border px-2 py-1"
              onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/resume`), 'Resumed')}>Resume</button> : null}
            {['ACTIVE', 'PAUSED'].includes(c.status) ? <button className="rounded border px-2 py-1"
              onClick={() => run(() => call('post', `/advertiser/campaigns/${c.id}/complete`), 'Campaign stopped')}>Stop campaign</button> : null}
          </div>
        </section>
      ))}
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
                  <td className="pr-3">{l.status}</td><td className="pr-3">{l.payout_status || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
