'use client'

import * as React from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface ContestantDescriptionProps {
  description: string
  maxLength?: number
}

export function ContestantDescription({ description, maxLength = 200 }: ContestantDescriptionProps) {
  const [isOpen, setIsOpen] = React.useState(false)
  const { t, language } = useLanguage()

  if (!description || description.trim() === '') {
    return (
      <p className="text-sm text-gray-400 dark:text-gray-500 italic">
        {language === 'fr'
          ? 'Aucune description disponible'
          : language === 'es'
            ? 'No hay descripción disponible'
            : language === 'de'
              ? 'Keine Beschreibung verfügbar'
              : 'No description available'}
      </p>
    )
  }

  const shouldTruncate = description.length > maxLength
  const truncatedDescription = shouldTruncate ? description.substring(0, maxLength) + '...' : description

  const dialogTitle =
    language === 'fr'
      ? 'Description'
      : language === 'es'
        ? 'Descripción'
        : language === 'de'
          ? 'Beschreibung'
          : 'Description'

  return (
    <>
      <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
        {truncatedDescription}
        {shouldTruncate && (
          <Button
            variant="link"
            className="ml-1 p-0 h-auto text-myfav-primary dark:text-myfav-secondary underline"
            onClick={() => setIsOpen(true)}
          >
            {t('common.view_more') || (language === 'fr' ? 'Voir plus' : language === 'es' ? 'Ver más' : language === 'de' ? 'Mehr anzeigen' : 'View more')}
          </Button>
        )}
      </p>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{dialogTitle}</DialogTitle>
          </DialogHeader>
          <div className="mt-3">
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
              {description}
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

