'use client'

import { useLanguage } from '@/contexts/language-context'
import { countries } from '@/lib/countries'
import { FileText, Camera } from 'lucide-react'

interface DocumentInfoData {
  documentType: string
  documentNumber: string
  issuingCountry: string
}

interface KYCDocumentInfoStepProps {
  data: DocumentInfoData
  onChange: (field: keyof DocumentInfoData, value: string) => void
}

export function KYCDocumentInfoStep({ data, onChange }: KYCDocumentInfoStepProps) {
  const { t } = useLanguage()

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <FileText className="w-6 h-6 text-myfav-primary" />
          {t('kyc.document_info')}
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Document Type */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {t('kyc.document_type')}
          </label>
          <select
            value={data.documentType}
            onChange={(e) => onChange('documentType', e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
          >
            <option value="passport">{t('kyc.passport')}</option>
            <option value="national_id">{t('kyc.national_id')}</option>
            <option value="drivers_license">{t('kyc.drivers_license')}</option>
          </select>
        </div>

        {/* Document Number */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {t('kyc.document_number')}
          </label>
          <input
            type="text"
            value={data.documentNumber}
            onChange={(e) => onChange('documentNumber', e.target.value)}
            placeholder={t('kyc.document_number_placeholder')}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          />
        </div>

        {/* Issuing Country */}
        <div className="md:col-span-2">
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {t('kyc.issuing_country')}
          </label>
          <select
            value={data.issuingCountry}
            onChange={(e) => onChange('issuingCountry', e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          >
            <option value="">{t('kyc.issuing_country_placeholder')}</option>
            {countries.map((country) => (
              <option key={country.code} value={country.name}>
                {country.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Document Upload Info */}
      <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
        <div className="flex gap-3">
          <Camera className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-blue-900 dark:text-blue-100 text-sm">
              {t('kyc.document_upload_next')}
            </p>
            <p className="text-xs text-blue-800 dark:text-blue-200 mt-1">
              {t('kyc.document_upload_next_desc')}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
