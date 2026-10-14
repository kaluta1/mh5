'use client'

import { useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { financeErrorText } from '@/lib/finance-admin'
import { kycGrantSessionUrl } from '@/lib/kyc-settings'
import { inputClass } from './admin-finance-ui'

const OPEN = new Set(['pending', 'in_progress', 'expired'])
export const SESSIONS_PER_ATTEMPT = 3

type Verification = {
  id: number
  status: string
  attempt_sessions_count?: number | null
  attempt_sessions_granted?: number | null
}

/** Sessions the member can still open for the current attempt (null when unknown). */
export function sessionsLeft(v: Verification, perAttempt = SESSIONS_PER_ATTEMPT): number | null {
  if (v.attempt_sessions_count === undefined || v.attempt_sessions_count === null) return null
  return Math.max(0, perAttempt + (v.attempt_sessions_granted || 0) - v.attempt_sessions_count)
}

/**
 * Admin > KYC > verification detail: allow ONE more provider session for a
 * member whose open attempt used every session it had. No payment and no new
 * attempt. The server decides (manage_kyc_settings + current password) and
 * audits it.
 */
export default function AdminKycSessionGrant({ verification, onGranted }: {
  verification: Verification
  onGranted?: () => void
}) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const left = sessionsLeft(verification)
  if (!OPEN.has(verification.status) || left === null) return null

  const grant = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    const sent = password
    setPassword('')
    const res = await api.post(kycGrantSessionUrl(verification.id), { current_password: sent })
    if (res.status === 200) {
      setNotice('One more session allowed. The member can now get a new verification link.')
      onGranted?.()
    } else {
      setError(financeErrorText(res, 'The session could not be allowed.'))
    }
    setBusy(false)
  }

  return (
    <div className="pt-2 border-t border-gray-200 dark:border-gray-600 space-y-2" data-testid="kyc-session-grant">
      <p className="text-sm">
        Provider sessions left for this attempt: <span className="font-semibold">{left}</span>
      </p>
      {left === 0 && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <label htmlFor={`kyc-grant-password-${verification.id}`} className="block text-xs font-medium">
              Your current password
            </label>
            <input id={`kyc-grant-password-${verification.id}`} type="password" autoComplete="current-password"
              className={inputClass} value={password} disabled={busy} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <Button size="sm" variant="outline" onClick={() => void grant()} disabled={busy || !password}>
            {busy ? 'Saving…' : 'Allow one more session'}
          </Button>
        </div>
      )}
      {notice && <p className="text-sm text-green-700 dark:text-green-300" role="status">{notice}</p>}
      {error && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>}
    </div>
  )
}
