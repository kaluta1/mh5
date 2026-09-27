'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import {
  interactionErrorMessage,
  interactionService,
  type ContactStatus,
  type ReportReason,
} from '@/services/interaction-service'

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'HARASSMENT', label: 'Harassment' },
  { value: 'INAPPROPRIATE_CONTENT', label: 'Inappropriate content' },
  { value: 'PERSONAL_INFORMATION', label: 'Sharing personal information' },
  { value: 'CHILD_SAFETY', label: 'Child safety concern' },
  { value: 'SPAM', label: 'Spam' },
  { value: 'OTHER', label: 'Other' },
]

interface Props {
  partnerId: number
  /** Reports whether a NEW message may be sent (the backend still decides). */
  onStatus: (status: ContactStatus | null) => void
}

/** Block / report controls for one conversation partner (Phase 9). */
export function ThreadSafetyControls({ partnerId, onStatus }: Props) {
  const { addToast } = useToast()
  const [status, setStatus] = useState<ContactStatus | null>(null)
  const [reason, setReason] = useState<ReportReason>('HARASSMENT')
  const [busy, setBusy] = useState(false)

  const refresh = async () => {
    try {
      const next = await interactionService.contactStatus(partnerId)
      setStatus(next)
      onStatus(next)
    } catch {
      setStatus(null)
      onStatus({ user_id: partnerId, can_message: false, blocked_by_me: false }) // fail closed
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partnerId])

  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try {
      await action()
      addToast(done, 'success')
      await refresh()
    } catch (error) {
      addToast(interactionErrorMessage(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="thread-safety-controls">
      {status?.blocked_by_me ? (
        <Button size="sm" variant="outline" disabled={busy}
          onClick={() => run(() => interactionService.unblock(partnerId), 'Member unblocked.')}>
          Unblock
        </Button>
      ) : (
        <Button size="sm" variant="outline" disabled={busy}
          onClick={() => run(() => interactionService.block(partnerId), 'Member blocked.')}>
          Block
        </Button>
      )}
      <select
        aria-label="Report reason"
        className="h-8 rounded-md border border-gray-300 bg-transparent px-2 dark:border-gray-600"
        value={reason}
        onChange={(e) => setReason(e.target.value as ReportReason)}
      >
        {REASONS.map((r) => (
          <option key={r.value} value={r.value}>{r.label}</option>
        ))}
      </select>
      <Button size="sm" variant="outline" disabled={busy}
        onClick={() => run(() => interactionService.report('user', partnerId, reason), 'Thanks. Our team will review this.')}>
        Report
      </Button>
    </div>
  )
}
