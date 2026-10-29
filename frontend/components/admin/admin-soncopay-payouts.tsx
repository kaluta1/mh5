'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { financeErrorText } from '@/lib/finance-admin'
import { inputClass } from './admin-finance-ui'

/**
 * Admin > Finance & Payments > SoncoPay Payouts. Automatic USDT (BNB Smart Chain, BEP20) commission
 * payouts through SoncoPay: what still blocks them, the owner's recorded authorization, and every
 * member wallet as a SoncoPay payout destination (address masked). The backend decides everything
 * (/api/v1/admin/finance/soncopay/payouts); no key is ever shown. Recording the authorization changes
 * no payout switch: the server activation stays a separate operator step.
 */

type Blocker = { code: string; message: string }
type Destination = {
  id: number; user_id: number; username: string; address: string | null; status: string; usable: boolean
  usable_from: string | null; confirmed_at: string | null; destination_id: string | null; last_error: string | null
}
type PayoutsView = {
  blockers: Blocker[]
  authorization: { authorized_at: string; authorized_by: number | null; note: string | null } | null
  confirmation_phrase: string
  destination_limit: number
  counts: Record<string, number>
  destinations: Destination[]
  provider: null | {
    balance?: Record<string, string | null>; fee?: string | null; min_payout_usd?: string | number | null
    open_destinations?: number; settings?: Record<string, unknown>; error?: string
  }
}

const STATUS_TEXT: Record<string, string> = {
  QUEUED: 'Queued (no free SoncoPay slot yet)',
  PENDING_CONFIRMATION: 'Awaiting confirmation in the SoncoPay dashboard',
  ACTIVE: 'Confirmed',
  DISABLED: 'Disabled',
  REJECTED: 'Refused by SoncoPay',
  SUPERSEDED: 'Replaced by a newer wallet',
}

export function destinationText(d: Pick<Destination, 'status' | 'usable' | 'usable_from'>): string {
  if (d.status === 'ACTIVE' && !d.usable) {
    return d.usable_from ? `Security waiting period until ${d.usable_from.replace('T', ' ').slice(0, 16)} UTC`
      : 'Security waiting period'
  }
  if (d.status === 'ACTIVE') return 'Ready for automatic payouts'
  return STATUS_TEXT[d.status] ?? d.status
}

