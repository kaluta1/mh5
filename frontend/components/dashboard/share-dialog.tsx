'use client'

import { useState } from 'react'
import { Copy, Check, Share2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

interface ShareDialogProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  shareLink: string
  title?: string
  description?: string
}

export function ShareDialog({ isOpen, onOpenChange, shareLink, title, description }: ShareDialogProps) {
  const { t } = useLanguage()
  const [linkCopied, setLinkCopied] = useState(false)

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(shareLink)
      setLinkCopied(true)
      setTimeout(() => setLinkCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleNativeShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: title || t('dashboard.contests.share') || 'Partager',
          text: description || '',
          url: shareLink
        })
      } catch (err) {
        // User cancelled or error occurred
        console.error('Error sharing:', err)
      }
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700">
        <DialogHeader>
          <DialogTitle className="text-gray-900 dark:text-white">
            {t('dashboard.contests.share_title') || 'Partager ce participant'}
          </DialogTitle>
          <DialogDescription className="text-gray-600 dark:text-gray-400">
            {t('dashboard.contests.share_description') || 'Partagez ce participant avec vos amis et votre réseau'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-4">
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">
              {t('dashboard.contests.share_link_label') || 'Lien de partage'}
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={shareLink}
                readOnly
                className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
              />
              <button
                onClick={copyToClipboard}
                className="px-4 py-2 bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {linkCopied ? (
                  <>
                    <Check className="w-4 h-4" />
                    {t('dashboard.contests.copied') || 'Copié'}
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    {t('dashboard.contests.copy') || 'Copier'}
                  </>
                )}
              </button>
            </div>
          </div>
          {navigator.share && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                onClick={handleNativeShare}
              >
                <Share2 className="w-4 h-4 mr-2" />
                {t('dashboard.contests.share_natively') || 'Partager nativement'}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

