'use client'

import Link from 'next/link'
import { Header } from '@/components/layout/header'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'

type PublicShareShellProps = {
  children: React.ReactNode
  refCode?: string | null
  ctaHref?: string
  ctaLabel?: string
}

export function PublicShareShell({
  children,
  refCode,
  ctaHref,
  ctaLabel,
}: PublicShareShellProps) {
  const { t } = useLanguage()
  const registerHref = refCode ? `/register?ref=${encodeURIComponent(refCode)}` : '/register'
  const actionHref = ctaHref || registerHref
  const actionLabel =
    ctaLabel ||
    t('public_share.join_cta') ||
    'Join MyHigh5 to vote, comment, and earn'

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header />
      <div className="bg-myhigh5-primary/10 border-b border-myhigh5-primary/20">
        <div className="max-w-4xl mx-auto px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-sm text-gray-700 dark:text-gray-200">
            {t('public_share.guest_banner') ||
              'You are viewing shared content. Sign in for the full experience.'}
          </p>
          <div className="flex items-center gap-2 shrink-0">
            <Button asChild variant="outline" size="sm">
              <Link href="/login">{t('auth.login') || 'Sign in'}</Link>
            </Button>
            <Button asChild size="sm">
              <Link href={actionHref}>{actionLabel}</Link>
            </Button>
          </div>
        </div>
      </div>
      <main className="max-w-4xl mx-auto px-4 py-6 md:py-8">{children}</main>
    </div>
  )
}