export default function AdminSoncoPayPayouts() {
  const [view, setView] = useState<PayoutsView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [phrase, setPhrase] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  const load = useCallback(async (provider = false) => {
    setError(null)
    const res = await api.get(`/api/v1/admin/finance/soncopay/payouts${provider ? '?provider=true' : ''}`)
    if (res.status === 200) setView(res.data)
    else setError(financeErrorText(res, 'The SoncoPay payouts could not be loaded.'))
  }, [])

  useEffect(() => { void load() }, [load])

  const post = async (path: string, body: object, done: string) => {
    setBusy(true); setError(null); setMessage(null)
    const res = await api.post(`/api/v1/admin/finance/soncopay/payouts${path}`, body)
    setPassword(''); setPhrase('')
    if (res.status === 200) {
      setMessage(done)
      await load()
    } else {
      setError(financeErrorText(res, 'Nothing was changed.'))
    }
    setBusy(false)
  }

  if (!view) {
    return <p className="text-sm text-gray-500" role="status">{error ?? 'Loading SoncoPay payouts…'}</p>
  }
  const facts = view.provider
  return (
    <Card>
      <CardContent className="space-y-6 pt-6" data-testid="soncopay-payouts">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">SoncoPay Payouts</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Each available direct commission is paid on its own, in USDT on BNB Smart Chain (BEP20), to the member&apos;s
            approved wallet once SoncoPay has confirmed it as a payout destination and its security waiting period is
            over. The member receives the commission less SoncoPay&apos;s network fee.
          </p>
        </div>

        <section className="space-y-2" aria-labelledby="sp-blockers">
          <h3 id="sp-blockers" className="text-sm font-semibold">Readiness</h3>
          {view.blockers.length === 0
            ? <p className="text-sm text-green-700 dark:text-green-400" data-testid="sp-ready">
                SoncoPay payouts are configured. Payouts still need the server activation and the Crypto Cashout settings.
              </p>
            : <ul className="list-disc pl-5 text-sm text-amber-700 dark:text-amber-300" data-testid="sp-blockers">
                {view.blockers.map((b) => <li key={b.code}>{b.message}</li>)}
              </ul>}
        </section>

        <section className="space-y-2" aria-labelledby="sp-auth">
          <h3 id="sp-auth" className="text-sm font-semibold">Owner authorization</h3>
          {view.authorization
            ? <div className="text-sm space-y-2">
                <p data-testid="sp-authorized">Recorded {view.authorization.authorized_at.replace('T', ' ').slice(0, 16)} UTC
                  {view.authorization.note ? `: ${view.authorization.note}` : ''}</p>
                <div className="flex flex-wrap items-end gap-2">
                  <input type="password" aria-label="Current password" className={inputClass} value={password}
                    autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
                  <Button variant="outline" disabled={busy || !password}
                    onClick={() => post('/authorization/revoke', { current_password: password }, 'Authorization withdrawn.')}>
                    Withdraw authorization
                  </Button>
                </div>
              </div>
            : <div className="grid gap-2 max-w-xl">
                <p className="text-xs text-gray-500">
                  Record here that SoncoPay confirmed member commission payouts are allowed from this merchant account.
                  Nothing is registered at SoncoPay or paid before it.
                </p>
                <label className="text-sm" htmlFor="sp-note">Where SoncoPay confirmed it</label>
                <input id="sp-note" className={inputClass} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
                <label className="text-sm" htmlFor="sp-phrase">Type <code>{view.confirmation_phrase}</code></label>
                <input id="sp-phrase" className={inputClass} value={phrase} autoComplete="off"
                  onChange={(e) => setPhrase(e.target.value)} />
                <label className="text-sm" htmlFor="sp-password">Current password</label>
                <input id="sp-password" type="password" className={inputClass} value={password}
                  autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
                <Button disabled={busy || !password || !phrase || note.trim().length < 10}
                  onClick={() => post('/authorization', { note, confirmation: phrase, current_password: password },
                    'Authorization recorded.')}>
                  Record authorization
                </Button>
              </div>}
        </section>

        <section className="space-y-2" aria-labelledby="sp-provider">
          <div className="flex items-center gap-3">
            <h3 id="sp-provider" className="text-sm font-semibold">SoncoPay account</h3>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => load(true)}>Read from SoncoPay</Button>
            <Button variant="outline" size="sm" disabled={busy}
              onClick={() => post('/sync', {}, 'A payout cycle was requested.')}>Run a cycle now</Button>
          </div>
          {facts?.error && <p className="text-sm text-red-600" role="alert">SoncoPay could not be read: {facts.error}</p>}
          {facts && !facts.error && (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm max-w-xl" data-testid="sp-facts">
              <dt>Available USDT</dt><dd>{facts.balance?.available ?? facts.balance?.balances ?? '—'}</dd>
              <dt>Reserved USDT</dt><dd>{facts.balance?.reserved ?? '0'}</dd>
              <dt>Network fee (USDT:BSC)</dt><dd>{facts.fee ?? 'not published'}</dd>
              <dt>Minimum payout (USD)</dt><dd>{String(facts.min_payout_usd ?? '—')}</dd>
              <dt>Open destinations</dt><dd>{facts.open_destinations ?? '—'} of {view.destination_limit}</dd>
              <dt>Waiting period (hours)</dt><dd>{String(facts.settings?.cooldown_hours ?? '—')}</dd>
              <dt>Automatic confirmation</dt><dd>{facts.settings?.api_auto_confirm ? 'On' : 'Off'}</dd>
            </dl>
          )}
        </section>

        <section className="space-y-2" aria-labelledby="sp-destinations">
          <h3 id="sp-destinations" className="text-sm font-semibold">Member destinations</h3>
          <p className="text-xs text-gray-500">
            A destination awaiting confirmation must be confirmed by a SoncoPay operator in the SoncoPay dashboard
            (Withdrawal methods). No other member&apos;s destination is ever disabled to free one of the {view.destination_limit} slots.
          </p>
          {view.destinations.length === 0
            ? <p className="text-sm text-gray-500">No approved wallet yet.</p>
            : <table className="w-full text-sm" data-testid="sp-destination-table">
                <thead><tr className="text-left text-gray-500"><th>Member</th><th>Wallet</th><th>State</th><th>Note</th></tr></thead>
                <tbody>
                  {view.destinations.map((d) => (
                    <tr key={d.id} className="border-t border-gray-100 dark:border-gray-800">
                      <td>{d.username} (#{d.user_id})</td>
                      <td className="font-mono">{d.address}</td>
                      <td>{destinationText(d)}</td>
                      <td className="text-xs text-gray-500">{d.last_error ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>}
        </section>
        {message && <p className="text-sm text-green-700" role="status">{message}</p>}
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
      </CardContent>
    </Card>
  )
}
