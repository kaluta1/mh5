'use client'

import { useState, useEffect, ReactNode } from 'react'
import { HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useLanguage } from '@/contexts/language-context'

interface StickyPageHeaderProps {
  title: string
  subtitle?: string
  onInfoClick: () => void
  infoTooltip?: string
  className?: string
  children?: ReactNode
}

export function StickyPageHeader({
  title,
  subtitle,
  onInfoClick,
  infoTooltip,
  className = '',
  children
}: StickyPageHeaderProps) {
  const { t } = useLanguage()
  const [isScrolled, setIsScrolled] = useState(false)
  const [scrollY, setScrollY] = useState(0)

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY
      setScrollY(currentScrollY)
      setIsScrolled(currentScrollY > 100) // Déclencher l'animation après 100px de scroll
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <div 
      className={`transition-all duration-300 ease-in-out ${isScrolled ? 'sticky top-16 z-40' : ''} ${className}`}
    >
      <div className={`${isScrolled ? 'bg-white/95 dark:bg-gray-900/95 backdrop-blur-md border-b border-gray-200/50 dark:border-gray-800/50 shadow-lg' : ''} ${isScrolled ? 'px-4 sm:px-6 lg:px-8 py-4' : 'mb-6'}`}>
        <div className={`flex items-center justify-between gap-3 sm:gap-4 ${isScrolled ? 'max-w-7xl mx-auto' : ''}`}>
          <div className="flex-1 min-w-0">
            <h1 className={`font-bold text-gray-900 dark:text-white ${isScrolled ? 'text-xl sm:text-2xl truncate' : 'text-2xl sm:text-3xl lg:text-4xl'}`}>
              {title}
            </h1>
            {subtitle && (
              <p className={`text-gray-600 dark:text-gray-400 mt-1 ${isScrolled ? 'text-xs sm:text-sm truncate' : 'text-sm'}`}>
                {subtitle}
              </p>
            )}
          </div>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  onClick={onInfoClick}
                  variant="outline"
                  size="icon"
                  className={`rounded-full border-myhigh5-primary text-myhigh5-primary hover:bg-myhigh5-blue-50 dark:hover:bg-myhigh5-blue-900/20 flex-shrink-0 ${isScrolled ? 'h-9 w-9' : ''}`}
                >
                  <HelpCircle className={isScrolled ? 'w-4 h-4' : 'w-5 h-5'} />
                </Button>
              </TooltipTrigger>
              <TooltipContent className="bg-white text-gray-900 border-gray-200 shadow-lg dark:bg-gray-800 dark:text-white dark:border-gray-700">
                <p className="text-xs">{infoTooltip || t('dashboard.contests.tooltip_info') || 'Voir les détails'}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        {children && !isScrolled && (
          <div className="mt-4">
            {children}
          </div>
        )}
      </div>
    </div>
  )
}

