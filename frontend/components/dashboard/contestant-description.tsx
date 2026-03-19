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

  // Extraire le texte brut du HTML pour la troncature
  const plainText = description.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
  const shouldTruncate = plainText.length > maxLength

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
      <div className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
        {shouldTruncate ? (
          <>
            <span>{plainText.substring(0, maxLength)}...</span>
            <Button
              variant="link"
              className="ml-1 p-0 h-auto text-myhigh5-primary dark:text-myhigh5-secondary underline"
              onClick={() => setIsOpen(true)}
            >
              {t('common.view_more') || (language === 'fr' ? 'Voir plus' : language === 'es' ? 'Ver más' : language === 'de' ? 'Mehr anzeigen' : 'View more')}
            </Button>
          </>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none [&>*]:m-0 [&>p]:mb-1" dangerouslySetInnerHTML={{ __html: description }} />
        )}
      </div>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{dialogTitle}</DialogTitle>
          </DialogHeader>
          <div className="mt-3">
            <div className="prose prose-sm dark:prose-invert max-w-none text-sm text-gray-700 dark:text-gray-300 leading-relaxed" dangerouslySetInnerHTML={{ __html: description }} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

