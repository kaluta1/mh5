'use client'

import { CheckCircle, AlertCircle } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

export interface ContestantInfoCardProps {
  contest_title?: string
  total_participants?: number
  is_qualified?: boolean
  registration_date?: string
}

export function ContestantInfoCard({
  contest_title,
  total_participants,
  is_qualified,
  registration_date
}: ContestantInfoCardProps) {
  const { t } = useLanguage()

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-200 dark:border-gray-700 sticky top-6 space-y-6">
      {/* Contest Info */}
      <div>
        <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
          {t('contestant_detail.contest_info')}
        </h2>
        <div className="space-y-3">
          {contest_title && (
            <div>
              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">
                {t('contestant_detail.title')}
              </p>
              <p className="text-sm text-gray-900 dark:text-white mt-1">{contest_title}</p>
            </div>
          )}

          {total_participants && (
            <div>
              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">
                {t('contestant_detail.participants')}
              </p>
              <p className="text-sm text-gray-900 dark:text-white mt-1">{total_participants}</p>
            </div>
          )}

          {registration_date && (
            <div>
              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">
                {t('contestant_detail.registered_on')}
              </p>
              <p className="text-sm text-gray-900 dark:text-white mt-1">
                {new Date(registration_date).toLocaleDateString('fr-FR')}
              </p>
            </div>
          )}

          {is_qualified !== undefined && (
            <div>
              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">
                {t('contestant_detail.status')}
              </p>
              <div className="flex items-center gap-2 mt-1">
                {is_qualified ? (
                  <>
                    <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                    <p className="text-sm font-semibold text-green-600 dark:text-green-400">
                      {t('contestant_detail.qualified')}
                    </p>
                  </>
                ) : (
                  <>
                    <AlertCircle className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                    <p className="text-sm font-semibold text-orange-600 dark:text-orange-400">
                      {t('contestant_detail.pending')}
                    </p>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
