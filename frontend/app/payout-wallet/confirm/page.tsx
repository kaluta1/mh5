'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { CheckCircle, Loader2, LogIn, XCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import api from '@/lib/api'
import { formatDate } from '@/lib/cashout'
import { takeLink } from '@/lib/one-time-link'

/**
 * loading   the one-time link is being exchanged;
 * success   the wallet is confirmed and its security hold has started;
 * sign_in   the member is not signed in (the link is NOT consumed);
 * busy      a payout is in progress: the same link can be opened again later;
 * error     the link cannot be used (one answer for every reason).
 */
type Phase = 'loading' | 'success' | 'sign_in' | 'busy' | 'error'
type Confirmed = { wallet: string | null; network: string | null; payable_from: string | null }

/**
 * Payout wallet confirmation. The one-time token arrives in the URL fragment
 * (never sent to a server), is removed from the address bar and is exchanged
 * over POST, only for the signed-in account it was issued to.
 */
export default function ConfirmPayoutWalletPage() {
  const [phase, setPhase] = useState<Phase>('loading')
  const [confirmed, setConfirmed] = useState<Confirmed | null>(null)
  // The token works once: never submit it twice (React re-runs effects in development).
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    if (!localStorage.getItem('access_token')) {
      setPhase('sign_in') // the link stays in the address bar, unused
      return
    }
    const link = takeLink()
    if (link.kind !== 'current') {
      setPhase('error')
      return
    }
    ;(async () => {
      try {
        const res = await api.post('/api/v1/wallet/payout-wallet/confirm', { token: link.token })
        if (res.status === 200) {
          setConfirmed(res.data as Confirmed)
          setPhase('success')
        } else if (res.status === 401) {
          setPhase('sign_in')
        } else if (res.data?.detail?.code === 'PAYOUT_IN_PROGRESS') {
          setPhase('busy')
        } else {
          setPhase('error')
        }
      } catch {
        setPhase('error')
      }
    })()
  }, [])

  const toSettings = (
    <Button asChild variant="outline" className="w-full rounded-xl mt-2">
      <Link href="/dashboard/settings?tab=wallet">Payout wallet settings</Link>
    </Button>
  )

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 shadow-sm text-center space-y-4">
        {phase === 'loading' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto text-blue-600 animate-spin" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Confirming your payout wallet</h1>
          </>
        )}
        {phase === 'success' && (
          <>
            <CheckCircle className="w-12 h-12 mx-auto text-green-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Payout wallet confirmed</h1>
            <p className="text-sm text-gray-600 dark:text-gray-300" role="status">
              {confirmed?.wallet ? <span className="font-mono">{confirmed.wallet}</span> : 'Your wallet'}
              {confirmed?.network ? ` (${confirmed.network})` : ''} is now your payout wallet. For your security,
              payouts to it start on {formatDate(confirmed?.payable_from)}.
            </p>
            {toSettings}
          </>
        )}
        {phase === 'sign_in' && (
          <>
            <LogIn className="w-12 h-12 mx-auto text-blue-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Sign in to confirm</h1>
            <p className="text-sm text-gray-600 dark:text-gray-300" role="status">
              Sign in to your MyHigh5 account in this browser, then open the link from your email again. The link has
              not been used.
            </p>
            <Button asChild className="w-full rounded-xl">
              <Link href="/login">Sign in</Link>
            </Button>
          </>
        )}
        {phase === 'busy' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto text-amber-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">A payout is in progress</h1>
            <p className="text-sm text-gray-600 dark:text-gray-300" role="status">
              Your wallet cannot be changed while a payout is being sent. Open the link from your email again when the
              payout has finished, or request a new link in Settings.
            </p>
            {toSettings}
          </>
        )}
        {phase === 'error' && (
          <>
            <XCircle className="w-12 h-12 mx-auto text-red-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">This link cannot be used</h1>
            <p className="text-sm text-gray-600 dark:text-gray-300" role="alert">
              The confirmation link is not valid, has expired or was already used. Your payout wallet has not been
              changed. You can request a new link in Settings.
            </p>
            {toSettings}
          </>
        )}
      </div>
    </div>
  )
}
