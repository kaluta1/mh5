'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  CASHOUTS_BASE,
  FEE_EVENT_LABEL,
  FEE_FLAG_LABEL,
  RECONCILIATION_LABEL,
  REVIEW_NOTE_MAX,
  REVIEW_NOTE_MIN,
  dateTime,
  financeErrorText,
  humanize,
  validReviewNote,
  type FeeEvent,
  type FeeException,
  type FeeExceptionList,
} from '@/lib/finance-admin'
import { Row, TonePill, inputClass } from './admin-finance-ui'

/**
 * Flagged Payout Review.
 *
 * A completed payout that did not add up is flagged by the backend. An
 * administrator with the process_cashouts permission looks at it here and
 * records that they did, with their password and a written note.
 *
 * A review is a record and nothing else, and the screen says so: it does not
 * clear the flag, does not verify the payout's actual fee, does not lift a
 * payout suspension and does not allow a new payout. There is no control here
 * that sends, releases or reactivates anything.
 */
type Filter = '' | 'PENDING' | 'REVIEWED'

const show = (value: string | null | undefined) => value ?? '-'

export function FlaggedPayoutReview({ canProcess }: { canProcess: boolean }) {
  const [filter, setFilter] = useState<Filter>('PENDING')
  const [list, setList] = useState<FeeExceptionList | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)
  const [events, setEvents] = useState<FeeEvent[]>([])
  const [note, setNote] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [unavailable, setUnavailable] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const res = await api.get(`${CASHOUTS_BASE}/fee-exceptions`, { params: filter ? { state: filter, limit: 50 } : { limit: 50 } })
    if (res.status === 200) {
      setList(res.data)
      setUnavailable(false)
    } else setUnavailable(true)
  }, [filter])

  useEffect(() => { void load() }, [load])

  const open = async (id: number) => {
    setOpenId(id)
    setNote('')
    setPassword('')
    setError('')
    setNotice('')
    setEvents([])
    const res = await api.get(`${CASHOUTS_BASE}/${id}`)
    if (res.status === 200) setEvents(res.data.fee_events ?? [])
  }

  const review = async (item: FeeException) => {
    const sentPassword = password
    setPassword('')
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const res = await api.post(`${CASHOUTS_BASE}/${item.cashout_id}/fee-review`, {
        note: note.trim(), current_password: sentPassword,
      })
      if (res.status === 200) {
        setNotice(`Review of cashout #${item.cashout_id} recorded. Nothing else was changed: the flag, the payout and any suspension are as they were.`)
        setNote('')
        setOpenId(null)
        await load()
      } else setError(financeErrorText(res, 'The review could not be recorded.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3" data-testid="flagged-payout-review">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-gray-900 dark:text-white">Flagged Payout Review</h2>
          {list && (
            <span className="flex items-center gap-2 text-xs text-gray-500" data-testid="flagged-counts">
              <TonePill tone={list.pending_count > 0 ? 'red' : 'green'}>{list.pending_count} to review</TonePill>
              <span>{list.reviewed_count} reviewed</span>
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500">
          A completed crypto payout is flagged when the provider did not do what was configured: it charged its fee to
          MyHigh5, reported an amount that does not agree, or took a fee above the member&apos;s limit. Reviewing one
          records who looked at it, when, and what they found. It does not clear the flag, does not count as
          verifying the payout&apos;s actual fee, does not lift a suspension and does not allow a new payout. The
          payout and its accounting entry are never changed here.
        </p>
        {list?.payout_suspension && (
          <p className="text-sm text-red-700 dark:text-red-300" data-testid="review-suspension">
            Crypto payouts are suspended ({humanize(list.payout_suspension.reason)}). They stay suspended after a
            review: reactivation is a separate step in Crypto Cashout Settings, and it is refused while a flagged
            payout is not reviewed or its actual fee is not verified.
          </p>
        )}
        <div className="flex flex-wrap gap-2" role="group" aria-label="Review state">
          {([['PENDING', 'To review'], ['REVIEWED', 'Reviewed'], ['', 'All']] as [Filter, string][]).map(([value, label]) => (
            <Button key={label} size="sm" variant={filter === value ? 'default' : 'outline'} aria-pressed={filter === value}
              onClick={() => { setOpenId(null); setFilter(value) }}>
              {label}
            </Button>
          ))}
        </div>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        {notice && <p role="status" className="text-sm text-green-700 dark:text-green-400">{notice}</p>}
        {unavailable && <p className="text-sm text-gray-500">The flagged payouts could not be loaded.</p>}
        {list && list.items.length === 0 && (
          <p className="text-sm text-gray-500" data-testid="flagged-empty">
            {filter === 'PENDING' ? 'No flagged payout is waiting for a review.' : 'No flagged payout.'}
          </p>
        )}
        {list?.items.map((item) => (
          <FlaggedPayout key={item.cashout_id} item={item} open={openId === item.cashout_id} events={events}
            canProcess={canProcess} busy={busy} note={note} password={password} onOpen={() => void open(item.cashout_id)}
            onClose={() => setOpenId(null)} onNote={setNote} onPassword={setPassword} onReview={() => void review(item)} />
        ))}
      </CardContent>
    </Card>
  )
}

function FlaggedPayout({ item, open, events, canProcess, busy, note, password, onOpen, onClose, onNote, onPassword, onReview }: {
  item: FeeException; open: boolean; events: FeeEvent[]; canProcess: boolean; busy: boolean; note: string; password: string
  onOpen: () => void; onClose: () => void; onNote: (value: string) => void; onPassword: (value: string) => void
  onReview: () => void
}) {
  const review = item.review
  const reviewed = review.state === 'REVIEWED'
  const currency = item.payout_currency ?? 'payout currency'
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-3" data-testid={`flagged-${item.cashout_id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm">
          <span className="font-medium text-gray-900 dark:text-white">Cashout #{item.cashout_id}</span>{' '}
          <span className="text-gray-500">{item.username ?? 'Member'} #{item.user_id} · completed {dateTime(item.processed_at)}</span>
        </div>
        <span className="flex items-center gap-2">
          {item.caused_suspension && <TonePill tone="red">Caused the suspension</TonePill>}
          <TonePill tone={reviewed ? 'green' : 'red'}>{reviewed ? 'Reviewed' : 'Not reviewed'}</TonePill>
          <Button size="sm" variant="outline" onClick={open ? onClose : onOpen}>{open ? 'Close' : 'Details'}</Button>
        </span>
      </div>
      <p className="text-sm text-red-700 dark:text-red-300" data-testid={`flagged-reason-${item.cashout_id}`}>
        Why it was flagged: {FEE_FLAG_LABEL[item.flag] ?? item.flag_message ?? humanize(item.flag)}
      </p>
      {reviewed && (
        <p className="text-sm text-gray-700 dark:text-gray-300" data-testid={`flagged-review-${item.cashout_id}`}>
          Reviewed by administrator #{review.reviewed_by} on {dateTime(review.reviewed_at)}: {review.note}
        </p>
      )}
      {review.superseded && (
        <p className="text-sm text-amber-800 dark:text-amber-200" data-testid={`flagged-superseded-${item.cashout_id}`}>
          An earlier review (administrator #{review.reviewed_by}, {dateTime(review.reviewed_at)}) covered{' '}
          {humanize(review.reviewed_flag)}. The payout has been flagged for something else since and needs a new review.
        </p>
      )}
      {open && (
        <div className="space-y-3 border-t border-gray-200 dark:border-gray-700 pt-3" data-testid={`flagged-detail-${item.cashout_id}`}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <div>
              <h3 className="font-semibold mb-1">Expected ({currency})</h3>
              <dl className="space-y-1">
                <Row label="Handed to the provider" value={show(item.expected.amount_sent)} />
                <Row label="Provider's fee estimate" value={show(item.expected.network_fee_estimate)} />
                <Row label="Estimate with the safety margin" value={show(item.expected.network_fee_estimate_adjusted)} />
                <Row label="Member's limit for the estimate" value={show(item.expected.fee_cap)} />
                <Row label="Member expected to receive (by the estimate)" value={show(item.expected.received)} />
              </dl>
            </div>
            <div>
              <h3 className="font-semibold mb-1">Actual ({currency})</h3>
              <dl className="space-y-1">
                <Row label="Actual network fee" value={<span data-testid="actual-fee">{item.actual.network_fee ?? 'Not recorded'}</span>} />
                <Row label="Member received" value={<span data-testid="actual-received">{item.actual.received ?? 'Not recorded'}</span>} />
                <Row label="Fee above the estimate" value={show(item.actual.fee_above_estimate)} />
                <Row label="Fee above the member's limit" value={
                  <span className={item.actual.fee_above_cap ? 'text-red-700 dark:text-red-300' : ''}>{show(item.actual.fee_above_cap)}</span>} />
                <Row label="Received, compared with the estimate" value={show(item.actual.received_difference)} />
              </dl>
            </div>
          </div>
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1 text-sm">
            <Row label="Provider payout ID" value={<span className="font-mono text-xs">{show(item.provider_batch_id)}</span>} />
            <Row label="Provider status" value={show(item.provider_status)} />
            <Row label="Destination wallet" value={<span className="font-mono text-xs">{show(item.destination)}</span>} />
            <Row label="Provider fee behaviour configured" value={humanize(item.provider_fee_mode) || '-'} />
            <Row label="Evidence for the actual fee" value={item.evidence.evidence ? humanize(item.evidence.evidence) : 'None recorded'} />
            <Row label="Reconciliation of the actual fee" value={
              <span data-testid="exception-reconciliation" className={item.evidence.reconciled ? '' : 'text-amber-800 dark:text-amber-200'}>
                {item.evidence.reconciliation
                  ? RECONCILIATION_LABEL[item.evidence.reconciliation] ?? humanize(item.evidence.reconciliation)
                  : 'Nothing recorded'}
                {!item.evidence.reconciled && ' · not reconciled'}
              </span>} />
            {Object.entries(item.flag_details).map(([key, value]) => (
              <Row key={key} label={`Reported when flagged: ${humanize(key).toLowerCase()}`} value={show(value)} />
            ))}
          </dl>
          {!item.evidence.reconciled && (
            <p className="text-xs text-amber-800 dark:text-amber-200" data-testid="exception-unreconciled">
              The actual fee of this payout is not verified. A review does not change that: record the verified fee in
              Cashout Transactions. Until then this payout keeps new payouts on hold.
            </p>
          )}
          {events.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-1">History of this payout&apos;s fee</h3>
              <ul className="text-xs text-gray-700 dark:text-gray-300 space-y-1" data-testid="exception-events">
                {events.map((e) => (
                  <li key={e.id}>{dateTime(e.created_at)} · {FEE_EVENT_LABEL[e.action] ?? humanize(e.action)} ·{' '}
                    {e.actor_id ? `administrator or member #${e.actor_id}` : 'system'}</li>
                ))}
              </ul>
            </div>
          )}
          {!reviewed && !canProcess && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Reviewing a flagged payout needs the <code>process_cashouts</code> permission.
            </p>
          )}
          {!reviewed && canProcess && (
            <div className="space-y-3" data-testid="review-form">
              <div className="space-y-1">
                <label htmlFor={`review-note-${item.cashout_id}`} className="block text-sm font-medium">
                  What you checked and what you found
                </label>
                <textarea id={`review-note-${item.cashout_id}`} className={inputClass} rows={3} maxLength={REVIEW_NOTE_MAX}
                  value={note} disabled={busy} onChange={(e) => onNote(e.target.value)} />
                <p className="text-xs text-gray-500">
                  At least {REVIEW_NOTE_MIN} characters. Kept with the payout and in the audit trail under your name;
                  a review is recorded once and cannot be replaced.
                </p>
              </div>
              <div className="space-y-1">
                <label htmlFor={`review-password-${item.cashout_id}`} className="block text-sm font-medium">Your current password</label>
                <input id={`review-password-${item.cashout_id}`} type="password" autoComplete="current-password"
                  className={inputClass} value={password} disabled={busy} onChange={(e) => onPassword(e.target.value)} />
              </div>
              <Button variant="outline" disabled={busy || !password || !validReviewNote(note)} onClick={onReview}>
                Mark as reviewed
              </Button>
              <p className="text-xs text-gray-500">
                This records your review only. It sends nothing, releases nothing and reactivates nothing.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
