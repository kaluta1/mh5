'use client'

import { X } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useLanguage } from '@/contexts/language-context'

interface AdvertisementProps {
  title?: string
  description?: string
  imageUrl?: string
  ctaText?: string
  onDismiss?: () => void
}

export function Advertisement({ 
  title,
  description,
  imageUrl,
  ctaText,
  onDismiss
}: AdvertisementProps) {
  const { t } = useLanguage()
  const defaultTitle = t('dashboard.feed.ad_title') || 'Discover premium features'
  const defaultDescription = t('dashboard.feed.ad_description') || 'Access exclusive features and boost your visibility'
  const defaultCta = t('dashboard.feed.ad_cta') || 'Learn more'
  
  const adTitle = title || defaultTitle
  const adDescription = description || defaultDescription
  const adCta = ctaText || defaultCta
  const [isVisible, setIsVisible] = useState(true)

  if (!isVisible) return null

  const handleDismiss = () => {
    setIsVisible(false)
    onDismiss?.()
  }

  return (
    <div className="bg-gradient-to-br from-myhigh5-primary/10 to-myhigh5-secondary/10 rounded-2xl p-4 relative overflow-hidden border border-myhigh5-primary/20">
      {onDismiss && (
        <Button
          variant="ghost"
          size="icon"
          onClick={handleDismiss}
          className="absolute top-2 right-2 h-6 w-6 rounded-full hover:bg-white/20"
        >
          <X className="h-4 w-4" />
        </Button>
      )}
      {imageUrl && (
        <div className="w-full h-32 bg-gray-200 dark:bg-gray-700 rounded-lg mb-3" />
      )}
      <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
        {adTitle}
      </h4>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
        {adDescription}
      </p>
      <Button
        className="w-full rounded-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white font-semibold"
        size="sm"
      >
        {adCta}
      </Button>
    </div>
  )
}

