'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Loader2, CheckCircle, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { authService } from '@/lib/api'

function VerifyEmailContent() {
  const searchParams = useSearchParams()
  const [phase, setPhase] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const token = searchParams.get('token')
    if (!token?.trim()) {
      setPhase('error')
      setMessage(
        'This link is missing the verification token. Open the link from your welcome email, or request a new email from support.',
      )
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        const data = await authService.verifyEmail(token)
        if (cancelled) return
        setPhase('success')
        setMessage(data?.message || 'Your email has been verified.')
      } catch (e: unknown) {
        if (cancelled) return
        setPhase('error')
        const err = e as { message?: string }
        setMessage(err?.message || 'Verification failed. The link may have expired.')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [searchParams])

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
            <Button asChild variant="outline" className="w-full rounded-xl mt-2">
              <Link href="/login">Back to sign in</Link>
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
          <Loader2 className="w-10 h-10 text-blue-600 animate-spin" aria-hidden />
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  )
}
