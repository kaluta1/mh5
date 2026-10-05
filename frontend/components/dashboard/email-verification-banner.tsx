'use client'

import { useState } from 'react'
import { MailWarning, MailCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { authService } from '@/lib/api'

/**
 * "Verify your email" for a signed-in member whose address is not confirmed.
 *
 * Only accounts that existed before verification became mandatory at sign-in
 * can be here: they keep their access, and this is their way to confirm the
 * address. It renders nothing unless the server says `email_verified: false`
 * (an older API response without the field shows nothing).
 */
export function EmailVerificationBanner() {
  const { t } = useLanguage()
  const { user } = useAuth()
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

  const account = user as ({ email?: string; email_verified?: boolean } | null)
  if (!account || account.email_verified !== false || !account.email) return null

  const resend = async () => {
    if (state === 'sending') return
    setState('sending')
    try {
      await authService.resendVerification(account.email as string)
      setState('sent')
    } catch {
      setState('error')
    }
  }

  return (
    <div
      role="status"
      className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-100"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          {state === 'sent' ? (
            <MailCheck className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden />
          ) : (
            <MailWarning className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden />
          )}
          <div>
            <p className="font-semibold">{t('auth.verify_email.banner_title')}</p>
            <p className="text-sm">
              {state === 'sent'
                ? t('auth.verify_email.banner_sent')
                : state === 'error'
                  ? t('auth.verify_email.banner_failed')
                  : t('auth.verify_email.banner_message')}
            </p>
          </div>
        </div>
        {state !== 'sent' && (
          <Button type="button" variant="outline" onClick={resend} disabled={state === 'sending'} className="flex-shrink-0">
            {state === 'sending' ? t('auth.verify_email.resend_sending') : t('auth.verify_email.banner_button')}
          </Button>
        )}
      </div>
    </div>
  )
}
