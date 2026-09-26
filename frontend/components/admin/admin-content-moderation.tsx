'use client'

import { useCallback, useEffect, useState } from 'react'
import { ShieldAlert } from 'lucide-react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

/**
 * Phase 6 content moderation queue. Shows codes only (state, rating, findings,
 * classifier status). The backend authorizes every action; child-safety items
 * can only be resolved by holders of the explicit child_safety_resolve
 * permission, and ordinary actions on them are refused server-side.
 */
type Item = {
  id: number
  contestant_id: number
  contest_id: number | null
  entry_kind: string | null
  exposure_status: string | null
  state: string
  rating: string | null
  proposed_rating: string | null
  findings: string[]
  classifier_status: string
  subject_possibly_minor: boolean
  child_safety_escalated: boolean
  update_required: boolean
  coverage: Record<string, string>
}

type Detail = Item & {
  can_moderate: boolean
  can_resolve_child_safety: boolean
  history: { action: string; actor_user_id: number | null; at: string | null; state: string | null; reason_code: string | null }[]
}

function StatusBadge({ item }: { item: Item }) {
  if (item.child_safety_escalated) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-600 text-white text-xs">
        <ShieldAlert className="w-3 h-3" /> Child safety review
      </span>
    )
  }
  if (item.state === 'PROHIBITED') {
    return <span className="px-2 py-0.5 rounded bg-gray-800 text-white text-xs">Prohibited</span>
  }
  return <span className="px-2 py-0.5 rounded bg-amber-500 text-white text-xs">Review</span>
}

const RATINGS = ['GENERAL', 'TEEN_13_PLUS', 'TEEN_16_PLUS', 'ADULT_18_PLUS']
const REASONS = ['REVIEWED_OK', 'FALSE_POSITIVE', 'REMOVE_PERSONAL_INFORMATION', 'POLICY_VIOLATION', 'POSSIBLE_MINOR', 'NEEDS_SECOND_REVIEW']

export default function AdminContentModeration() {
  const [items, setItems] = useState<Item[]>([])
  const [selected, setSelected] = useState<Detail | null>(null)
  const [rating, setRating] = useState('GENERAL')
  const [reason, setReason] = useState('REVIEWED_OK')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const res = await api.get('/api/v1/admin/content-moderation/queue')
    if (res.status === 200) setItems(res.data)
    else setError(res.status === 403 ? 'You are not allowed to moderate content.' : 'Could not load the queue.')
  }, [])

  const open = async (id: number) => {
    setError('')
    const res = await api.get(`/api/v1/admin/content-moderation/items/${id}`)
    if (res.status === 200) setSelected(res.data)
  }

  useEffect(() => { load() }, [load])

  const act = async (path: string, body: Record<string, unknown>) => {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      const res = await api.post(`/api/v1/admin/content-moderation/items/${selected.id}/${path}`, body)
      if (res.status === 200) {
        await load()
        await open(selected.id)
      } else {
        setError(res.data?.detail?.message || 'The action was not accepted.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card>
        <CardContent className="p-4 space-y-2">
          <h2 className="font-semibold text-gray-900 dark:text-white">Queue ({items.length})</h2>
          {items.length === 0 && <p className="text-sm text-gray-500">Nothing is waiting for review.</p>}
          {items.map((it) => (
            <button key={it.id} type="button" onClick={() => open(it.id)}
              className={`w-full text-left p-3 rounded-lg border ${selected?.id === it.id ? 'border-blue-500' : 'border-gray-200 dark:border-gray-700'}`}>
              <div className="flex items-center gap-2 text-sm">
                <StatusBadge item={it} />
                <span className="font-medium">#{it.id}</span>
                <span className="text-gray-500">entry {it.contestant_id} · {it.entry_kind ?? '-'}</span>
                <span className="ml-auto text-xs">{it.state}</span>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                proposed {it.proposed_rating ?? '-'} · classifier {it.classifier_status}
                {it.subject_possibly_minor ? ' · possible minor' : ''}
                {it.findings.length ? ` · findings: ${it.findings.join(', ')}` : ''}
              </div>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4 space-y-3">
          {!selected && <p className="text-sm text-gray-500">Select an item.</p>}
          {selected && (
            <>
              <h2 className="font-semibold text-gray-900 dark:text-white">Item #{selected.id}</h2>
              <p className="text-sm">State <strong>{selected.state}</strong> · rating {selected.rating ?? '-'} · exposure {selected.exposure_status ?? '-'}</p>
              <p className="text-sm">Findings: {selected.findings.length ? selected.findings.join(', ') : 'none'}</p>
              <p className="text-xs text-gray-500">
                Coverage: {Object.entries(selected.coverage || {}).map(([k, v]) => `${k}=${v}`).join(' · ') || 'not recorded'}
              </p>
              {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
              <div className="flex flex-wrap gap-2 items-center">
                <select aria-label="Rating" value={rating} onChange={(e) => setRating(e.target.value)}
                  className="px-2 py-1 border rounded bg-white dark:bg-gray-800 text-sm">
                  {RATINGS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
                <select aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)}
                  className="px-2 py-1 border rounded bg-white dark:bg-gray-800 text-sm">
                  {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
              {selected.child_safety_escalated ? (
                <div className="space-y-2">
                  <p className="text-sm text-red-600">Dedicated child-safety escalation. Ordinary moderation actions are disabled.</p>
                  {/* Resolution controls exist only for explicitly authorized child-safety resolvers. */}
                  {selected.can_resolve_child_safety ? (
                    <div className="flex gap-2">
                      <Button disabled={busy} variant="destructive"
                        onClick={() => act('child-safety-resolution', { resolution: 'CONFIRMED', reason })}>Confirm (stays prohibited)</Button>
                      <Button disabled={busy} variant="outline"
                        onClick={() => act('child-safety-resolution', { resolution: 'NO_CHILD_SAFETY_CONCERN', reason })}>No child-safety concern (back to review)</Button>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">Only authorized child-safety reviewers can resolve this item.</p>
                  )}
                </div>
              ) : selected.state === 'PROHIBITED' ? (
                <p className="text-sm text-gray-600 dark:text-gray-400">Prohibited content stays private. It cannot be approved.</p>
              ) : !selected.can_moderate ? (
                <p className="text-sm text-gray-500">You can view this item but not moderate it.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy} onClick={() => act('actions', { action: 'APPROVE', reason, rating })}>Approve</Button>
                  <Button disabled={busy} variant="outline" onClick={() => act('actions', { action: 'RESOLVE_ISSUE', reason })}>Resolve findings</Button>
                  <Button disabled={busy} variant="outline" onClick={() => act('actions', { action: 'REQUEST_UPDATE', reason })}>Request update</Button>
                  <Button disabled={busy} variant="outline" onClick={() => act('actions', { action: 'HOLD', reason })}>Hold</Button>
                  <Button disabled={busy} variant="destructive" onClick={() => act('actions', { action: 'PROHIBIT', reason })}>Prohibit</Button>
                  <Button disabled={busy} variant="destructive" onClick={() => act('actions', { action: 'ESCALATE_CHILD_SAFETY', reason })}>Escalate child safety</Button>
                </div>
              )}
              <div>
                <h3 className="text-sm font-semibold mt-2">History</h3>
                <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
                  {selected.history.map((h, i) => (
                    <li key={i}>{h.at ?? ''} · {h.action} · {h.state ?? ''}{h.reason_code ? ` · ${h.reason_code}` : ''}{h.actor_user_id ? ` · user ${h.actor_user_id}` : ''}</li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
