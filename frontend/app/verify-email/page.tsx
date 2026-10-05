'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Loader2, CheckCircle, XCircle, MailCheck, Mail } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useLanguage } from '@/contexts/language-context'
import { authService } from '@/lib/api'
import { takeLink } from '@/lib/one-time-link'

/**
 * loading  the credential from the link is being exchanged;
 * success  the address is confirmed;
 * error    the link could not be used (the server gives one answer for every
 *          reason: expired, already used, replaced by a newer link, unknown);
 * old      a link from an email sent before one-time links (never accepted);
 * request  the page was opened without a link: ask for a new one.
 */
type Phase = 'loading' | 'success' | 'error' | 'old' | 'request'

/**
 * Email verification. The one-time credential arrives in the URL fragment
 * (never sent to a server), is removed from the address bar at once and is
 * exchanged over POST. When there is no usable link, a new one can be
 * requested here.
 */
export default function VerifyEmailPage() {
  const { t } = useLanguage()
  const [phase, setPhase] = useState<Phase>('loading')
  const [email, setEmail] = useState('')
  const [resendState, setResendState] = useState<'idle' | 'sending' | 'sent' | 'error' | 'limited'>('idle')
  // The credential works once: never submit it twice (React re-runs effects in development).
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true

    const link = takeLink()
    if (link.kind === 'none') {
      setPhase('request')
      return
    }
    if (link.kind === 'legacy') {
      setPhase('old')
      return
    }
    if (link.kind === 'invalid') {
      setPhase('error')
      return
    }
    ;(async () => {
      try {
        await authService.verifyEmail(link.token)
        setPhase('success')
      } catch {
        setPhase('error')
      }
    })()
  }, [])

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || resendState === 'sending') return
    setResendState('sending')
    try {
      await authService.resendVerification(email.trim())
      setResendState('sent')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setResendState(status === 429 ? 'limited' : 'error')
    }
  }

  const resendForm =
    resendState === 'sent' ? (
      <div className="rounded-xl bg-green-50 dark:bg-green-900/20 p-4 text-sm text-green-800 dark:text-green-200" role="status">
        <MailCheck className="w-5 h-5 inline-block mr-2" aria-hidden />
        {t('auth.verify_email.resend_sent')}
      </div>
    ) : (
      <form onSubmit={handleResend} className="space-y-3 text-left" aria-label={t('auth.verify_email.resend_button')}>
        <label htmlFor="resend-email" className="block text-sm font-medium text-gray-700 dark:text-gray-200">
          {t('auth.verify_email.resend_label')}
        </label>
        <Input
          id="resend-email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t('auth.verify_email.resend_placeholder')}
          className="h-11 rounded-xl"
        />
        {(resendState === 'error' || resendState === 'limited') && (
          <p className="text-sm text-red-600" role="alert">
            {t(resendState === 'limited' ? 'auth.verify_email.resend_rate_limited' : 'auth.verify_email.resend_failed')}
          </p>
        )}
        <Button type="submit" className="w-full rounded-xl" disabled={resendState === 'sending'}>
          {resendState === 'sending' ? t('auth.verify_email.resend_sending') : t('auth.verify_email.resend_button')}
        </Button>
      </form>
    )

  const backToSignIn = (
    <Button asChild variant="outline" className="w-full rounded-xl mt-2">
      <Link href="/login">{t('auth.verify_email.back_to_sign_in')}</Link>
    </Button>
  )

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 shadow-sm text-center space-y-4">
        {phase === 'loading' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto text-blue-600 animate-spin" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{t('auth.verify_email.verifying_title')}</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">{t('auth.verify_email.verifying_message')}</p>
          </>
        )}
        {phase === 'success' && (
          <>
            <CheckCircle className="w-12 h-12 mx-auto text-green-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{t('auth.verify_email.success_title')}</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">{t('auth.verify_email.success_message')}</p>
            <Button asChild className="w-full rounded-xl mt-2">
              <Link href="/login">{t('auth.verify_email.continue_to_sign_in')}</Link>
            </Button>
          </>
        )}
        {(phase === 'error' || phase === 'old') && (
          <>
            <XCircle className="w-12 h-12 mx-auto text-red-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{t('auth.verify_email.error_title')}</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t(phase === 'old' ? 'auth.verify_email.error_old_link' : 'auth.verify_email.error_invalid_link')}
            </p>
            {resendForm}
            {backToSignIn}
          </>
        )}
        {phase === 'request' && (
          <>
            <Mail className="w-12 h-12 mx-auto text-blue-600" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{t('auth.verify_email.request_title')}</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">{t('auth.verify_email.request_message')}</p>
            {resendForm}
            {backToSignIn}
          </>
        )}
      </div>
    </div>
  )
}
