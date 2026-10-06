'use client'

import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import type { ListViewState } from '@/lib/participants-state'

/**
 * What the contest list shows when it has no cards. A request that FAILED is
 * an error with a retry action; "no contests" is said only when a request
 * succeeded and returned none.
 */
export function ContestListFeedback({
  state,
  emptyMessage,
  onRetry,
}: {
  state: ListViewState
  emptyMessage: string
  onRetry: () => void
}) {
  const { t } = useLanguage()
  if (state === 'ERROR') {
    return (
      <div className="text-center py-20 space-y-4" role="alert">
        <p className="text-gray-600 dark:text-gray-300">
          {t('dashboard.contests.list_load_failed') || 'Could not load contests. Please try again.'}
        </p>
        <Button type="button" variant="default" onClick={onRetry}>
          {t('common.try_again') || 'Try again'}
        </Button>
      </div>
    )
  }
  if (state !== 'EMPTY') return null
  return (
    <div className="text-center py-20">
      <p className="text-gray-500 dark:text-gray-400">{emptyMessage}</p>
    </div>
  )
}
