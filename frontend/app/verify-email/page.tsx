'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Loader2, CheckCircle, XCircle, MailCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { authService } from '@/lib/api'
import { takeLinkToken } from '@/lib/one-time-link'

type Phase = 'loading' | 'success' | 'error'

const INVALID_LINK =
  'This link is invalid, has expired or has already been used. If you already confirmed your email, you can simply sign in. Otherwise, ask for a new link below.'

/**
 * Email verification. The one-time credential arrives in the URL fragment
 * (never sent to a server), is removed from the address bar at once and is
 * exchanged over POST. When the link cannot be used, a new one can be
 * requested here.
 */
export default function VerifyEmailPage() {
  const [phase, setPhase] = useState<Phase>('loading')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')
  const [resendState, setResendState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [resendMessage, setResendMessage] = useState('')
  // The credential works once: never submit it twice (React re-runs effects in development).
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true

    const token = takeLinkToken()
    if (!token) {
      setPhase('error')
      setMessage(INVALID_LINK)
      return
    }
    ;(async () => {
      try {
        await authService.verifyEmail(token)
        setPhase('success')
        setMessage('Your email address has been confirmed.')
      } catch {
        setPhase('error')
        setMessage(INVALID_LINK)
      }
    })()
  }, [])

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || resendState === 'sending') return
    setResendState('sending')
    try {
      const data = await authService.resendVerification(email.trim())
      setResendState('sent')
      setResendMessage(
        data?.message ||
          'If this address belongs to an account that still needs to be confirmed, a new confirmation link has been sent.',
      )
    } catch (err: unknown) {
      setResendState('error')
      setResendMessage((err as { message?: string })?.message || 'The request could not be sent. Please try again later.')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 shadow-sm text-center space-y-4">
        {phase === 'loading' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto text-blue-600 animate-spin" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Verifying your email</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">Please wait…</p>
          </>
        )}
        {phase === 'success' && (
          <>
            <CheckCircle className="w-12 h-12 mx-auto text-green-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Email verified</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">{message}</p>
            <Button asChild className="w-full rounded-xl mt-2">
              <Link href="/login">Continue to sign in</Link>
            </Button>
          </>
        )}
        {phase === 'error' && (
          <>
            <XCircle className="w-12 h-12 mx-auto text-red-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Could not verify</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">{message}</p>

            {resendState === 'sent' ? (
              <div className="rounded-xl bg-green-50 dark:bg-green-900/20 p-4 text-sm text-green-800 dark:text-green-200" role="status">
                <MailCheck className="w-5 h-5 inline-block mr-2" aria-hidden />
                {resendMessage}
              </div>
            ) : (
              <form onSubmit={handleResend} className="space-y-3 text-left" aria-label="Request a new verification link">
                <label htmlFor="resend-email" className="block text-sm font-medium text-gray-700 dark:text-gray-200">
                  Your email address
                </label>
                <Input
                  id="resend-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="h-11 rounded-xl"
                />
                {resendState === 'error' && (
                  <p className="text-sm text-red-600" role="alert">
                    {resendMessage}
                  </p>
                )}
                <Button type="submit" className="w-full rounded-xl" disabled={resendState === 'sending'}>
                  {resendState === 'sending' ? 'Sending…' : 'Send a new verification link'}
                </Button>
              </form>
            )}

            <Button asChild variant="outline" className="w-full rounded-xl mt-2">
              <Link href="/login">Back to sign in</Link>
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
