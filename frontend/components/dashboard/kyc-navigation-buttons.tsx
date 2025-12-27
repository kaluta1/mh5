'use client'

import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { ChevronRight } from 'lucide-react'

interface KYCNavigationButtonsProps {
  currentStep: number
  totalSteps: number
  isSubmitting: boolean
  onPrevious: () => void
  onNext: () => void
  onSubmit: (e: React.FormEvent) => void
}

export function KYCNavigationButtons({
  currentStep,
  totalSteps,
  isSubmitting,
  onPrevious,
  onNext,
  onSubmit
}: KYCNavigationButtonsProps) {
  const { t } = useLanguage()

  return (
    <div className="mt-8 flex gap-3 pt-6 border-t border-gray-200 dark:border-gray-700">
      <Button
        type="button"
        onClick={onPrevious}
        disabled={currentStep === 1 || isSubmitting}
        variant="outline"
        className="flex-1"
      >
        {t('common.previous')}
      </Button>

      {currentStep < totalSteps ? (
        <Button
          type="button"
          onClick={onNext}
          disabled={isSubmitting}
          className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white flex items-center justify-center gap-2"
        >
          {t('common.next')}
          <ChevronRight className="w-4 h-4" />
        </Button>
      ) : (
        <Button
          type="submit"
          onClick={onSubmit}
          disabled={isSubmitting}
          className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white"
        >
          {isSubmitting ? t('common.submitting') : t('kyc.submit_verification')}
        </Button>
      )}
    </div>
  )
}
