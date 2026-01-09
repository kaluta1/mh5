'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Mail, Loader2, CheckCircle, ArrowLeft } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { authService } from '@/lib/api'

export default function ForgotPasswordPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const { addToast } = useToast()
  
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!email.trim()) {
      addToast(t('auth.forgot_password.email_required') || 'L\'email est requis', 'error')
      return
    }

    setIsLoading(true)
    
    try {
      await authService.requestPasswordReset(email)
      setIsSuccess(true)
      addToast(
        t('auth.forgot_password.success') || 'Un email de réinitialisation a été envoyé',
        'success'
      )
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || t('auth.forgot_password.error') || 'Erreur lors de l\'envoi de l\'email'
      addToast(errorMessage, 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        <div className="bg-white/80 dark:bg-gray-800/90 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/20 dark:border-gray-700/50 p-8">
          {isSuccess ? (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="mb-6 animate-bounce">
                <CheckCircle className="w-16 h-16 text-green-500" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                {t('auth.forgot_password.success_title') || 'Email envoyé !'}
              </h2>
              <p className="text-center text-gray-700 dark:text-gray-200 mb-6">
                {t('auth.forgot_password.success_message') || 'Si cet email existe dans notre système, vous recevrez un lien de réinitialisation de mot de passe.'}
              </p>
              <p className="text-center text-sm text-gray-600 dark:text-gray-400 mb-6">
                {t('auth.forgot_password.check_spam') || 'Vérifiez votre dossier spam si vous ne recevez pas l\'email.'}
              </p>
              <Link href="/login">
                <Button className="bg-blue-500 hover:bg-blue-600 text-white">
                  {t('auth.login.title') || 'Retour à la connexion'}
                </Button>
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <Link href="/login" className="inline-flex items-center text-sm text-gray-600 dark:text-gray-400 hover:text-blue-500 mb-4">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  {t('common.back') || 'Retour'}
                </Link>
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                  {t('auth.forgot_password.title') || 'Mot de passe oublié ?'}
                </h1>
                <p className="text-gray-600 dark:text-gray-400">
                  {t('auth.forgot_password.description') || 'Entrez votre adresse email et nous vous enverrons un lien pour réinitialiser votre mot de passe.'}
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    {t('auth.email')} *
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <Input
                      type="email"
                      placeholder={t('auth.register.email_placeholder') || 'votre@email.com'}
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-blue-500 focus:ring-blue-500"
                      required
                      disabled={isLoading}
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={isLoading}
                  className="w-full h-12 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-xl"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                      {t('common.submitting') || 'Envoi en cours...'}
                    </>
                  ) : (
                    t('auth.forgot_password.send_reset_link') || 'Envoyer le lien de réinitialisation'
                  )}
                </Button>
              </form>

              <div className="mt-6 text-center">
                <Link href="/login" className="text-sm text-blue-500 hover:text-blue-600">
                  {t('auth.forgot_password.remember_password') || 'Vous vous souvenez de votre mot de passe ?'}
                </Link>
              </div>
            </>
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

