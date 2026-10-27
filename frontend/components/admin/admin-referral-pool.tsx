'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'

type Json = Record<string, any>
type Paged = { items: Json[]; page: number; page_size: number; total?: number; summary?: Json; checked_total?: number }

const BASE = '/api/v1/admin/referral-pool'

function errorDetail(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (detail && typeof detail === 'object' && 'message' in (detail as Json)) return String((detail as Json).message)
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

function cell(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

type Render = Record<string, (row: Json) => React.ReactNode>

function Table({ rows, cols, actions, headers = {}, render = {} }: {
  rows: Json[]
  cols: string[]
  actions?: (row: Json) => React.ReactNode
  headers?: Record<string, string>
  render?: Render
}) {
  if (!rows.length) return <p className="text-sm text-gray-500">No rows.</p>
  return (
    <table className="w-full text-xs sm:text-sm">
      <thead className="text-left text-gray-500">
        <tr>
          {cols.map((c) => (
            <th key={c} className="py-1 pr-3 whitespace-nowrap">{headers[c] ?? c}</th>
          ))}
          {actions && <th className="py-1 pr-3" />}
        </tr>
      </thead>
      <tbody className="text-gray-800 dark:text-gray-200">
        {rows.map((r, i) => (
          <tr key={r.id ?? i} className="border-t border-gray-100 dark:border-gray-700 align-top">
            {cols.map((c) => (
              <td key={c} className="py-1 pr-3 break-words">{render[c] ? render[c](r) : cell(r[c])}</td>
            ))}
            {actions && <td className="py-1 pr-3 whitespace-nowrap">{actions(r)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** One server-paginated list: at most `pageSize` rows are ever requested or rendered. */
function PagedTable({
  path, cols, statuses, defaultStatus = '', pageSize = 25, reloadKey = 0, actions, extra, rowView, params = {}, headers, render,
}: {
  path: string
  cols: string[]
  statuses?: string[]
  defaultStatus?: string
  pageSize?: number
  reloadKey?: number
  actions?: (row: Json) => React.ReactNode
  extra?: (data: Paged) => React.ReactNode
  rowView?: (row: Json) => Json
  params?: Json
  headers?: Record<string, string>
  render?: Render
}) {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState(defaultStatus)
  const [data, setData] = useState<Paged | null>(null)
  const [error, setError] = useState<string | null>(null)
  const paramsKey = JSON.stringify(params)

  useEffect(() => {
    let live = true
    setError(null)
    const query: Json = { page, page_size: pageSize, ...JSON.parse(paramsKey) }
    if (statuses) query.status = status
    api
      .get<Paged>(`${BASE}${path}`, { params: query })
      .then((res) => {
        if (!live) return
        setData(rowView ? { ...res.data, items: res.data.items.map(rowView) } : res.data)
      })
      .catch((e) => live && setError(errorDetail(e)))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, page, status, pageSize, reloadKey, paramsKey])

  const pages = data?.total !== undefined ? Math.max(1, Math.ceil(data.total / data.page_size)) : null
  return (
    <div className="space-y-2">
      {statuses && (
        <label className="text-sm flex items-center gap-2">
          Status
          <select
            aria-label="Status filter"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setPage(1)
            }}
            className="rounded border px-2 py-1 dark:bg-gray-700"
          >
            <option value="">All</option>
            {statuses.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      )}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {data && (
        <>
          {extra?.(data)}
          <Table rows={data.items} cols={cols} actions={actions} headers={headers} render={render} />
          <div className="flex items-center gap-2 text-sm">
            <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded bg-gray-100 dark:bg-gray-700 px-2 py-1 disabled:opacity-50">
              Previous
            </button>
            <span>
              Page {page}
              {pages ? ` / ${pages}` : ''}
              {data.total !== undefined ? ` · ${data.total} rows` : ''}
            </span>
            <button
              type="button"
              disabled={pages ? page >= pages : data.items.length < data.page_size}
              onClick={() => setPage(page + 1)}
              className="rounded bg-gray-100 dark:bg-gray-700 px-2 py-1 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function OnOff({ on }: { on: boolean }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-semibold ${on ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-800'}`}>
      {on ? 'ON' : 'OFF'}
    </span>
  )
}

const input = 'rounded border px-2 py-1 dark:bg-gray-700'

function LimitsForm({ limits, onSaved }: { limits: Json; onSaved: (msg: string) => void }) {
  const [values, setValues] = useState<Record<string, string>>({
    max_units_per_purchase: limits.max_units_per_purchase?.toString() ?? '',
    max_units_per_member: limits.max_units_per_member?.toString() ?? '',
    max_active_units: limits.max_active_units?.toString() ?? '',
  })
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const save = async () => {
    setError(null)
    const body: Json = { password }
    for (const [k, v] of Object.entries(values)) body[k] = v.trim() === '' ? null : Number(v)
    try {
      await api.put(`${BASE}/limits`, body)
      setPassword('')
      onSaved('Limits saved.')
    } catch (e) {
      setError(errorDetail(e))
    }
  }
  return (
    <div className="space-y-2 text-sm">
      <p className="text-gray-500">
        Purchases are unlimited: leave a field empty for <strong>Unlimited</strong> (the default). Set a number only to impose a
        cap. Requires manage_payment_settings and your password; audited. Units already paid for are never removed.
      </p>
      <div className="flex flex-wrap gap-3 items-end">
        {Object.keys(values).map((k) => (
          <label key={k} className="flex flex-col">
            {k}
            <input aria-label={k} inputMode="numeric" placeholder="Unlimited" value={values[k]} onChange={(e) => setValues({ ...values, [k]: e.target.value })} className={`${input} w-32`} />
            <span className="text-xs text-gray-500" data-testid={`limit-${k}`}>{values[k].trim() === '' ? 'Unlimited' : `At most ${values[k].trim()}`}</span>
          </label>
        ))}
        <label className="flex flex-col">
          Password
          <input aria-label="Password for limits" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className={input} />
        </label>
        <button type="button" onClick={save} disabled={!password} className="rounded bg-myhigh5-primary text-white px-3 py-1.5 disabled:opacity-50">
          Save limits
        </button>
      </div>
      {error && <p role="alert" className="text-red-600">{error}</p>}
    </div>
  )
}

function RefundProposalForm({ onDone }: { onDone: (msg: string) => void }) {
  const [form, setForm] = useState({ purchase_id: '', quantity: '1', provider_reference: '', evidence_note: '', password: '' })
  const [error, setError] = useState<string | null>(null)
  const quantity = Number(form.quantity) || 0
  const submit = async () => {
    setError(null)
    try {
      await api.post(`${BASE}/refunds`, {
        purchase_id: Number(form.purchase_id), quantity, amount: (quantity * 100).toFixed(2),
        provider_reference: form.provider_reference, evidence_note: form.evidence_note, password: form.password,
      })
      setForm({ purchase_id: '', quantity: '1', provider_reference: '', evidence_note: '', password: '' })
      onDone('Refund proposed. A different administrator must approve it before anything changes.')
    } catch (e) {
      setError(errorDetail(e))
    }
  }
  const field = (k: keyof typeof form, label: string, type = 'text') => (
    <label className="flex flex-col">
      {label}
      <input aria-label={label} type={type} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className={input} />
    </label>
  )
  return (
    <div className="space-y-2 text-sm">
      <p className="text-gray-500">
        Only for a refund the provider sent no signed notification for. Record what you checked at the provider. The reference you enter is an
        administrator-entered claim, never treated as verified. No money is sent from here.
      </p>
      <div className="flex flex-wrap gap-3 items-end">
        {field('purchase_id', 'Purchase id')}
        {field('quantity', 'Units')}
        <span className="pb-1">Amount: ${(quantity * 100).toFixed(2)}</span>
        {field('provider_reference', 'Provider reference')}
        {field('evidence_note', 'Evidence checked')}
        {field('password', 'Password to propose', 'password')}
        <button type="button" onClick={submit} disabled={!form.password} className="rounded bg-myhigh5-primary text-white px-3 py-1.5 disabled:opacity-50">
          Propose refund
        </button>
      </div>
      {error && <p role="alert" className="text-red-600">{error}</p>}
    </div>
  )
}

/** Approve/reject (refunds) or clear/confirm (risk reviews): a note and the administrator's password. */
function DecisionForm({ choices, submit }: { choices: [string, string][]; submit: (choice: string, note: string, password: string) => Promise<void> }) {
  const [note, setNote] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  return (
    <span className="flex flex-wrap gap-1 items-center">
      <input aria-label="Decision note" placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)} className={`${input} w-32`} />
      <input aria-label="Password to decide" placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className={`${input} w-28`} />
      {choices.map(([value, label]) => (
        <button
          key={value}
          type="button"
          disabled={!password || note.trim().length < 5}
          onClick={async () => {
            setError(null)
            try {
              await submit(value, note, password)
            } catch (e) {
              setError(errorDetail(e))
            }
          }}
          className="rounded bg-gray-100 dark:bg-gray-700 px-2 py-1 disabled:opacity-50"
        >
          {label}
        </button>
      ))}
      {error && <span role="alert" className="text-red-600">{error}</span>}
    </span>
  )
}

/** A refund record's status in words that never call an administrator claim "confirmed". */
export function refundStatusText(row: Json): string {
  if (row.status === 'APPROVED') return 'Approved by a second administrator (claim, not provider-verified)'
  if (row.status === 'REJECTED') return 'Rejected'
  return 'Awaiting a second administrator'
}

// users.sponsor_source values (services/sponsor_assignment.py); NULL = linked before the source was recorded.
const REFERRAL_TYPES: Record<string, string> = {
  PERSONAL_REFERRAL: 'Personal Referral',
  JOIN_CODE: 'Join Code',
  REFERRAL_POOL: 'Referral Pool',
  FOUNDER_ASSIGNED: 'First Pool member (no previous sponsor)',
  DSM_IMPORT: 'DSM Import',
  NONE: 'None',
}

export function referralTypeLabel(source: unknown): string {
  if (source === null || source === undefined || String(source).trim() === '') return 'Not recorded (legacy)'
  const value = String(source)
  return REFERRAL_TYPES[value] ?? value.toLowerCase().split('_').filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')
}

/** The member's profile in the dashboard (/dashboard/users/{id}); plain text when the account has no username or is gone. */
function ProfileLink({ id, username }: { id: unknown; username: unknown }) {
  if (id === null || id === undefined) return <span className="text-gray-500">—</span>
  if (!username) return <span className="text-gray-500">Unknown account (#{String(id)})</span>
  return (
    <a href={`/dashboard/users/${encodeURIComponent(String(id))}`} className="text-myhigh5-primary hover:underline break-all">
      {String(username)}
    </a>
  )
}

const SPONSOR_VIEWS = {
  all: { path: '/sponsors', label: 'All sponsor relationships' },
  invalid: { path: '/invalid-sponsors', label: 'Personal sponsors that would not be valid inviters today' },
} as const

function SponsorsTable() {
  const [view, setView] = useState<keyof typeof SPONSOR_VIEWS>('all')
  return (
    <div className="space-y-2">
      <label className="text-sm flex flex-wrap items-center gap-2">
        Show
        <select aria-label="Sponsors view" value={view} onChange={(e) => setView(e.target.value as keyof typeof SPONSOR_VIEWS)} className="rounded border px-2 py-1 dark:bg-gray-700">
          {Object.entries(SPONSOR_VIEWS).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
      </label>
      <PagedTable
        key={view}
        path={SPONSOR_VIEWS[view].path}
        pageSize={50}
        cols={['user', 'sponsor', 'referral_type']}
        headers={{ user: 'User', sponsor: 'Sponsor', referral_type: 'Referral Type' }}
        render={{
          user: (r) => <ProfileLink id={r.user_id} username={r.username} />,
          sponsor: (r) => <ProfileLink id={r.sponsor_id} username={r.sponsor_username} />,
          referral_type: (r) => referralTypeLabel(r.sponsor_source ?? r.source),
        }}
        extra={(data) =>
          view === 'invalid' ? (
            <p className="text-xs text-gray-500">Checks {data.page_size} personally sponsored members per page, of {data.checked_total}.</p>
          ) : null
        }
      />
    </div>
  )
}

const TABS = ['Overview', 'Rounds', 'Queue', 'Purchases', 'Units', 'Refunds', 'Reconciliation', 'Events', 'Risk reviews', 'Sponsors', 'Audit'] as const

export default function AdminReferralPool() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Overview')
  const [overview, setOverview] = useState<Json | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [roundId, setRoundId] = useState<number | null>(null)

  const loadOverview = useCallback(async () => {
    try {
      setOverview((await api.get(`${BASE}/overview`)).data)
    } catch (e) {
      setMessage(errorDetail(e))
    }
  }, [])

  useEffect(() => {
    loadOverview()
  }, [loadOverview, reload])

  const done = (msg: string) => {
    setMessage(msg)
    setReload((n) => n + 1)
  }

  const finance = Boolean(overview?.permissions?.finance)
  const kyc = Boolean(overview?.permissions?.kyc)
  const operations = Boolean(overview?.permissions?.operations)
  const needs = (permission: string) => (
    <p className="text-sm text-gray-500">This view requires the {permission} permission. The server enforces it.</p>
  )

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Referral Pool (Multi-Unit)</h1>
        <p className="text-sm text-gray-500">
          Units, rounds, allocation, purchases, refunds and anti-abuse cases. Every list is paginated. Feature switches are shown read-only:
          this console cannot turn sales, allocation or the worker on.
        </p>
      </div>
      <div className="flex flex-wrap gap-2" role="tablist">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${tab === t ? 'bg-myhigh5-primary text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200'}`}
          >
            {t}
          </button>
        ))}
      </div>
      {message && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{message}</p>}

      {tab === 'Overview' && overview && (
        <>
          <Card title="Feature status (read-only)">
            <ul className="text-sm space-y-1" data-testid="feature-status">
              <li>multiunit_sales_enabled <OnOff on={overview.features.multiunit_sales_enabled} /></li>
              <li>allocation_enabled <OnOff on={overview.features.allocation_enabled} /></li>
              <li>REFERRAL_POOL_WORKER_ENABLED <OnOff on={overview.features.worker_enabled} /></li>
            </ul>
            <p className="text-sm text-gray-500">Activation is a separate, approved release step and is not available from this console.</p>
          </Card>
          <Card title="Statistics">
            <p className="text-sm">
              Eligible (active) units {overview.eligible_units} · holders {overview.unit_holders} · waiting for the next round{' '}
              {overview.units_waiting_for_next_round} · round-based assignments {overview.round_assignments}
            </p>
            <p className="text-sm">Units by status: {cell(overview.units)}</p>
            <p className="text-sm">Purchases by status: {cell(overview.purchases)}</p>
            <p className="text-sm">Rounds: {cell(overview.rounds)} · queue: {cell(overview.queue)} · events: {cell(overview.events)}</p>
            <p className="text-sm">
              Refund records: {cell(overview.refunds)} · open risk reviews {overview.risk_reviews.open} (blocking {overview.risk_reviews.open_blocking})
            </p>
            {overview.current_round ? (
              <p className="text-sm">
                Current round {overview.current_round.round_number}: {overview.current_round.filled_slots} filled,{' '}
                {overview.current_round.void_slots} void, {overview.current_round.remaining_slots} open of {overview.current_round.total_slots}
              </p>
            ) : (
              <p className="text-sm">No round is open.</p>
            )}
            {overview.amounts ? (
              <p className="text-sm" data-testid="overview-amounts">
                Paid ${overview.amounts.paid} · refunded ${overview.amounts.refunded} {overview.amounts.currency}
              </p>
            ) : (
              <p className="text-sm text-gray-500">Amounts are shown to administrators with a finance permission.</p>
            )}
          </Card>
          <Card title="Optional unit limits (empty = Unlimited)">
            <LimitsForm key={JSON.stringify(overview.limits)} limits={overview.limits} onSaved={done} />
          </Card>
        </>
      )}

      {tab === 'Rounds' && !operations && needs('process_cashouts, manage_payment_settings or manage_kyc_settings')}
      {tab === 'Rounds' && operations && (
        <>
          <Card title="Rounds">
            <PagedTable
              path="/rounds"
              statuses={['OPEN', 'COMPLETED', 'CLOSED']}
              cols={['round_number', 'status', 'opened_at', 'completed_at', 'total_slots', 'filled_slots', 'void_slots', 'remaining_slots']}
              actions={(r) => (
                <button type="button" onClick={() => setRoundId(r.id)} className="rounded bg-gray-100 dark:bg-gray-700 px-2 py-1">
                  Slots
                </button>
              )}
            />
          </Card>
          {roundId !== null && (
            <>
              <Card title={`Slots of round id ${roundId}`}>
                <PagedTable path={`/rounds/${roundId}/slots`} statuses={['OPEN', 'FILLED', 'VOID']} pageSize={50}
                  cols={['id', 'unit_id', 'member_user_id', 'member_username', 'status', 'referred_user_id', 'filled_at', 'voided_at', 'void_reason']} />
              </Card>
              <Card title={`Allocations of round id ${roundId}`}>
                <PagedTable path="/assignments" params={{ round_id: roundId }}
                  cols={['id', 'referred_user_id', 'pool_member_user_id', 'unit_id', 'slot_id', 'assigned_at']} />
              </Card>
            </>
          )}
        </>
      )}

      {tab === 'Queue' && !operations && needs('process_cashouts, manage_payment_settings or manage_kyc_settings')}
      {tab === 'Queue' && operations && (
        <Card title="Pending referral queue (first in, first out)">
          <PagedTable path="/queue" statuses={['WAITING', 'ASSIGNED', 'CANCELLED']} defaultStatus="WAITING"
            cols={['referred_user_id', 'status', 'enqueued_at', 'attempts', 'last_error', 'resolved_at', 'resolution_reason', 'assignment_id']} />
        </Card>
      )}

      {tab === 'Purchases' &&
        (finance ? (
          <Card title="Purchases and payment status">
            <PagedTable path="/purchases" statuses={['PENDING_PAYMENT', 'PAID', 'PARTIALLY_REFUNDED', 'REFUNDED', 'CANCELLED', 'HELD_FOR_REVIEW']}
              cols={['id', 'user_id', 'username', 'quantity', 'total_amount', 'status', 'payment', 'units', 'refund', 'created_at', 'paid_at']} />
          </Card>
        ) : needs('process_cashouts or manage_payment_settings'))}

      {tab === 'Units' &&
        (finance ? (
          <Card title="Units (suspended, refunded and all others)">
            <PagedTable
              path="/units"
              pageSize={50}
              statuses={['PENDING', 'ACTIVE', 'SUSPENDED', 'REFUNDED', 'REVOKED']}
              cols={['id', 'user_id', 'username', 'purchase_id', 'unit_index', 'status', 'status_reason', 'activated_at', 'suspended_at', 'refunded_at', 'refund_reference', 'evidence']}
              extra={() => (
                <p className="text-xs text-gray-500">
                  Evidence: "Confirmed by the payment provider" only for signed provider notifications. Administrator-entered references are
                  labelled as claims.
                </p>
              )}
              rowView={(row) => ({ ...row, evidence: row.refund_evidence?.label ?? '' })}
            />
          </Card>
        ) : needs('process_cashouts or manage_payment_settings'))}

      {tab === 'Refunds' &&
        (finance ? (
          <>
            <Card title="Propose a manual refund (two-person rule)">
              <RefundProposalForm onDone={done} />
            </Card>
            <Card title="Refund records">
              <p className="text-sm text-gray-500">
                The proposer can never approve their own proposal. Both administrators need process_cashouts and their password.
              </p>
              <PagedTable
                path="/refunds"
                reloadKey={reload}
                statuses={['PROPOSED', 'APPROVED', 'REJECTED']}
                cols={['id', 'purchase_id', 'quantity', 'amount', 'provider_reference', 'evidence_label', 'evidence_note', 'decision', 'proposed_by', 'proposed_at', 'decided_by', 'decided_at', 'decision_note']}
                rowView={(row) => ({ ...row, decision: refundStatusText(row) })}
                actions={(r) =>
                  r.status === 'PROPOSED' ? (
                    <DecisionForm
                      choices={[['approve', 'Approve'], ['reject', 'Reject']]}
                      submit={async (choice, note, password) => {
                        await api.post(`${BASE}/refunds/${r.id}/decision`, { approve: choice === 'approve', note, password })
                        done(`Refund ${r.id} ${choice === 'approve' ? 'approved' : 'rejected'}.`)
                      }}
                    />
                  ) : null
                }
              />
            </Card>
          </>
        ) : needs('process_cashouts or manage_payment_settings'))}

      {tab === 'Reconciliation' &&
        (finance ? (
          <Card title="Financial reconciliation (ledger against units, one page of purchases at a time)">
            <PagedTable
              path="/reconciliation"
              pageSize={25}
              cols={['purchase_id', 'user_id', 'status', 'total_amount', 'problems']}
              extra={(data) =>
                data.summary ? (
                  <div className="text-sm space-y-1">
                    <p>Refunded units by evidence: {cell(data.summary.refunded_units)}</p>
                    <p>
                      Outstanding: {data.summary.refund_proposals_awaiting_decision} refund proposal(s) awaiting a decision ·{' '}
                      {data.summary.held_for_review_purchases} purchase(s) held for review · {data.summary.page_purchases_with_problems} purchase(s)
                      on this page with ledger differences
                    </p>
                  </div>
                ) : null
              }
            />
          </Card>
        ) : needs('process_cashouts or manage_payment_settings'))}

      {tab === 'Events' && !operations && needs('process_cashouts, manage_payment_settings or manage_kyc_settings')}
      {tab === 'Events' && operations && (
        <Card title="Pool events">
          <PagedTable path="/events" statuses={['PENDING', 'DONE', 'FAILED']} defaultStatus="FAILED"
            cols={['id', 'user_id', 'event_type', 'status', 'attempts', 'last_error', 'created_at', 'processed_at']} />
        </Card>
      )}

      {tab === 'Risk reviews' &&
        (kyc ? (
          <Card title="Anti-abuse review cases">
            <p className="text-sm text-gray-500">
              Account ids and an evidence fingerprint only: no identity documents, names, birth dates, wallet addresses or IP addresses.
            </p>
            <PagedTable
              path="/risk-reviews"
              reloadKey={reload}
              statuses={['OPEN', 'CLEARED', 'CONFIRMED']}
              defaultStatus="OPEN"
              cols={['id', 'user_id', 'signal', 'blocking', 'status', 'related_user_ids', 'evidence_fingerprint', 'created_at', 'decided_by', 'decided_at', 'decision_note']}
              actions={(r) =>
                r.status === 'OPEN' ? (
                  <DecisionForm
                    choices={[['CLEARED', 'Clear'], ['CONFIRMED', 'Confirm']]}
                    submit={async (decision, note, password) => {
                      await api.post(`${BASE}/risk-reviews/${r.id}/decision`, { decision, note, password })
                      done(`Review ${r.id} ${decision.toLowerCase()}.`)
                    }}
                  />
                ) : null
              }
            />
          </Card>
        ) : needs('manage_kyc_settings'))}

      {tab === 'Sponsors' && !kyc && needs('manage_kyc_settings')}
      {tab === 'Sponsors' && kyc && (
        <Card title="Sponsors (read-only)">
          <p className="text-sm text-gray-500">
            Who sponsors whom: each row is a member (User), the member who sponsors them (Sponsor) and how that link was made (Referral
            Type). Click a username to open the profile. This view never changes a sponsor.
          </p>
          <SponsorsTable />
        </Card>
      )}

      {tab === 'Audit' &&
        (finance || kyc ? (
          <Card title="Audit trail (limits, refunds, risk decisions)">
            <PagedTable path="/audit" reloadKey={reload} cols={['id', 'timestamp', 'action', 'table_name', 'record_id', 'user_id', 'old_values', 'new_values']} />
          </Card>
        ) : needs('a finance permission or manage_kyc_settings'))}
    </div>
  )
}
