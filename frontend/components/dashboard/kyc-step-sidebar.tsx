'use client'

import { useLanguage } from '@/contexts/language-context'
import { Shield } from 'lucide-react'

interface Step {
  number: number
  title: string
  description: string
}

interface KYCStepSidebarProps {
  steps: Step[]
  currentStep: number
  onStepClick: (step: number) => void
}

export function KYCStepSidebar({ steps, currentStep, onStepClick }: KYCStepSidebarProps) {
  const { t } = useLanguage()

  return (
    <>
      {/* Mobile View - Icons */}
      <div className="lg:hidden mb-6">
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex justify-between items-center gap-2">
            {steps.map((step) => (
              <div
                key={step.number}
                onClick={() => onStepClick(step.number)}
                className="flex flex-col items-center gap-2 flex-1"
              >
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm cursor-pointer transition-all ${
                    currentStep >= step.number
                      ? 'bg-myfav-primary text-white'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                  } ${
                    currentStep === step.number
                      ? 'ring-2 ring-myfav-primary ring-offset-2 dark:ring-offset-gray-900'
                      : ''
                  }`}
                >
                  {step.number}
                </div>
                <p className="text-xs text-center text-gray-600 dark:text-gray-400 line-clamp-2">
                  {step.title}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Desktop View - Sidebar */}
      <div className="hidden lg:block">
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 sticky top-20">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-6">
            {t('kyc.steps')}
          </h3>

          <div className="space-y-4">
            {steps.map((step) => (
              <div
                key={step.number}
                onClick={() => onStepClick(step.number)}
                className={`flex items-start gap-3 p-4 rounded-lg cursor-pointer transition-all ${
                  currentStep === step.number
                    ? 'bg-myfav-primary/10 border border-myfav-primary'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <div
                  className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${
                    currentStep >= step.number
                      ? 'bg-myfav-primary text-white'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                  }`}
                >
                  {step.number}
                </div>
                <div className="flex-1">
                  <p className="font-semibold text-gray-900 dark:text-white">
                    {step.title}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {step.description}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Info Box */}
          <div className="mt-8 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="flex gap-3">
              <Shield className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-blue-900 dark:text-blue-100 text-sm">
                  {t('kyc.secure')}
                </p>
                <p className="text-xs text-blue-800 dark:text-blue-200 mt-1">
                  {t('kyc.secure_desc')}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
