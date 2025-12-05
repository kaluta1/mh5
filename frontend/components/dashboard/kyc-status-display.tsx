'use client'

import { useLanguage } from '@/contexts/language-context'
import { CheckCircle, Clock, AlertCircle, XCircle } from 'lucide-react'

type KYCStatus = 'pending' | 'approved' | 'rejected' | 'under_review'

interface KYCStatusDisplayProps {
  status: KYCStatus
  submittedAt?: string
  reviewedAt?: string
  rejectionReason?: string
}

export function KYCStatusDisplay({
  status,
  submittedAt,
  reviewedAt,
  rejectionReason
}: KYCStatusDisplayProps) {
  const { t } = useLanguage()

  const statusConfig = {
    pending: {
      icon: Clock,
      bgColor: 'bg-yellow-50 dark:bg-yellow-900/20',
      borderColor: 'border-yellow-200 dark:border-yellow-800',
      textColor: 'text-yellow-900 dark:text-yellow-100',
      iconColor: 'text-yellow-600 dark:text-yellow-400',
      title: 'Pending Verification',
      description: 'Your KYC submission is being processed. This usually takes 24-48 hours.'
    },
    under_review: {
      icon: Clock,
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
      borderColor: 'border-blue-200 dark:border-blue-800',
      textColor: 'text-blue-900 dark:text-blue-100',
      iconColor: 'text-blue-600 dark:text-blue-400',
      title: 'Under Review',
      description: 'Your documents are being reviewed by our team.'
    },
    approved: {
      icon: CheckCircle,
      bgColor: 'bg-green-50 dark:bg-green-900/20',
      borderColor: 'border-green-200 dark:border-green-800',
      textColor: 'text-green-900 dark:text-green-100',
      iconColor: 'text-green-600 dark:text-green-400',
      title: 'Verified',
      description: 'Your identity has been verified successfully. You can now participate in contests.'
    },
    rejected: {
      icon: XCircle,
      bgColor: 'bg-red-50 dark:bg-red-900/20',
      borderColor: 'border-red-200 dark:border-red-800',
      textColor: 'text-red-900 dark:text-red-100',
      iconColor: 'text-red-600 dark:text-red-400',
      title: 'Verification Failed',
      description: rejectionReason || 'Your KYC verification was rejected. Please try again with valid documents.'
    }
  }

  const config = statusConfig[status]
  const Icon = config.icon

  const formatDate = (dateString?: string) => {
    if (!dateString) return ''
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <div className={`${config.bgColor} border ${config.borderColor} rounded-lg p-6`}>
      <div className="flex gap-4">
        <Icon className={`w-8 h-8 ${config.iconColor} flex-shrink-0 mt-1`} />
        <div className="flex-1">
          <h3 className={`font-semibold text-lg ${config.textColor} mb-1`}>
            {config.title}
          </h3>
          <p className={`text-sm ${config.textColor} opacity-90 mb-4`}>
            {config.description}
          </p>

          {/* Timeline Info */}
          <div className="space-y-2 text-sm">
            {submittedAt && (
              <div className="flex items-center gap-2">
                <span className={`${config.textColor} opacity-75`}>Submitted:</span>
                <span className={`font-medium ${config.textColor}`}>
                  {formatDate(submittedAt)}
                </span>
              </div>
            )}

            {reviewedAt && (
              <div className="flex items-center gap-2">
                <span className={`${config.textColor} opacity-75`}>Reviewed:</span>
                <span className={`font-medium ${config.textColor}`}>
                  {formatDate(reviewedAt)}
                </span>
              </div>
            )}

            {status === 'pending' || status === 'under_review' ? (
              <div className={`mt-4 p-3 bg-white dark:bg-gray-800 rounded border ${config.borderColor}`}>
                <p className={`text-xs ${config.textColor} opacity-75`}>
                  ⏱️ Typical processing time: 24-48 hours. We'll notify you via email once the review is complete.
                </p>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
