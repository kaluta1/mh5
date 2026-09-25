'use client'

import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { GUARDIAN_SCOPE_LABELS, readFragmentToken } from '@/lib/guardian-consent'

type Summary = { username: string | null; available_scopes: string[]; required_scope: string }

/**
 * Guardian review page. The token comes from the URL fragment (never sent to
 * servers) and is posted in the request body. The server decides validity,
 * verification and the resulting status; this page only displays them.
 */
export default function GuardianConsentPage() {
  const [token, setToken] = useState('')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [state, setState] = useState<'loading' | 'invalid' | 'ready' | 'done'>('loading')
  const [relationship, setRelationship] = useState('')
  const [scopes, setScopes] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const raw = readFragmentToken(typeof window !== 'undefined' ? window.location.hash : '')
    if (!raw) {
      setState('invalid')
      return
    }
    setToken(raw)
    api.post('/api/v1/guardian/requests/lookup', { token: raw }).then((res) => {
      if (res.status === 200) {
        setSummary(res.data)
        setScopes([res.data.required_scope])
        setState('ready')
      } else {
        setState('invalid')
      }
    }).catch(() => setState('invalid'))
  }, [])

  const toggle = (scope: string) =>
    setScopes((prev) => (prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]))

  const respond = async (decision: 'APPROVE' | 'DECLINE') => {
    setError('')
    if (decision === 'APPROVE' && !relationship) {
      setError('Please state your relationship to the applicant.')
      return
    }
    setBusy(true)
    try {
      const res = await api.post('/api/v1/guardian/requests/respond', {
        token, decision, relationship_type: decision === 'APPROVE' ? relationship : undefined,
        scopes: decision === 'APPROVE' ? scopes : [],
      })
      if (res.status === 200) {
        setMessage(res.data.message)
        setState('done')
      } else if (res.status === 404) {
        setState('invalid')
      } else {
        setError(res.data?.detail?.message || 'Your response could not be recorded.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4">
      <div className="w-full max-w-xl bg-white dark:bg-gray-800 rounded-2xl shadow p-6 space-y-4">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Parent or guardian approval</h1>
        {state === 'loading' && <Loader2 className="h-5 w-5 animate-spin" />}
        {state === 'invalid' && (
          <p className="text-gray-700 dark:text-gray-200">This link is invalid or has expired.</p>
        )}
        {state === 'done' && <p className="text-gray-700 dark:text-gray-200">{message}</p>}
        {state === 'ready' && summary && (
          <>
            <p className="text-gray-700 dark:text-gray-200">
              Someone using the username <strong>{summary.username}</strong> asked to create a MyHigh5 account
              and named you as their parent or legal guardian. Approving the account does not approve anything
              else: choose each permission separately.
            </p>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200">
              Your relationship to the applicant
              <select
                className="mt-1 w-full rounded-lg border border-gray-300 p-2 dark:bg-gray-700"
                value={relationship}
                onChange={(e) => setRelationship(e.target.value)}
              >
                <option value="">Select…</option>
                <option value="PARENT">Parent</option>
                <option value="LEGAL_GUARDIAN">Legal guardian</option>
              </select>
            </label>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-gray-700 dark:text-gray-200">Permissions</legend>
              {summary.available_scopes.map((scope) => (
                <label key={scope} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope)}
                    disabled={scope === summary.required_scope}
                    onChange={() => toggle(scope)}
                  />
                  <span>{GUARDIAN_SCOPE_LABELS[scope] || scope}</span>
                </label>
              ))}
            </fieldset>
            <p className="text-xs text-gray-500">
              Your authority as parent or guardian must be verified by MyHigh5 before the account can be created.
            </p>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex gap-3">
              <Button disabled={busy} onClick={() => respond('APPROVE')}>Approve selected</Button>
              <Button disabled={busy} variant="outline" onClick={() => respond('DECLINE')}>Decline</Button>
            </div>
          </>
        )}
      </div>
    </main>
  )
}
