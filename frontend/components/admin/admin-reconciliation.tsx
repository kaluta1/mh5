'use client'

import { useCallback, useEffect, useState } from 'react'
import api from '@/lib/api'

type Json = Record<string, any>
const BASE = '/api/v1/admin/reconciliation'

async function read(path: string): Promise<Json | { forbidden: true } | null> {
  try {
    const res = await api.get(`${BASE}${path}`)
    if (res.status === 403) return { forbidden: true }
    return res.status < 400 ? res.data : null
  } catch {
    return null
  }
}

function Issues({ issues }: { issues: Json[] }) {
  if (!issues?.length) return <p className="text-emerald-700">No issues.</p>
  return (
    <ul className="space-y-1">
      {issues.slice(0, 50).map((i, n) => (
        <li key={n} className="text-xs">
          <strong>{i.type}</strong> {Object.entries(i).filter(([k]) => k.endsWith('_id')).map(([k, v]) => `${k} ${v}`).join(', ')}
          {' '}— expected {String(i.expected)}, actual {String(i.actual)}{i.suggestion ? `; ${i.suggestion}` : ''}
          {i.owner_approval ? ' (owner approval needed)' : ''}
        </li>
      ))}
    </ul>
  )
}

/** Prompt 6 reconciliation: read-only reports, plus the one-at-a-time DSM sponsor restoration
 * (Super Admin and current password, enforced by the server). */
export default function AdminReconciliation() {
  const [annual, setAnnual] = useState<Json | null>(null)
  const [pool, setPool] = useState<Json | null>(null)
  const [dsm, setDsm] = useState<Json | null>(null)
  const [candidates, setCandidates] = useState<Json[]>([])
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    const [a, p, d, c] = await Promise.all([read('/annual-ads'), read('/referral-pool'), read('/dsm'), read('/dsm/candidates')])
    setAnnual(a as Json)
    setPool(p as Json)
    setDsm(d as Json)
    setCandidates(c && !('forbidden' in c) ? (c as Json).candidates || [] : [])
  }, [])
  useEffect(() => { load() }, [load])

  const restore = async (userId: number) => {
    setMessage('')
    try {
      const res = await api.post(`${BASE}/dsm/restorations`, { user_id: userId, note: notes[userId] || '', current_password: password })
      if (res.status >= 400) throw { response: res }
      setMessage(`Sponsor restored for member #${userId}`)
      await load()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: Json } } })?.response?.data?.detail
      setMessage(detail?.message || 'Restoration refused')
    }
  }

  return (
    <section data-testid="admin-reconciliation" className="space-y-4 rounded-xl border border-gray-200 bg-white p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
      <h2 className="font-semibold">Annual Ads, Referral Pool and DSM reconciliation (read-only)</h2>
      <div data-testid="rec-annual">
        <h3 className="font-medium">Annual Ads</h3>
        {annual && !annual.forbidden ? (<>
          <p>Payments {annual.payments} · gross {annual.gross} USD · sponsor commissions {annual.sponsor_commission_total} USD ·
            {' '}{JSON.stringify(annual.by_commission_status || {})}</p>
          <Issues issues={annual.issues || []} />
        </>) : <p className="text-gray-500">Not available.</p>}
      </div>
      <div data-testid="rec-pool">
        <h3 className="font-medium">Referral Pool</h3>
        {pool && !pool.forbidden ? (<>
          <p>Units {JSON.stringify(pool.counts?.units_by_status || {})} · holders {pool.counts?.holders_with_active_units} ·
            {' '}assignments {pool.counts?.assignments} · fingerprint {pool.fingerprint}</p>
          <Issues issues={pool.issues || []} />
        </>) : <p className="text-gray-500">Not available.</p>}
      </div>
      <div data-testid="rec-dsm">
        <h3 className="font-medium">DSM membership</h3>
        {dsm && 'forbidden' in dsm ? <p className="text-gray-500">A Super Admin or manage_administrators is required.</p>
          : dsm?.source === 'SOURCE_MISSING' ? <p className="text-gray-500">No DSM import record on this server.</p>
            : dsm ? (<>
              <ul className="grid gap-1 sm:grid-cols-2">
                {Object.entries(dsm.counts || {}).map(([k, v]) => <li key={k}>{k.replace(/_/g, ' ').toLowerCase()}: <strong>{String(v)}</strong></li>)}
              </ul>
              <p className="text-xs text-gray-500">{dsm.referral_pool_eligibility?.note}</p>
              <h4 className="mt-2 font-medium">Restoration candidates ({candidates.length})</h4>
              <p className="text-xs text-gray-500">Each restoration is applied one at a time, only while the member still has no sponsor,
                never creates commissions for the past, and is recorded with its evidence.</p>
              <input type="password" placeholder="Current password" aria-label="Current password" value={password}
                onChange={(e) => setPassword(e.target.value)} className="rounded border px-2 py-1 dark:bg-gray-900" autoComplete="current-password" />
              {candidates.map((c) => (
                <div key={c.user_id} className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                  <span>Member #{c.user_id} (DSM {c.dsm_id}) → sponsor #{c.dsm_sponsor_user_id}</span>
                  <input placeholder="Evidence / reason" aria-label={`Evidence for member ${c.user_id}`} value={notes[c.user_id] || ''}
                    onChange={(e) => setNotes({ ...notes, [c.user_id]: e.target.value })} className="rounded border px-2 py-0.5 dark:bg-gray-900" />
                  <button type="button" disabled={(notes[c.user_id] || '').trim().length < 5}
                    onClick={() => restore(c.user_id)} className="rounded bg-blue-600 px-2 py-0.5 text-white disabled:opacity-50">Restore sponsor</button>
                </div>
              ))}
            </>) : <p className="text-gray-500">Not available.</p>}
      </div>
      {message ? <p role="status">{message}</p> : null}
    </section>
  )
}
