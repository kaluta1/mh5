'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2 } from 'lucide-react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/use-auth'
import { readFragmentToken } from '@/lib/guardian-consent'

const STORAGE_KEY = 'mh5-nominee-claim'

type Summary = { entry_title: string | null; contest_name: string | null; expires_at: string }

/**
 * Nominee claim page (Child/Teen Safety s.12). The single-use token comes from
 * the URL fragment (never sent to servers in a URL) and is posted in the body.
 * The server decides everything: confirming only links the signed-in account
 * as the nominee. It never makes the entry public by itself and never makes
 * anyone a guardian.
 */
export default function NomineeClaimPage() {
  const { isAuthenticated, isLoading } = useAuth()
  const [token, setToken] = useState('')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [state, setState] = useState<'loading' | 'signin' | 'invalid' | 'ready' | 'done'>('loading')
  const [result, setResult] = useState<{ status: string; next_step: string | null } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const fromHash = readFragmentToken(typeof window !== 'undefined' ? window.location.hash : '')
    let stored = ''
    try {
      if (fromHash) sessionStorage.setItem(STORAGE_KEY, fromHash)
      stored = sessionStorage.getItem(STORAGE_KEY) || ''
    } catch {
      stored = fromHash
    }
    if (fromHash && typeof window !== 'undefined') {
      window.history.replaceState(null, '', window.location.pathname) // keep the token out of history
    }
    setToken(fromHash || stored)
  }, [])

  useEffect(() => {
    if (isLoading) return
    if (!token) {
      setState('invalid')
      return
    }
    if (!isAuthenticated) {
      setState('signin')
      return
    }
    api.post('/api/v1/contest-eligibility/claims/summary', { token }).then((res) => {
      if (res.status === 200) {
        setSummary(res.data)
        setState('ready')
      } else {
        setState('invalid')
      }
    }).catch(() => setState('invalid'))
  }, [token, isAuthenticated, isLoading])

  const respond = async (decision: 'ACCEPT' | 'DECLINE') => {
    setError('')
    setBusy(true)
    try {
      const res = await api.post('/api/v1/contest-eligibility/claims/respond', { token, decision })
      if (res.status === 200) {
        setResult(res.data)
        setState('done')
        try { sessionStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
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
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">You were nominated</h1>
        {state === 'loading' && <Loader2 className="h-5 w-5 animate-spin" />}
        {state === 'invalid' && (
          <p className="text-gray-700 dark:text-gray-200">This link is invalid or has expired.</p>
        )}
        {state === 'signin' && (
          <div className="space-y-3">
            <p className="text-gray-700 dark:text-gray-200">
              Please sign in (or create an account) with your own details to confirm or decline this nomination.
            </p>
            <Link href="/login?returnUrl=/nominations/claim" className="text-blue-600 underline">Sign in</Link>
          </div>
        )}
        {state === 'ready' && summary && (
          <div className="space-y-4">
            <p className="text-gray-700 dark:text-gray-200">
              Someone nominated <strong>{summary.entry_title || 'your work'}</strong>
              {summary.contest_name ? <> in <strong>{summary.contest_name}</strong></> : null}.
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Confirm only if this is your own work. Your entry stays private until all required checks are complete.
              If you are under 18, a verified parent or guardian must give consent first. The person who nominated
              you does not become your guardian.
            </p>
            {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
            <div className="flex gap-2">
              <Button disabled={busy} onClick={() => respond('ACCEPT')}>This is my work — confirm</Button>
              <Button disabled={busy} variant="outline" onClick={() => respond('DECLINE')}>Decline</Button>
            </div>
          </div>
        )}
        {state === 'done' && result && (
          <div className="space-y-3 text-gray-700 dark:text-gray-200">
            {result.status === 'DECLINED' ? (
              <p>You declined this nomination. It will not be shown publicly.</p>
            ) : result.next_step === 'ADD_DATE_OF_BIRTH' ? (
              <>
                <p>Thank you. The nomination is on hold because your date of birth is missing from your account.
                  Please update your profile; we will check again automatically.</p>
                <Link href="/dashboard/settings" className="text-blue-600 underline">Update my profile</Link>
              </>
            ) : result.next_step ? (
              <p>Thank you. The nomination is on hold until the remaining checks are complete.</p>
            ) : (
              <p>Thank you. The nomination is now confirmed.</p>
            )}
          </div>
        )}
      </div>
    </main>
  )
}
