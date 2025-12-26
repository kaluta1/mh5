'use client'

import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface FloatingActionButtonProps {
  onClick: () => void
  icon?: React.ReactNode
  label?: string
  className?: string
  variant?: 'default' | 'primary' | 'secondary'
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left'
}

export function FloatingActionButton({
  onClick,
  icon,
  label,
  className,
  variant = 'primary',
  position = 'bottom-right'
}: FloatingActionButtonProps) {
  const positionClasses = {
    'bottom-right': 'bottom-6 right-6',
    'bottom-left': 'bottom-6 left-6',
    'top-right': 'top-6 right-6',
    'top-left': 'top-6 left-6'
  }

  const variantClasses = {
    default: 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-lg hover:shadow-xl border border-gray-200 dark:border-gray-700',
    primary: 'bg-myfav-primary hover:bg-myfav-primary/90 text-white shadow-lg hover:shadow-xl',
    secondary: 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white shadow-lg hover:shadow-xl'
  }

  return (
    <div className={cn('fixed z-50', positionClasses[position])}>
      <Button
        onClick={onClick}
        size="lg"
        className={cn(
          'rounded-full h-14 w-14 md:h-16 md:w-16 flex items-center justify-center transition-all duration-300 hover:scale-110 shadow-2xl',
          variantClasses[variant],
          className
        )}
        aria-label={label || 'Action'}
      >
        {icon || <Plus className="h-6 w-6 md:h-7 md:w-7" />}
      </Button>
    </div>
  )
}

