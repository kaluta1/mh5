'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'

type Json = Record<string, any>
const BASE = '/api/v1/admin/marketplace'
const ORDERS = '/api/v1/admin/business-model/marketplace/orders'
const TABS = ['Overview', 'Listings', 'Orders', 'Requests', 'Reconciliation'] as const
type Tab = (typeof TABS)[number]
const REFUND_REASONS = ['NON_HANDOVER', 'PAYMENT_FAILURE', 'DUPLICATE_CHARGE', 'FRAUD', 'SELLER_UNABLE_TO_SUPPLY', 'LEGAL_REMEDY']

export function errorText(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object') return String((detail as Json).message || JSON.stringify(detail))
  return typeof detail === 'string' ? detail : 'Request failed'
}

async function call(method: 'get' | 'post', url: string, body?: Json) {
  const res = method === 'get' ? await api.get(url, { params: body }) : await api.post(url, body)
  if (res.status >= 400) throw { response: res }
  return res.data
}

function Counts({ title, data }: { title: string; data?: Record<string, number> }) {
  const entries = Object.entries(data || {})
  return (
    <div className="rounded-md border p-3 dark:border-gray-700">
      <p className="text-xs font-semibold uppercase text-gray-500">{title}</p>
      {entries.length === 0 ? <p className="text-sm text-gray-500">None</p> : (
        <ul className="text-sm">{entries.map(([k, v]) => <li key={k}>{k}: {v}</li>)}</ul>
      )}
    </div>
  )
}

function Password({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <input type="password" autoComplete="current-password" aria-label="Your current password" placeholder="Your current password"
           className="h-9 w-full rounded-md border px-2 text-sm dark:border-gray-700 dark:bg-gray-900" value={value}
           onChange={(e) => onChange(e.target.value)} />
  )
}

/** Marketplace administration: overview, listing moderation (moderate_content + password), orders and buyer
 * requests (money actions need process_cashouts + password), and the read-only reconciliation. Every rule is
 * enforced by the server; this page never publishes a listing or approves a seller. */
