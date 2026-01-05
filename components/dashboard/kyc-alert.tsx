'use client'

import { AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { useRouter } from 'next/navigation'

interface KYCAlertProps {
  showButton?: boolean
}

export function KYCAlert({ showButton = true }: KYCAlertProps) {
  const { t } = useLanguage()
  const router = useRouter()

  return (
    <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-6">
      <div className="flex items-start gap-4">
        <AlertCircle className="w-6 h-6 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-1" />
        <div className="flex-1">
          <h2 className="text-lg font-semibold text-yellow-900 dark:text-yellow-100 mb-2">
            {t('kyc.verification_required')}
          </h2>
          <p className="text-yellow-800 dark:text-yellow-200 mb-4">
            {t('kyc.verification_required_description')}
          </p>
          {showButton && (
            <Button
              onClick={() => router.push('/dashboard/kyc')}
              className="bg-yellow-600 hover:bg-yellow-700 text-white"
            >
              {t('kyc.start_verification')}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
