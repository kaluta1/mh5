'use client'

import { useLanguage } from '@/contexts/language-context'
import AdminKYC from '@/components/admin/admin-kyc'

export default function KYCPage() {
  const { t } = useLanguage()
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{t('admin.kyc.title') || 'Manage KYC'}</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">{t('admin.kyc.description') || 'Approve or reject identity verifications'}</p>
      </div>
      <AdminKYC />
    </div>
  )
}
