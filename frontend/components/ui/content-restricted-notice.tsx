'use client'

import { ShieldAlert } from 'lucide-react'
import type { ContentRestriction } from '@/lib/content-restriction'

/** Shown instead of an entry the backend refused for this viewer (no content is available client-side). */
export function ContentRestrictedNotice({ restriction }: { restriction: ContentRestriction }) {
  return (
    <div className="min-h-[50vh] flex items-center justify-center p-6">
      <div
        role="status"
        data-testid="content-restricted"
        className="max-w-md w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 text-center"
      >
        <ShieldAlert className="mx-auto mb-3 h-8 w-8 text-gray-500" aria-hidden="true" />
        <p className="text-gray-800 dark:text-gray-100">{restriction.message}</p>
      </div>
    </div>
  )
}
