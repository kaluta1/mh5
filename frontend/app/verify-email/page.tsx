'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { CheckCircle, XCircle, Loader2, Mail } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { authService } from '@/lib/api'

export default function VerifyEmailPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { addToast } = useToast()
  
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')
  const hasVerified = useRef(false)

  useEffect(() => {
    // Empêcher les appels multiples
    if (hasVerified.current) {
      return
    }

    const token = searchParams.get('token')
    
    if (!token) {
      setStatus('error')
      setMessage(t('auth.verify_email.no_token') || 'Token de vérification manquant')
      hasVerified.current = true
      return
    }

    // Marquer comme vérifié pour éviter les appels multiples
    hasVerified.current = true

    const verifyEmail = async () => {
      try {
        const response = await authService.verifyEmail(token)
        setStatus('success')
        setMessage(response.message || t('auth.verify_email.success') || 'Email verified successfully')
        setEmail(response.email)
        
        // Rediriger vers la page de connexion après 3 secondes
        setTimeout(() => {
          router.push('/login')
        }, 3000)
      } catch (error: any) {
        setStatus('error')
        let errorMessage = error.response?.data?.detail || error.message || t('auth.verify_email.error') || 'Erreur lors de la vérification de l\'email'
        
        // Traduire le message d'erreur si c'est un token invalide
        if (errorMessage.includes('Token invalide ou expiré') || errorMessage.includes('Invalid or expired token')) {
          errorMessage = t('auth.verify_email.invalid_token') || 'Token invalide ou expiré'
        }
        
        setMessage(errorMessage)
        addToast(errorMessage, 'error')
      }
    }

    verifyEmail()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Dépendances vides intentionnellement - on veut exécuter une seule fois au montage

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        <div className="bg-white/80 dark:bg-gray-800/90 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/20 dark:border-gray-700/50 p-8">
          {status === 'loading' && (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-16 h-16 text-blue-500 animate-spin mb-6" />
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                {t('auth.verify_email.verifying') || 'Vérification en cours...'}
              </h2>
              <p className="text-center text-gray-700 dark:text-gray-200">
                {t('auth.verify_email.please_wait') || 'Veuillez patienter pendant que nous vérifions votre email.'}
              </p>
            </div>
          )}

          {status === 'success' && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="mb-6 animate-bounce">
                <CheckCircle className="w-16 h-16 text-green-500" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                {t('auth.verify_email.success_title') || 'Email vérifié !'}
              </h2>
              <p className="text-center text-gray-700 dark:text-gray-200 mb-2">
                {message}
              </p>
              {email && (
                <p className="text-center text-sm text-gray-600 dark:text-gray-400 mb-6">
                  {email}
                </p>
              )}
              <p className="text-center text-sm text-gray-600 dark:text-gray-400 mb-6">
                {t('auth.verify_email.redirecting') || 'Redirection vers la page de connexion...'}
              </p>
              <Link href="/login">
                <Button className="bg-blue-500 hover:bg-blue-600 text-white">
                  {t('auth.login.title') || 'Se connecter'}
                </Button>
              </Link>
            </div>
          )}

          {status === 'error' && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="mb-6">
                <XCircle className="w-16 h-16 text-red-500" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                {t('auth.verify_email.error_title') || 'Erreur de vérification'}
              </h2>
              <p className="text-center text-gray-700 dark:text-gray-200 mb-6">
                {message}
              </p>
              <div className="flex flex-col sm:flex-row gap-4 w-full">
                <Link href="/login" className="flex-1">
                  <Button variant="outline" className="w-full">
                    {t('auth.login.title') || 'Se connecter'}
                  </Button>
                </Link>
                <Link href="/register" className="flex-1">
                  <Button className="w-full bg-blue-500 hover:bg-blue-600 text-white">
                    {t('auth.register.title') || 'S\'inscrire'}
                  </Button>
                </Link>
              </div>
            </div>
          )}
        </div>

        <div className="mt-6 text-center">
          <Link href="/" className="text-sm text-gray-600 dark:text-gray-400 hover:text-blue-500">
            {t('common.back') || 'Retour à l\'accueil'}
          </Link>
        </div>
      </div>
    </div>
  )
}