export default function AdminMarketplace() {
  const [tab, setTab] = useState<Tab>('Overview')
  const [message, setMessage] = useState('')
  const [overview, setOverview] = useState<Json | null>(null)
  const [listings, setListings] = useState<Json[]>([])
  const [listingStatus, setListingStatus] = useState('')
  const [listing, setListing] = useState<Json | null>(null)
  const [orders, setOrders] = useState<Json[]>([])
  const [order, setOrder] = useState<Json | null>(null)
  const [requests, setRequests] = useState<Json[]>([])
  const [recon, setRecon] = useState<Json | null>(null)
  const [form, setForm] = useState({ reason: '', seller_message: '', note: '', refund_reason: 'NON_HANDOVER', password: '' })
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const load = useCallback(async () => {
    setMessage('')
    try {
      if (tab === 'Overview') setOverview(await call('get', `${BASE}/overview`))
      if (tab === 'Listings') setListings(await call('get', `${BASE}/listings`, listingStatus ? { status: listingStatus } : undefined))
      if (tab === 'Orders') setOrders(await call('get', ORDERS))
      if (tab === 'Requests') setRequests(await call('get', `${BASE}/requests`))
      if (tab === 'Reconciliation') setRecon(await call('get', `${BASE}/reconciliation`))
    } catch (e) { setMessage(errorText(e)) }
  }, [tab, listingStatus])
  useEffect(() => { load() }, [load])

  const act = async (fn: () => Promise<void>, done: string) => {
    setMessage('')
    try { await fn(); setMessage(done); set('password', ''); await load() } catch (e) { setMessage(errorText(e)) }
  }
  const moderate = (action: 'suspend' | 'restore') => act(async () => {
    setListing(await call('post', `${BASE}/listings/${listing?.id}/moderation`, {
      action, reason: form.reason, seller_message: action === 'suspend' ? form.seller_message : undefined, current_password: form.password,
    }))
  }, action === 'suspend' ? 'Listing suspended' : 'Suspension lifted: the seller may publish it again')
  const orderAct = (path: string, body: Json, done: string) => act(async () => {
    setOrder(await call('post', `${ORDERS}/${order?.id}/${path}`, { ...body, current_password: form.password }))
  }, done)

  return (
    <div className="space-y-4">
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b dark:border-gray-700">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => { setTab(t); setListing(null); setOrder(null) }}
                  className={`whitespace-nowrap px-3 py-2 text-sm font-medium ${tab === t ? 'border-b-2 border-primary text-primary' : 'text-gray-500'}`}>
            {t}
          </button>
        ))}
      </div>
      {message && <p role="status" className="rounded-md bg-gray-50 p-2 text-sm dark:bg-gray-800">{message}</p>}

      {tab === 'Overview' && overview && (
        <div className="space-y-3">
          <p className="text-sm">
            Marketplace {overview.marketplace_enabled ? 'open' : 'closed'} · seller verification {overview.seller_verification_enforced ? 'enforced' : 'not enforced'} ·
            payment custodian: {overview.custodian} · checkout {overview.checkout_available ? 'available' : 'not available'} · open requests: {overview.open_requests}
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Counts title="Sellers" data={overview.sellers_by_status} />
            <Counts title="Seller applications" data={overview.applications_by_status} />
            <Counts title="Listings" data={overview.listings_by_status} />
            <Counts title="Orders" data={overview.orders_by_state} />
          </div>
        </div>
      )}

      {tab === 'Listings' && !listing && (
        <div className="space-y-2">
          <select aria-label="Listing status" className="h-9 rounded-md border px-2 text-sm dark:border-gray-700 dark:bg-gray-900"
                  value={listingStatus} onChange={(e) => setListingStatus(e.target.value)}>
            <option value="">All statuses</option>
            {['DRAFT', 'PUBLISHED', 'UNPUBLISHED', 'SUSPENDED', 'ARCHIVED'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          {listings.length === 0 ? <p className="text-sm text-gray-500">No listings.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead><tr className="text-xs text-gray-500"><th className="p-2">ID</th><th className="p-2">Title</th><th className="p-2">Status</th>
                  <th className="p-2">Seller</th><th className="p-2">Buyer price</th><th className="p-2" /></tr></thead>
                <tbody>{listings.map((l) => (
                  <tr key={l.id} className="border-t dark:border-gray-700">
                    <td className="p-2">{l.id}</td><td className="p-2">{l.title}</td><td className="p-2">{l.status}</td>
                    <td className="p-2">#{l.seller_user_id} ({l.seller_status})</td><td className="p-2">${l.buyer_price_usd}</td>
                    <td className="p-2"><button className="text-primary underline" onClick={async () => setListing(await call('get', `${BASE}/listings/${l.id}`))}>Open</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </div>
      )}
      {tab === 'Listings' && listing && (
        <div className="space-y-3 rounded-md border p-4 dark:border-gray-700" aria-label="Listing detail">
          <button className="text-sm text-primary underline" onClick={() => setListing(null)}>Back to listings</button>
          <h3 className="text-lg font-semibold">{listing.title} <span className="text-sm font-normal text-gray-500">({listing.status})</span></h3>
          <p className="whitespace-pre-line text-sm">{listing.description}</p>
          <p className="text-sm">Seller #{listing.seller_user_id}: {listing.seller_status}{listing.seller_can_sell ? '' : ' (not allowed to sell now)'} · orders: {listing.orders}</p>
          <ul className="text-xs text-gray-600 dark:text-gray-300">
            {(listing.history || []).map((h: Json, i: number) => <li key={i}>{h.at}: {h.action} by {h.by} ({h.from || '-'} → {h.to})</li>)}
          </ul>
          <div className="space-y-2">
            <input aria-label="Internal reason" placeholder="Internal reason (recorded in the audit trail)" value={form.reason}
                   onChange={(e) => set('reason', e.target.value)} className="h-9 w-full rounded-md border px-2 text-sm dark:border-gray-700 dark:bg-gray-900" />
            {listing.status !== 'SUSPENDED' && (
              <input aria-label="Message to the seller" placeholder="Message to the seller" value={form.seller_message}
                     onChange={(e) => set('seller_message', e.target.value)} className="h-9 w-full rounded-md border px-2 text-sm dark:border-gray-700 dark:bg-gray-900" />
            )}
            <Password value={form.password} onChange={(v) => set('password', v)} />
            {listing.status === 'SUSPENDED' ? (
              <button className="rounded-md bg-primary px-3 py-2 text-sm text-white" onClick={() => moderate('restore')}>Lift suspension</button>
            ) : listing.status !== 'ARCHIVED' && (
              <button className="rounded-md bg-red-600 px-3 py-2 text-sm text-white" onClick={() => moderate('suspend')}>Suspend listing</button>
            )}
          </div>
        </div>
      )}

      {tab === 'Orders' && !order && (
        orders.length === 0 ? <p className="text-sm text-gray-500">No marketplace orders.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr className="text-xs text-gray-500"><th className="p-2">ID</th><th className="p-2">State</th><th className="p-2">Total</th>
                <th className="p-2">Settlement</th><th className="p-2">Request</th><th className="p-2" /></tr></thead>
              <tbody>{orders.map((o) => (
                <tr key={o.id} className="border-t dark:border-gray-700">
                  <td className="p-2">{o.id}</td><td className="p-2">{o.state}</td><td className="p-2">${Number(o.buyer_total_amount).toFixed(2)}</td>
                  <td className="p-2">{o.settlement_status}</td><td className="p-2">{o.open_request ? o.open_request.kind : '-'}</td>
                  <td className="p-2"><button className="text-primary underline" onClick={() => setOrder(o)}>Open</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )
      )}
      {tab === 'Orders' && order && (
        <div className="space-y-3 rounded-md border p-4 dark:border-gray-700" aria-label="Order detail">
          <button className="text-sm text-primary underline" onClick={() => setOrder(null)}>Back to orders</button>
          <h3 className="text-lg font-semibold">Order #{order.id} · {order.state}</h3>
          <p className="text-sm">Buyer #{order.buyer_user_id} · seller #{order.seller_user_id} · total ${Number(order.buyer_total_amount).toFixed(2)} · custodian {order.custodian}</p>
          {order.open_request && <p className="text-sm">Buyer request ({order.open_request.kind}): {order.open_request.reason}</p>}
          <ul className="text-xs text-gray-600 dark:text-gray-300">
            {(order.events || []).map((e: Json, i: number) => <li key={i}>{e.at}: {e.from || '-'} → {e.to} by {e.by}{e.note ? ` (${e.note})` : ''}</li>)}
          </ul>
          <p className="text-xs text-gray-500">Money actions need the process_cashouts permission and your password. A refund is asked of the custodian; nothing is booked until it confirms.</p>
          <input aria-label="Note" placeholder="Note (shown in the order history)" value={form.note}
                 onChange={(e) => set('note', e.target.value)} className="h-9 w-full rounded-md border px-2 text-sm dark:border-gray-700 dark:bg-gray-900" />
          <Password value={form.password} onChange={(v) => set('password', v)} />
          <div className="flex flex-wrap gap-2">
            {['FUNDS_HELD', 'FULFILLED', 'DISPUTED'].includes(order.state) && (
              <>
                <select aria-label="Refund reason" className="h-9 rounded-md border px-2 text-sm dark:border-gray-700 dark:bg-gray-900"
                        value={form.refund_reason} onChange={(e) => set('refund_reason', e.target.value)}>
                  {REFUND_REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
                <button className="rounded-md bg-red-600 px-3 py-2 text-sm text-white"
                        onClick={() => orderAct('refund', { reason: form.refund_reason, note: form.note }, 'Refund requested from the custodian')}>Support refund</button>
              </>
            )}
            {order.open_request && (
              <button className="rounded-md border px-3 py-2 text-sm" onClick={() => orderAct('requests/decline', { note: form.note }, 'Request declined')}>Decline request</button>
            )}
            {order.settlement_status === 'SETTLEMENT_RETRY_NEEDED' && (
              <button className="rounded-md border px-3 py-2 text-sm" onClick={() => orderAct('retry-settlement', {}, 'Settlement requested again')}>Retry settlement</button>
            )}
          </div>
        </div>
      )}

      {tab === 'Requests' && (
        requests.length === 0 ? <p className="text-sm text-gray-500">No open buyer requests.</p> : (
          <ul className="space-y-2">{requests.map((r) => (
            <li key={r.id} className="rounded-md border p-3 text-sm dark:border-gray-700">
              <p className="font-medium">Order #{r.order_id} · {r.kind} · order {r.order_state} · ${r.buyer_total_amount}</p>
              <p className="text-gray-600 dark:text-gray-300">{r.reason}</p>
              <p className="text-xs text-gray-500">Open it under Orders to refund or decline.</p>
            </li>
          ))}</ul>
        )
      )}

      {tab === 'Reconciliation' && recon && (
        <div className="space-y-3">
          <p className="text-sm">Read only · fingerprint {recon.fingerprint} · {recon.issue_count} issue(s) · {recon.ok ? 'no issue needs an owner decision' : 'review needed'}</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Counts title="Sellers" data={recon.counts?.seller_profiles_by_status} />
            <Counts title="Listings" data={recon.counts?.listings_by_status} />
            <Counts title="Orders" data={recon.counts?.orders_by_state} />
            <Counts title="Applications" data={recon.counts?.seller_applications_by_status} />
          </div>
          {(recon.issues || []).length > 0 && (
            <ul className="space-y-1 text-sm">{recon.issues.map((i: Json, n: number) => (
              <li key={n} className="rounded-md bg-amber-50 p-2 dark:bg-amber-900/30">{i.type}: expected {i.expected}, found {i.actual}. {i.suggestion}</li>
            ))}</ul>
          )}
        </div>
      )}
    </div>
  )
}
