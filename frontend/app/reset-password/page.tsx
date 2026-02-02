'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Lock, Eye, EyeOff, Loader2, CheckCircle, XCircle } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { authService } from '@/lib/api'

function ResetPasswordPageContent() {
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { addToast } = useToast()
  
  const [token, setToken] = useState('')
  const [formData, setFormData] = useState({
    new_password: '',
    confirm_password: ''
  })
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [errors, setErrors] = useState<{ new_password?: string; confirm_password?: string }>({})

  useEffect(() => {
    const tokenParam = searchParams.get('token')
    if (!tokenParam) {
      addToast(t('auth.reset_password.no_token') || 'Token de réinitialisation manquant', 'error')
      router.push('/forgot-password')
      return
    }
    setToken(tokenParam)
  }, [searchParams, router, t, addToast])

  const validateForm = () => {
    const newErrors: { new_password?: string; confirm_password?: string } = {}
    
    if (!formData.new_password) {
      newErrors.new_password = t('auth.reset_password.password_required') || 'Le mot de passe est requis'
    } else if (formData.new_password.length < 6) {
      newErrors.new_password = t('auth.reset_password.password_min_length') || 'Le mot de passe doit contenir au moins 6 caractères'
    }
    
    if (!formData.confirm_password) {
      newErrors.confirm_password = t('auth.reset_password.confirm_password_required') || 'La confirmation du mot de passe est requise'
    } else if (formData.new_password !== formData.confirm_password) {
      newErrors.confirm_password = t('auth.reset_password.passwords_not_match') || 'Les mots de passe ne correspondent pas'
    }
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateForm() || !token) {
      return
    }

    setIsLoading(true)
    
    try {
      await authService.confirmPasswordReset({
        token,
        new_password: formData.new_password
      })
      
      setIsSuccess(true)
      addToast(
        t('auth.reset_password.success') || 'Mot de passe réinitialisé avec succès',
        'success'
      )
      
      // Rediriger vers la page de connexion après 3 secondes
      setTimeout(() => {
        router.push('/login')
      }, 3000)
    } catch (error: any) {
      let errorMessage = error.response?.data?.detail || error.message || t('auth.reset_password.error') || 'Erreur lors de la réinitialisation du mot de passe'
      
      // Traduire le message d'erreur si c'est un token invalide
      if (errorMessage.includes('Token invalide ou expiré') || errorMessage.includes('Invalid or expired token')) {
        errorMessage = t('auth.reset_password.invalid_token') || 'Token invalide ou expiré'
      }
      
      addToast(errorMessage, 'error')
    } finally {
      setIsLoading(false)
    }
  }

  if (!token) {
    return null
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
                {t('auth.reset_password.success_title') || 'Mot de passe réinitialisé !'}
              </h2>
              <p className="text-center text-gray-700 dark:text-gray-200 mb-6">
                {t('auth.reset_password.success_message') || 'Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.'}
              </p>
              <p className="text-center text-sm text-gray-600 dark:text-gray-400 mb-6">
                {t('auth.reset_password.redirecting') || 'Redirection vers la page de connexion...'}
              </p>
              <Link href="/login">
                <Button className="bg-blue-500 hover:bg-blue-600 text-white">
                  {t('auth.login.title') || 'Se connecter'}
                </Button>
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                  {t('auth.reset_password.title') || 'Réinitialiser le mot de passe'}
                </h1>
                <p className="text-gray-600 dark:text-gray-400">
                  {t('auth.reset_password.description') || 'Entrez votre nouveau mot de passe ci-dessous.'}
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    {t('auth.reset_password.new_password') || 'Nouveau mot de passe'} *
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      placeholder={t('auth.register.password_placeholder') || 'Nouveau mot de passe'}
                      value={formData.new_password}
                      onChange={(e) => {
                        setFormData({ ...formData, new_password: e.target.value })
                        if (errors.new_password) setErrors({ ...errors, new_password: undefined })
                      }}
                      className={`pl-10 pr-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-blue-500 focus:ring-blue-500 ${
                        errors.new_password ? 'border-red-500' : ''
                      }`}
                      required
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  {errors.new_password && (
                    <p className="mt-1 text-sm text-red-500">{errors.new_password}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    {t('auth.reset_password.confirm_password') || 'Confirmer le mot de passe'} *
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <Input
                      type={showConfirmPassword ? 'text' : 'password'}
                      placeholder={t('auth.register.confirm_password_placeholder') || 'Confirmer le mot de passe'}
                      value={formData.confirm_password}
                      onChange={(e) => {
                        setFormData({ ...formData, confirm_password: e.target.value })
                        if (errors.confirm_password) setErrors({ ...errors, confirm_password: undefined })
                      }}
                      className={`pl-10 pr-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-blue-500 focus:ring-blue-500 ${
                        errors.confirm_password ? 'border-red-500' : ''
                      }`}
                      required
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  {errors.confirm_password && (
                    <p className="mt-1 text-sm text-red-500">{errors.confirm_password}</p>
                  )}
                </div>

                <Button
                  type="submit"
                  disabled={isLoading}
                  className="w-full h-12 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-xl"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                      {t('common.submitting') || 'Réinitialisation en cours...'}
                    </>
                  ) : (
                    t('auth.reset_password.submit') || 'Réinitialiser le mot de passe'
                  )}
                </Button>
              </form>

              <div className="mt-6 text-center">
                <Link href="/login" className="text-sm text-blue-500 hover:text-blue-600">
                  {t('auth.login.title') || 'Retour à la connexion'}
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

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-white dark:bg-gray-900 flex items-center justify-center" />}>
      <ResetPasswordPageContent />
    </Suspense>
  )
}
