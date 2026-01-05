'use client'

import { CheckCircle, AlertCircle } from 'lucide-react'

interface ToastNotificationProps {
  type: 'success' | 'error'
  message: string
}

export function ToastNotification({ type, message }: ToastNotificationProps) {
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-6 py-4 rounded-2xl shadow-2xl backdrop-blur-md transition-all duration-300 animate-in slide-in-from-bottom-5 ${
        type === 'success'
          ? 'bg-green-500/95 dark:bg-green-600/95 border border-green-400/50 dark:border-green-500/50'
          : 'bg-red-500/95 dark:bg-red-600/95 border border-red-400/50 dark:border-red-500/50'
      } text-white`}
    >
      {type === 'success' ? (
        <CheckCircle className="w-5 h-5 flex-shrink-0" />
      ) : (
        <AlertCircle className="w-5 h-5 flex-shrink-0" />
      )}
      <p className="font-semibold">{message}</p>
    </div>
  )
}

