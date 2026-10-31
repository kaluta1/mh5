'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'

type Json = Record<string, any>
const BASE = '/api/v1/admin/seller-verification'
const STATUSES = ['', 'MANUAL_REVIEW_REQUIRED', 'CHECKS_IN_PROGRESS', 'ACTION_REQUIRED', 'APPROVED', 'REJECTED', 'RESTRICTED',
  'REVERIFICATION_REQUIRED', 'DRAFT', 'SUPERSEDED']
const ACTIONS: [string, string][] = [['approve', 'Approve'], ['request_correction', 'Request corrections'], ['reject', 'Reject'],
  ['restrict', 'Restrict selling'], ['request_reverification', 'Request reverification']]

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail)
  }
  return e instanceof Error ? e.message : 'Request failed'
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 overflow-x-auto rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <h2 className="font-semibold text-gray-900 dark:text-white">{title}</h2>
      {children}
    </section>
  )
}

function cell(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join(', ')
  if (v && typeof v === 'object') return JSON.stringify(v)
  return String(v ?? '')
}

function Table({ rows, cols, onRow }: { rows: Json[]; cols: string[]; onRow?: (r: Json) => void }) {
  if (!rows.length) return <p className="text-sm text-gray-500">No rows.</p>
  return (
    <table className="w-full text-xs sm:text-sm">
      <thead className="text-left text-gray-500"><tr>{cols.map((c) => <th key={c} className="whitespace-nowrap py-1 pr-3">{c}</th>)}</tr></thead>
      <tbody className="text-gray-800 dark:text-gray-200">
        {rows.map((r, i) => (
          <tr key={i} className={`border-t border-gray-100 align-top dark:border-gray-700 ${onRow ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40' : ''}`}
              onClick={onRow ? () => onRow(r) : undefined}>
            {cols.map((c) => <td key={c} className="py-1 pr-3">{cell(r[c])}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const input = 'w-full rounded-md border border-gray-300 bg-white px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-900'

function Detail({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [app, setApp] = useState<Json | null>(null)
  const [action, setAction] = useState('approve')
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState('')
  const [grace, setGrace] = useState(0)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    try { setApp((await api.get(`${BASE}/applications/${id}`)).data) } catch (e) { setError(errorDetail(e)) }
  }, [id])
  useEffect(() => { load() }, [load])

  const decide = async () => {
    setError('')
    try {
      setApp((await api.post(`${BASE}/applications/${id}/decision`, {
        action, reason, seller_message: message || null, grace_days: grace })).data)
      setReason(''); setMessage(''); onChanged(); load()
    } catch (e) { setError(errorDetail(e)) }
  }
  const retry = async () => {
    setError('')
    try { await api.post(`${BASE}/applications/${id}/retry-checks`); load(); onChanged() } catch (e) { setError(errorDetail(e)) }
  }
  const openDocument = async (docId: number, name: string) => {
    try {
      const response = await api.get(`${BASE}/documents/${docId}`, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data as Blob)
      const a = document.createElement('a')
      a.href = url; a.download = name; a.click()
      URL.revokeObjectURL(url)
    } catch (e) { setError(errorDetail(e)) }
  }

  if (!app) return error ? <p className="text-sm text-red-600">{error}</p> : <p className="text-sm text-gray-500">Loading…</p>
  const fields = ['user_id', 'status', 'seller_category', 'business_structure', 'legal_name', 'trading_name', 'residence_country',
    'establishment_country', 'establishment_subdivision', 'customer_markets', 'business_address', 'contact_phone', 'product_categories',
    'products_description', 'commercial_indicators', 'registration_authority', 'registration_number', 'exemption_basis',
    'tax_registered', 'tax_identifier_masked', 'licences', 'representative', 'ownership', 'declaration_accepted_at', 'submitted_at',
    'appeal_text', 'correction_request', 'decision_reason']
  const needsMessage = action !== 'approve'
  return (
    <Section title={`Application #${app.id}`}>
      <p className="text-xs text-gray-500">
        Approval permits selling on MyHigh5 only. It is not government registration, tax registration or a licence.
      </p>
      <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        {fields.map((f) => (<div key={f} className="flex gap-2"><dt className="w-48 shrink-0 text-gray-500">{f}</dt><dd className="break-all">{cell(app[f])}</dd></div>))}
      </dl>
      <div><p className="text-sm font-medium">Review reasons</p><p className="text-xs">{cell(app.review_reasons) || 'None'}</p></div>
      <div><p className="text-sm font-medium">Applicable rules</p>
        <Table rows={app.applicable_rule_details || []} cols={['rule_code', 'version', 'jurisdiction', 'scope', 'rule_kind', 'title', 'official_source_url']} /></div>
      <div><p className="text-sm font-medium">Verification results</p>
        <Table rows={app.checks || []} cols={['check_type', 'provider', 'status', 'result_code', 'attempts', 'last_error', 'checked_at']} />
        <button className="mt-1 text-xs text-blue-600 underline" onClick={retry}>Retry automated checks</button></div>
      <div><p className="text-sm font-medium">Documents (each view is audited)</p>
        {(app.documents || []).length === 0 ? <p className="text-xs text-gray-500">None.</p> : (
          <ul className="text-xs">{app.documents.map((d: Json) => (
            <li key={d.id}><button className="text-blue-600 underline" onClick={() => openDocument(d.id, d.file_name)}>{d.doc_type}: {d.file_name}</button>
              {d.expires_on ? ` (expires ${d.expires_on})` : ''}</li>))}</ul>)}</div>
      <div><p className="text-sm font-medium">History and corrections</p>
        <Table rows={app.events || []} cols={['at', 'from_status', 'to_status', 'actor_role', 'actor_user_id', 'reason', 'seller_message']} /></div>
      <div><p className="text-sm font-medium">Previous decisions</p>
        <Table rows={app.previous_applications || []} cols={['id', 'status', 'decided_at', 'decision_reason']} /></div>
      <div className="space-y-2 rounded-md border border-gray-200 p-3 dark:border-gray-700">
        <p className="text-sm font-medium">Decision</p>
        <select aria-label="Action" className={input} value={action} onChange={(e) => setAction(e.target.value)}>
          {ACTIONS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <textarea aria-label="Internal reason" className={input} rows={2} placeholder="Internal reason (required, audited, never shown to the seller)"
                  value={reason} onChange={(e) => setReason(e.target.value)} />
        <textarea aria-label="Message to the seller" className={input} rows={2}
                  placeholder={needsMessage ? 'Message to the seller (required). Do not include fraud indicators.' : 'Message to the seller (optional)'}
                  value={message} onChange={(e) => setMessage(e.target.value)} />
        {action === 'request_reverification' && (
          <label className="flex items-center gap-2 text-xs">Days the seller may keep selling meanwhile (0-60)
            <input type="number" min={0} max={60} className="w-20 rounded border px-1" value={grace}
                   onChange={(e) => setGrace(Number(e.target.value) || 0)} /></label>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="rounded-md bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
                disabled={reason.trim().length < 5 || (needsMessage && !message.trim())} onClick={decide}>Record decision</button>
      </div>
    </Section>
  )
}

function Rules() {
  const [data, setData] = useState<Json | null>(null)
  const [editing, setEditing] = useState<Json | null>(null)
  const [form, setForm] = useState({ official_source_url: '', last_reviewed_on: '', effective_from: '', note: '' })
  const [error, setError] = useState('')
  const load = useCallback(async () => { try { setData((await api.get(`${BASE}/rules`)).data) } catch (e) { setError(errorDetail(e)) } }, [])
  useEffect(() => { load() }, [load])
  const seed = async () => { try { await api.post(`${BASE}/rules/seed-defaults`); load() } catch (e) { setError(errorDetail(e)) } }
  const activate = async () => {
    if (!editing) return
    try { await api.post(`${BASE}/rules/${editing.id}/activate`, form); setEditing(null); load() } catch (e) { setError(errorDetail(e)) }
  }
  const retire = async (rule: Json) => {
    const note = form.note.trim()
    if (note.length < 10) { setError('Write a note of at least 10 characters in the note field first.'); return }
    try { await api.post(`${BASE}/rules/${rule.id}/retire`, { note }); load() } catch (e) { setError(errorDetail(e)) }
  }
  return (
    <Section title="Jurisdiction rules">
      <p className="text-xs text-gray-500">
        LEGAL rules start as DRAFT and are used for automatic decisions only after you confirm the current law against the official source.
        A business seller in a country without an ACTIVE legal registration rule always goes to manual review.
      </p>
      <p className="text-xs">Connected providers: {cell(data?.connected_providers)}</p>
      <button className="rounded-md border px-3 py-1 text-sm" onClick={seed}>Add default rule catalogue (missing rules only)</button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Table rows={data?.rules || []} cols={['id', 'rule_code', 'version', 'jurisdiction', 'scope', 'rule_kind', 'status', 'effective_from', 'last_reviewed_on', 'official_source_url']}
             onRow={(r) => { setEditing(r); setForm((f) => ({ ...f, official_source_url: r.official_source_url || '' })) }} />
      {editing && (
        <div className="space-y-2 rounded-md border border-gray-200 p-3 dark:border-gray-700">
          <p className="text-sm font-medium">{editing.rule_code} v{editing.version} ({editing.status})</p>
          <p className="text-xs">{editing.description}</p>
          <input aria-label="Official source" className={input} placeholder="https://official source" value={form.official_source_url}
                 onChange={(e) => setForm({ ...form, official_source_url: e.target.value })} />
          <label className="block text-xs">Reviewed on <input type="date" className={input} value={form.last_reviewed_on}
                 onChange={(e) => setForm({ ...form, last_reviewed_on: e.target.value })} /></label>
          <label className="block text-xs">Effective from <input type="date" className={input} value={form.effective_from}
                 onChange={(e) => setForm({ ...form, effective_from: e.target.value })} /></label>
          <textarea aria-label="Review note" className={input} rows={2} placeholder="What was checked and by whom"
                    value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <div className="flex gap-2">
            <button className="rounded-md bg-blue-600 px-3 py-1 text-sm text-white" onClick={activate}>Activate</button>
            <button className="rounded-md border px-3 py-1 text-sm" onClick={() => retire(editing)}>Retire</button>
            <button className="px-3 py-1 text-sm" onClick={() => setEditing(null)}>Close</button>
          </div>
        </div>
      )}
    </Section>
  )
}

function Monitoring() {
  const [reviews, setReviews] = useState<Json[]>([])
  const [preview, setPreview] = useState<Json | null>(null)
  const [result, setResult] = useState<Json | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    try { setReviews((await api.get(`${BASE}/classification-reviews`)).data) } catch (e) { setError(errorDetail(e)) }
  }, [])
  useEffect(() => { load() }, [load])
  const run = async () => { try { setResult((await api.post(`${BASE}/monitoring/run`)).data); load() } catch (e) { setError(errorDetail(e)) } }
  const resolve = async (id: number, resolution: string) => {
    try { await api.post(`${BASE}/classification-reviews/${id}/resolve`, { resolution, note }); setNote(''); load() }
    catch (e) { setError(errorDetail(e)) }
  }
  return (
    <Section title="Private seller monitoring and existing sellers">
      <p className="text-xs text-gray-500">
        Review triggers (USD 1,000 or 20 completed sales in 12 months, or commercial activity) are internal MyHigh5 thresholds,
        not legal registration thresholds. Opening a review never restricts selling.
      </p>
      <div className="flex flex-wrap gap-2">
        <button className="rounded-md border px-3 py-1 text-sm" onClick={run}>Run monitoring, expiry checks and provider retries</button>
        <button className="rounded-md border px-3 py-1 text-sm" onClick={async () => {
          try { setPreview((await api.get(`${BASE}/migration-preview`)).data) } catch (e) { setError(errorDetail(e)) }
        }}>Existing seller preview (read-only)</button>
      </div>
      {result && <p className="text-xs">Last run: {JSON.stringify(result)}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Table rows={reviews} cols={['id', 'user_id', 'trigger', 'qualifying_sales_usd', 'qualifying_order_count', 'detail']} />
      {reviews.length > 0 && (
        <div className="space-y-2">
          <textarea aria-label="Resolution note" className={input} rows={2} placeholder="Resolution note (required)" value={note} onChange={(e) => setNote(e.target.value)} />
          {reviews.map((r) => (
            <div key={r.id} className="flex flex-wrap gap-2 text-xs">
              <span>#{r.id}</span>
              <button className="rounded border px-2" disabled={note.trim().length < 5} onClick={() => resolve(r.id, 'REMAINS_PRIVATE')}>Remains private</button>
              <button className="rounded border px-2" disabled={note.trim().length < 5} onClick={() => resolve(r.id, 'BUSINESS_ONBOARDING_REQUESTED')}>Request business onboarding</button>
            </div>
          ))}
        </div>
      )}
      {preview && (
        <div className="space-y-1">
          <p className="text-xs">
            Sellers: {preview.existing_seller_count} · approved: {preview.already_approved} · manual review: {preview.requiring_manual_review} ·
            would be paused: {preview.would_be_paused} · open orders protected: {preview.open_orders_protected}
          </p>
          <p className="text-xs text-gray-500">{preview.note}</p>
          <Table rows={preview.sellers || []} cols={['user_id', 'seller_status', 'proposed_category', 'published_listings', 'active_digital_products',
            'rolling_sales_usd', 'rolling_order_count', 'missing', 'requires_manual_review', 'proposed_restriction', 'open_orders_protected']} />
        </div>
      )}
    </Section>
  )
}

export default function AdminSellerVerification() {
  const [status, setStatus] = useState('MANUAL_REVIEW_REQUIRED')
  const [rows, setRows] = useState<Json[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setError('')
    try { setRows((await api.get(`${BASE}/applications`, { params: status ? { status } : {} })).data) } catch (e) { setError(errorDetail(e)) }
  }, [status])
  useEffect(() => { load() }, [load])
  return (
    <div className="space-y-4">
      <Section title="Seller applications">
        <select aria-label="Status filter" className={input} value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => <option key={s} value={s}>{s || 'All'}</option>)}
        </select>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Table rows={rows} cols={['id', 'user_id', 'status', 'seller_category', 'business_structure', 'legal_name', 'trading_name',
          'establishment_country', 'review_reasons', 'submitted_at']} onRow={(r) => setSelected(r.id)} />
      </Section>
      {selected !== null && <Detail key={selected} id={selected} onChanged={load} />}
      <Rules />
      <Monitoring />
    </div>
  )
}
