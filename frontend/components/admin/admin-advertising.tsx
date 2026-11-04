'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'
import { AdPreview } from '@/components/dashboard/advertiser-dashboard'

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

function Section({ title, children, testId }: { title: string; children: React.ReactNode; testId?: string }) {
  return (
    <section data-testid={testId} className="space-y-3 overflow-x-auto rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
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
  ['advertiser_sponsor_commission_enabled', "Advertiser's direct sponsor 20%/40% on recognized charges"],
]
const ISSUE_CATEGORIES: [string, string][] = [['COPY', 'Copy'], ['MEDIA', 'Media'], ['DESTINATION', 'Destination'],
  ['PLACEMENT', 'Placement']]

function IssuePicker({ id, value, onChange }: { id: string; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <span className="flex flex-wrap items-center gap-2" data-testid={`issues-${id}`}>
      {ISSUE_CATEGORIES.map(([code, label]) => (
        <label key={code} className="flex items-center gap-1">
          <input type="checkbox" aria-label={`${label} issue for ${id}`} checked={value.includes(code)}
            onChange={(e) => onChange(e.target.checked ? [...value, code] : value.filter((x) => x !== code))} />{label}
        </label>
      ))}
    </span>
  )
}

export default function AdminAdvertising() {
  const [overview, setOverview] = useState<Json | null>(null)
  const [campaigns, setCampaigns] = useState<Json[]>([])
  const [origins, setOrigins] = useState<Json[]>([])
  const [recon, setRecon] = useState<Json | null>(null)
  const [suspicious, setSuspicious] = useState<Json | null>(null)
  const [message, setMessage] = useState<string>('')
  const [password, setPassword] = useState('')
  const [cpm, setCpm] = useState('')
  const [minBudget, setMinBudget] = useState('')
  const [period, setPeriod] = useState('')
  const [adsenseTotal, setAdsenseTotal] = useState('')
  const [evidence, setEvidence] = useState('')
  const [notes, setNotes] = useState<Record<string, string>>({})

  const note = (key: string) => (notes[key] || '').trim()
  const setNote = (key: string, value: string) => setNotes((n) => ({ ...n, [key]: value }))
  const [issues, setIssues] = useState<Record<string, string[]>>({})
  const picked = (key: string) => issues[key] || []
  const issueBody = (key: string) => picked(key).map((category) => ({ category, note: note(key) }))

  const load = useCallback(async () => {
    try {
      const [o, c, g, r, s] = await Promise.all([call('get', '/overview'), call('get', '/campaigns'), call('get', '/origins'),
        call('get', '/reconciliation'), call('get', '/suspicious')])
      setOverview(o)
      setCampaigns(c.campaigns || [])
      setOrigins(g.origins || [])
      setRecon(r)
      setSuspicious(s)
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
  const policy = overview?.approved_policy || {}
  const originStats = overview?.origins || {}
  return (
    <div className="space-y-6">
      {message ? <p role="status" className="rounded bg-gray-100 p-2 text-sm dark:bg-gray-700">{message}</p> : null}
      <label className="block text-sm">
        Current password (required for prices, switches, finalization, origin decisions and scans)
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full max-w-sm rounded border px-2 py-1 dark:bg-gray-900" autoComplete="current-password" />
      </label>

      <Section title={`Pricing and switches — ${s.pricing_state || ''}`} testId="adv-pricing">
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Approved policy: CPM {policy.cpm_rate_usd ?? '—'} USD per 1,000 valid impressions, minimum campaign budget{' '}
          {policy.min_campaign_budget_usd ?? '—'} USD. A campaign keeps the CPM it was submitted with. Every money switch
          below stays off until the owner activates it.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">CPM (USD per 1,000 valid viewable impressions)
            <input value={cpm} onChange={(e) => setCpm(e.target.value)} className="mt-1 block rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <label className="text-sm">Minimum campaign budget (USD)
            <input value={minBudget} onChange={(e) => setMinBudget(e.target.value)} className="mt-1 block rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <button className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
            onClick={() => run(() => call('put', '/settings', { changes: { cpm_rate_usd: cpm || null, min_campaign_budget_usd: minBudget || null },
              current_password: password }), 'Prices saved')}>Save prices</button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {MONEY_SWITCHES.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!s[key]} data-testid={`adv-switch-${key}`}
                onChange={(e) => run(() => call('put', '/settings', { changes: { [key]: e.target.checked }, current_password: password }),
                  `${label}: ${e.target.checked ? 'on' : 'off'}`)} />
              {label}: {s[key] ? 'ON' : 'OFF'}
            </label>
          ))}
        </div>
      </Section>

      <Section title="Advertising products" testId="adv-packages">
        <Table rows={(overview?.packages || []).map((p: Json) => ({ ...p, purchasable: p.purchasable ? 'yes' : 'no' }))}
          cols={['name', 'type', 'price', 'minimum_budget', 'state', 'purchasable']} />
      </Section>

      <Section title="Campaigns" testId="adv-campaigns">
        {campaigns.length === 0 ? <p className="text-sm text-gray-500">No campaigns.</p> : null}
        {campaigns.map((c) => (
          <div key={c.id} data-testid={`adv-campaign-${c.id}`} className="space-y-2 rounded border border-gray-200 p-3 text-sm dark:border-gray-700">
            <p className="font-medium">#{c.id} {c.name} — {c.display_status || c.status} — advertiser #{c.advertiser_user_id} — budget {c.budget_total} USD,
              spent {c.spent}, remaining {c.remaining_budget}, CPM {c.cpm_rate_usd ?? '—'}, funding {c.funding}</p>
            <p className="text-xs text-gray-500">Placements {(c.placements || []).join(', ')} · targeting {JSON.stringify(c.targeting || {})} ·
              {' '}{c.start_at} → {c.end_at} · served {c.served_impressions}, valid {c.valid_impressions}, rejected {c.invalid_events}</p>
            {c.schedule ? <p className="text-xs text-gray-500">Schedule ({c.schedule.timezone}): {c.schedule.starts_after_approval
              ? 'starts at approval' : c.schedule.start_at_local} → {c.schedule.end_at_local}</p> : null}
            {c.review_note ? <p className="text-xs text-gray-500">Review note: {c.review_note}</p> : null}
            {(c.review_issues || []).length ? <p className="text-xs text-amber-700">Open issues: {(c.review_issues || [])
              .map((i: Json) => i.category).join(', ')}</p> : null}
            {(c.creatives || []).filter((cr: Json) => cr.review_status !== 'ARCHIVED').map((cr: Json) => (
              <div key={cr.id} className="space-y-1">
                <p className="text-xs">Creative #{cr.id}: {cr.review_status}
                  {cr.supersedes_creative_id ? ` · new version of #${cr.supersedes_creative_id} (the approved version keeps serving until this one is approved)` : ''}
                  {cr.display_name ? ` · advertiser "${cr.display_name}"` : ''}{cr.cta_label ? ` · CTA ${cr.cta_label}` : ''}
                  {cr.destination_domain ? ` · ${cr.destination_domain}` : ''}
                  {cr.image ? ` · image ${cr.image.mime} ${cr.image.width}×${cr.image.height}` : ''}
                  {cr.video ? ` · video ${cr.video.width}×${cr.video.height}, ${Math.round((cr.video.duration_ms || 0) / 1000)} s` : ''}</p>
                <AdPreview creative={cr} placements={c.placements} />
                {cr.review_status === 'PENDING' ? (
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <button className="rounded bg-green-600 px-2 py-0.5 text-white"
                      onClick={() => run(() => call('post', `/creatives/${cr.id}/review`, { approve: true, note: 'approved' }), 'Creative approved')}>Approve</button>
                    <IssuePicker id={`creative ${cr.id}`} value={picked(`cr${cr.id}`)} onChange={(v) => setIssues((x) => ({ ...x, [`cr${cr.id}`]: v }))} />
                    <input placeholder="Reason to reject" aria-label={`Reason to reject creative ${cr.id}`} value={notes[`cr${cr.id}`] || ''}
                      onChange={(e) => setNote(`cr${cr.id}`, e.target.value)} className="rounded border px-2 py-0.5 dark:bg-gray-900" />
                    <button className="rounded bg-red-600 px-2 py-0.5 text-white disabled:opacity-50"
                      disabled={!note(`cr${cr.id}`) && !picked(`cr${cr.id}`).length}
                      onClick={() => run(() => call('post', `/creatives/${cr.id}/review`, { approve: false, note: note(`cr${cr.id}`),
                        issues: issueBody(`cr${cr.id}`) }), 'Creative rejected')}>Reject</button>
                  </div>
                ) : null}
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-2">
              {c.status === 'PENDING_REVIEW' ? (
                <>
                  <button className="rounded bg-green-600 px-2 py-0.5 text-white"
                    onClick={() => run(() => call('post', `/campaigns/${c.id}/review`, { approve: true, note: 'approved' }), 'Campaign approved')}>Approve campaign</button>
                  <input placeholder="Reason or requested changes" aria-label={`Note for campaign ${c.id}`} value={notes[`c${c.id}`] || ''}
                    onChange={(e) => setNote(`c${c.id}`, e.target.value)} className="rounded border px-2 py-0.5 dark:bg-gray-900" />
                  <IssuePicker id={`campaign ${c.id}`} value={picked(`c${c.id}`)} onChange={(v) => setIssues((x) => ({ ...x, [`c${c.id}`]: v }))} />
                  <button className="rounded border px-2 py-0.5 disabled:opacity-50"
                    disabled={note(`c${c.id}`).length < 3 && !picked(`c${c.id}`).length}
                    onClick={() => run(() => call('post', `/campaigns/${c.id}/request-changes`, { note: note(`c${c.id}`),
                      issues: issueBody(`c${c.id}`) }), 'Changes requested')}>Request changes</button>
                  <button className="rounded bg-red-600 px-2 py-0.5 text-white disabled:opacity-50" disabled={!note(`c${c.id}`)}
                    onClick={() => run(() => call('post', `/campaigns/${c.id}/review`, { approve: false, note: note(`c${c.id}`) }), 'Campaign rejected')}>Reject campaign</button>
                </>
              ) : null}
              {c.status === 'ACTIVE' ? (
                <button className="rounded bg-gray-600 px-2 py-0.5 text-white"
                  onClick={() => run(() => call('post', `/campaigns/${c.id}/pause`), 'Campaign paused')}>Pause</button>
              ) : null}
              {c.status === 'PAUSED' ? (
                <button className="rounded border px-2 py-0.5"
                  onClick={() => run(() => call('post', `/campaigns/${c.id}/resume`), 'Campaign resumed')}>Resume</button>
              ) : null}
            </div>
          </div>
        ))}
      </Section>

      <Section title={`Advertising reconciliation — ${recon ? (recon.ok ? 'balanced' : 'MISMATCH') : '…'}`} testId="adv-reconciliation">
        <Table rows={(recon?.checks || []).map((c: Json) => ({ ...c, ok: c.ok ? 'ok' : 'MISMATCH' }))}
          cols={['check', 'expected', 'actual', 'ok', 'detail']} />
      </Section>

      <Section title="Impressions, suspicious activity and allocations" testId="adv-suspicious">
        <p className="text-sm">Impression events: {JSON.stringify(overview?.impression_events || {})}</p>
        <p className="text-sm">Rejected events by reason: {JSON.stringify(suspicious?.invalid_by_reason || {})}; reversed after
          charging: {suspicious?.reversed_events ?? 0}</p>
        <Table rows={(suspicious?.recent || []).slice(0, 20)} cols={['id', 'event_type', 'reason', 'received_at', 'is_bot_ua']} />
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

      <Section title={`Original submission type — ${originStats.under_review ?? 0} under review`} testId="adv-origins">
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Active entries {originStats.active_entries ?? '—'} · not yet classified {originStats.unscanned ?? '—'} · decided from
          records {originStats.resolved ?? 0} {JSON.stringify(originStats.resolved_by_kind || {})}. Classification uses only the
          submission records; anything not provable is held for a decision here, and the revenue of a held entry is never
          shared until then. A decision is final.
        </p>
        <button className="rounded border px-3 py-1 text-sm"
          onClick={() => run(() => call('post', '/origins/scan', { limit: 500, current_password: password }),
            'Entries classified from their records')}>Classify unscanned entries (500)</button>
        {origins.map((o) => (
          <div key={o.contestant_id} data-testid={`adv-origin-${o.contestant_id}`} className="space-y-1 rounded border border-gray-100 p-2 text-sm dark:border-gray-700">
            <p>Entry #{o.contestant_id} “{o.title || '—'}” · owner #{o.owner_user_id} · entry type {o.entry_type} · contest
              {' '}{o.contest_name || '—'} ({o.contest_mode || 'no contest link'}) · registered {o.registration_date || '—'}</p>
            <p className="text-xs text-gray-500">Evidence: {JSON.stringify(o.evidence)}</p>
            <div className="flex flex-wrap items-center gap-2">
              <input placeholder="Evidence for the decision" aria-label={`Evidence for entry ${o.contestant_id}`}
                value={notes[`o${o.contestant_id}`] || ''} onChange={(e) => setNote(`o${o.contestant_id}`, e.target.value)}
                className="min-w-[16rem] rounded border px-2 py-0.5 dark:bg-gray-900" />
              {(['PERSONAL_SUBMISSION', 'NOMINATION'] as const).map((kind) => (
                <button key={kind} className="rounded border px-2 py-0.5 disabled:opacity-50" disabled={note(`o${o.contestant_id}`).length < 3}
                  onClick={() => run(() => call('post', `/origins/${o.contestant_id}/resolve`, { origin_kind: kind,
                    note: note(`o${o.contestant_id}`), current_password: password }), 'Origin resolved')}>
                  {kind === 'PERSONAL_SUBMISSION' ? 'Personal submission (20%)' : 'Nomination (10%)'}</button>
              ))}
            </div>
          </div>
        ))}
      </Section>

      <Section title="Google AdSense reconciliation">
        <p className="text-sm">
          Missing credentials: {(overview?.adsense?.credentials_missing || []).join(', ') || 'none'}. Without them nothing is imported;
          no AdSense earnings are ever invented. AdSense revenue sharing stays off until the policy is confirmed.
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
