'use client'

import Link from 'next/link'
import { Archive } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

type HistoryLink = { href: string; labelKey: string }

/**
 * Shown where the retired business model (10-level affiliate program and the
 * Founding Members program) used to be advertised. Historical records stay
 * available through the linked pages.
 */
export function RetiredProgramNotice({
  titleKey,
  bodyKey,
  links = [],
  compact = false,
}: {
  titleKey: string
  bodyKey: string
  links?: HistoryLink[]
  compact?: boolean
}) {
  const { t } = useLanguage()

  return (
    <div
      role="status"
      className={`rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-100 ${
        compact ? 'px-4 py-3' : 'px-6 py-5'
      }`}
    >
      <div className="flex items-start gap-3">
        <Archive className="w-5 h-5 mt-0.5 shrink-0" aria-hidden="true" />
        <div className="space-y-2">
          <p className="font-semibold">{t(titleKey)}</p>
          <p className="text-sm">{t(bodyKey)}</p>
          {links.length > 0 && (
            <div className="flex flex-wrap gap-3 pt-1">
              {links.map((link) => (
                <Link key={link.href} href={link.href} className="text-sm font-medium underline underline-offset-4">
                  {t(link.labelKey)}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
