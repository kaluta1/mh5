'use client'

import { CheckCircle, Loader2 } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

interface SuccessPageProps {
  title?: string
  message?: string
  isRedirecting?: boolean
}

export function SuccessPage({ 
  title, 
  message,
  isRedirecting = true 
}: SuccessPageProps) {
  const { t } = useLanguage()

  return (
    <div className="flex flex-col items-center justify-center py-12">
      <div className="mb-6 animate-bounce">
        <CheckCircle className="w-16 h-16 text-green-500" />
      </div>
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
        {title || t('common.success')}
      </h2>
      <p className="text-center text-gray-700 dark:text-gray-200 mb-6">
        {message || t('common.redirecting')}
      </p>
      {isRedirecting && (
        <div className="flex items-center space-x-2">
          <Loader2 className="w-5 h-5 animate-spin text-myfav-primary" />
          <span className="text-sm text-gray-600 dark:text-gray-400">
            {t('common.please_wait')}
          </span>
        </div>
      )}
    </div>
  )
}
