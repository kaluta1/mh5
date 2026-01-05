'use client'

import { Heart } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

interface LoadingSpinnerProps {
  message?: string
  fullScreen?: boolean
}

export function LoadingSpinner({ message, fullScreen = false }: LoadingSpinnerProps) {
  const { t } = useLanguage()

  const content = (
    <div className="flex flex-col items-center justify-center space-y-6">
      {/* Animated Logo */}
      <div className="relative w-20 h-20">
        {/* Outer rotating circle */}
        <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-myhigh5-primary border-r-myhigh5-primary animate-spin"></div>
        
        {/* Middle rotating circle (slower) */}
        <div className="absolute inset-2 rounded-full border-4 border-transparent border-b-myhigh5-primary animate-spin" style={{ animationDirection: 'reverse', animationDuration: '3s' }}></div>
        
        {/* Center logo */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-12 h-12 bg-myhigh5-primary rounded-full flex items-center justify-center shadow-lg">
            <Heart className="w-6 h-6 text-white" />
          </div>
        </div>
      </div>

      {/* Loading text */}
      <div className="text-center">
        <p className="text-lg font-semibold text-gray-900 dark:text-white">
          {message || t('common.loading')}
        </p>
        <div className="flex items-center justify-center space-x-1 mt-2">
          <div className="w-2 h-2 bg-myhigh5-primary rounded-full animate-bounce" style={{ animationDelay: '0s' }}></div>
          <div className="w-2 h-2 bg-myhigh5-primary rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
          <div className="w-2 h-2 bg-myhigh5-primary rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
        </div>
      </div>
    </div>
  )

  if (fullScreen) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 flex items-center justify-center">
        {content}
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center py-12">
      {content}
    </div>
  )
}
