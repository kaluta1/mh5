'use client'

import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { 
  Mail, 
  Send, 
  Copy, 
  CheckCircle, 
  Loader2,
  Link as LinkIcon,
  X
} from 'lucide-react'

interface InviteDialogProps {
  isOpen: boolean
  onClose: () => void
  referralCode: string
  referralLink: string
}

export function InviteDialog({ 
  isOpen, 
  onClose, 
  referralCode, 
  referralLink 
}: InviteDialogProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [copiedLink, setCopiedLink] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!email.trim()) {
      addToast(t('dashboard.affiliates.invite_email_required') || 'Veuillez entrer un email', 'error')
      return
    }

    setIsLoading(true)
    
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/invitations`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            email: email.trim(),
            message: message.trim() || null
          })
        }
      )

      const data = await response.json()
      
      if (response.ok && data.success) {
        addToast(t('dashboard.affiliates.invite_sent_success') || 'Invitation envoyée avec succès !', 'success')
        setEmail('')
        setMessage('')
        onClose()
      } else {
        addToast(data.detail || data.message || 'Erreur lors de l\'envoi', 'error')
      }
    } catch (error) {
      console.error('Error sending invitation:', error)
      addToast(t('dashboard.affiliates.invite_error') || 'Erreur lors de l\'envoi de l\'invitation', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(referralLink)
      setCopiedLink(true)
      addToast(t('dashboard.affiliates.link_copied') || 'Lien copié !', 'success')
      setTimeout(() => setCopiedLink(false), 2000)
    } catch (error) {
      addToast(t('dashboard.affiliates.copy_error') || 'Erreur lors de la copie', 'error')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-[95vw] sm:max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base sm:text-lg">
            <Mail className="w-5 h-5 text-myhigh5-primary" />
            {t('dashboard.affiliates.invite_friend') || 'Inviter un ami'}
          </DialogTitle>
          <DialogDescription className="text-xs sm:text-sm">
            {t('dashboard.affiliates.invite_description') || 'Envoyez une invitation par email pour parrainer vos amis'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-4">
          {/* Email input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              {t('dashboard.affiliates.email_address') || 'Adresse email'}
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ami@exemple.com"
              className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-myhigh5-primary focus:border-transparent transition-all"
              disabled={isLoading}
            />
          </div>

          {/* Message optionnel */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              {t('dashboard.affiliates.personal_message') || 'Message personnalisé'} 
              <span className="text-gray-400 font-normal ml-1">({t('common.optional') || 'optionnel'})</span>
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={t('dashboard.affiliates.message_placeholder') || 'Salut ! Rejoins-moi sur MyHigh5...'}
              rows={3}
              maxLength={500}
              className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-myhigh5-primary focus:border-transparent transition-all resize-none"
              disabled={isLoading}
            />
            <p className="text-xs text-gray-400 mt-1 text-right">{message.length}/500</p>
          </div>

          {/* Bouton envoyer */}
          <Button
            type="submit"
            disabled={isLoading || !email.trim()}
            className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white rounded-xl py-3 font-medium disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                {t('dashboard.affiliates.sending') || 'Envoi en cours...'}
              </>
            ) : (
              <>
                <Send className="w-4 h-4 mr-2" />
                {t('dashboard.affiliates.send_invitation') || 'Envoyer l\'invitation'}
              </>
            )}
          </Button>
        </form>

        {/* Séparateur */}
        <div className="relative my-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-200 dark:border-gray-700"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-white dark:bg-gray-900 text-gray-500">
              {t('common.or') || 'ou'}
            </span>
          </div>
        </div>

        {/* Copier le lien */}
        <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            <LinkIcon className="w-4 h-4 text-myhigh5-primary" />
            <span className="text-sm font-medium text-gray-900 dark:text-white">
              {t('dashboard.affiliates.share_link') || 'Partager votre lien'}
            </span>
          </div>
          <div className="flex gap-2">
            <div className="flex-1 bg-white dark:bg-gray-900 rounded-lg p-2.5 font-mono text-xs text-gray-600 dark:text-gray-400 truncate border border-gray-200 dark:border-gray-700">
              {referralLink}
            </div>
            <Button
              type="button"
              onClick={copyToClipboard}
              variant="outline"
              size="sm"
              className={`rounded-lg flex-shrink-0 px-3 ${copiedLink ? 'bg-green-100 border-green-500 text-green-700' : ''}`}
            >
              {copiedLink ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </Button>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            {t('dashboard.affiliates.code_label') || 'Code'}: <span className="font-mono font-bold text-myhigh5-primary">{referralCode}</span>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
