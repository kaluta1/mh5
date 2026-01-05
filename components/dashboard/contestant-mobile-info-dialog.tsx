'use client'

import { useLanguage } from '@/contexts/language-context'

interface ContestantMobileInfoDialogProps {
  isOpen: boolean
  onClose: () => void
  contestTitle?: string
  totalParticipants?: number
  candidateTitle?: string
  registrationDate?: string
  isQualified?: boolean
}

export function ContestantMobileInfoDialog({
  isOpen,
  onClose,
  contestTitle,
  totalParticipants,
  candidateTitle,
  registrationDate,
  isQualified
}: ContestantMobileInfoDialogProps) {
  const { t } = useLanguage()

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-xl p-5 w-full max-w-sm border border-gray-200 dark:border-gray-700 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-4">
          {/* Contest Info */}
          <div className="bg-gradient-to-r from-myhigh5-primary/10 to-myhigh5-primary-dark/10 rounded-lg p-3 border border-myhigh5-primary/20">
            <h3 className="text-xs font-bold text-myhigh5-primary uppercase mb-2 tracking-wide">
              {t('contestant_detail.contest_info')}
            </h3>
            <div className="space-y-2">
              {contestTitle && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                    {t('contestant_detail.title')}
                  </p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {contestTitle}
                  </p>
                </div>
              )}
              {totalParticipants && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                    {t('contestant_detail.participants')}
                  </p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {totalParticipants}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Candidate Info */}
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-gray-700 dark:to-gray-800 rounded-lg p-3 border border-blue-200 dark:border-gray-600">
            <h3 className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase mb-2 tracking-wide">
              {t('contestant_detail.candidate_info')}
            </h3>
            <div className="space-y-2">
              {candidateTitle && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                    {t('contestant_detail.title')}
                  </p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {candidateTitle}
                  </p>
                </div>
              )}
              {registrationDate && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                    {t('contestant_detail.registered_on')}
                  </p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {new Date(registrationDate).toLocaleDateString('fr-FR')}
                  </p>
                </div>
              )}
              {isQualified !== undefined && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                    {t('contestant_detail.status')}
                  </p>
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-semibold ${
                      isQualified
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                        : 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400'
                    }`}>
                      {isQualified ? '✓' : '⏳'} {isQualified ? t('contestant_detail.qualified') : t('contestant_detail.pending')}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

