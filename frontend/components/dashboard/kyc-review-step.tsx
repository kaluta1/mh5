'use client'

import { useLanguage } from '@/contexts/language-context'
import { FileCheck, Clock } from 'lucide-react'

interface ReviewData {
  firstName: string
  lastName: string
  dateOfBirth: string
  nationality: string
  address: string
  documentType: string
  documentNumber: string
  issuingCountry: string
  documentFront: string
  documentBack: string
  selfie: string
}

interface KYCReviewStepProps {
  data: ReviewData
}

export function KYCReviewStep({ data }: KYCReviewStepProps) {
  const { t } = useLanguage()

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <FileCheck className="w-6 h-6 text-myfav-primary" />
          {t('kyc.review_submit')}
        </h2>
      </div>

      <div className="space-y-3">
        {/* Personal Info Summary */}
        <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
            {t('kyc.personal_info')}
          </h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-gray-600 dark:text-gray-400">{t('kyc.first_name')}</p>
              <p className="font-medium text-gray-900 dark:text-white">{data.firstName}</p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">{t('kyc.last_name')}</p>
              <p className="font-medium text-gray-900 dark:text-white">{data.lastName}</p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">{t('kyc.date_of_birth')}</p>
              <p className="font-medium text-gray-900 dark:text-white">{data.dateOfBirth}</p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">{t('kyc.nationality')}</p>
              <p className="font-medium text-gray-900 dark:text-white">{data.nationality}</p>
            </div>
            <div className="col-span-2">
              <p className="text-gray-600 dark:text-gray-400">{t('kyc.address')}</p>
              <p className="font-medium text-gray-900 dark:text-white">{data.address}</p>
            </div>
          </div>
        </div>

        {/* Document Info Summary */}
        <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
            {t('kyc.document_info')}
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-gray-600 dark:text-gray-400">{t('kyc.document_type')}</p>
              <p className="font-medium text-gray-900 dark:text-white capitalize">{data.documentType}</p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">{t('kyc.document_number')}</p>
              <p className="font-medium text-gray-900 dark:text-white">{data.documentNumber}</p>
            </div>
            <div className="col-span-2">
              <p className="text-gray-600 dark:text-gray-400">{t('kyc.issuing_country')}</p>
              <p className="font-medium text-gray-900 dark:text-white">{data.issuingCountry}</p>
            </div>
          </div>
        </div>

        {/* Document Upload Summary */}
        <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
            Uploaded Documents
          </h3>
          <div className="space-y-3 text-sm">
            <div>
              <p className="text-gray-600 dark:text-gray-400">Document Front</p>
              <p className="font-medium text-gray-900 dark:text-white break-all">
                {data.documentFront || 'Not uploaded'}
              </p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">Document Back</p>
              <p className="font-medium text-gray-900 dark:text-white break-all">
                {data.documentBack || 'Not uploaded'}
              </p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">Selfie</p>
              <p className="font-medium text-gray-900 dark:text-white break-all">
                {data.selfie || 'Not uploaded'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Timeline Info */}
      <div className="p-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
        <div className="flex gap-3">
          <Clock className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-amber-900 dark:text-amber-100 text-sm">
              {t('kyc.processing_time')}
            </p>
            <p className="text-xs text-amber-800 dark:text-amber-200 mt-1">
              {t('kyc.processing_time_desc')}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
