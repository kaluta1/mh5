'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Eye, EyeOff, Loader2, ArrowLeft, Heart, Mail, Lock, CheckCircle, Gift } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { LanguageSelector } from '@/components/ui/language-selector'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useToast } from '@/components/ui/toast'

export default function LoginPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { isAuthenticated, login } = useAuth()
  const { addToast } = useToast()
  
  const [formData, setFormData] = useState({
    emailOrUsername: '',
    password: ''
  })
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [referralCode, setReferralCode] = useState<string | null>(null)

  // Vérifier si un code de parrainage est présent dans l'URL
  useEffect(() => {
    const refCode = searchParams.get('ref') || searchParams.get('referral')
    if (refCode) {
      setReferralCode(refCode)
      // Stocker le code de parrainage dans localStorage pour l'inscription
      localStorage.setItem('referral_code', refCode)
    } else {
      // Vérifier si un code est déjà stocké
      const storedCode = localStorage.getItem('referral_code')
      if (storedCode) {
        setReferralCode(storedCode)
      }
    }
  }, [searchParams])

  // Rediriger si déjà connecté
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/dashboard/contests')
    }
  }, [isAuthenticated, router])

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleLogin = async () => {
    // Empêcher les soumissions multiples
    if (isLoading) {
      return
    }
    
    // Validation basique côté client
    if (!formData.emailOrUsername.trim() || !formData.password.trim()) {
      addToast(t('auth.login.errors.invalid_credentials'), 'error', 6000)
      return
    }
    
    setIsLoading(true)

    try {
      // Utiliser la fonction login du hook useAuth pour mettre à jour le contexte
      await login({
        email_or_username: formData.emailOrUsername.trim(),
        password: formData.password,
      })

      // Afficher la page de succès et rediriger
      setIsSuccess(true)
      // La redirection se fait via le useEffect qui surveille isAuthenticated
    } catch (err: any) {
      console.error('Login error:', err)
      
      // Fonction pour mapper les erreurs backend aux traductions
      const mapErrorToTranslation = (message: string): string => {
        const lowerMessage = message.toLowerCase()
        
        // Détecter les erreurs d'identifiants invalides dans différentes langues
        if (lowerMessage.includes('incorrect') || 
            lowerMessage.includes('invalid') || 
            lowerMessage.includes('invalide') ||
            lowerMessage.includes('inválido') ||
            lowerMessage.includes('ungültig') ||
            lowerMessage.includes('email') && (lowerMessage.includes('password') || lowerMessage.includes('mot de passe') || lowerMessage.includes('contraseña') || lowerMessage.includes('passwort')) ||
            lowerMessage.includes('username') && (lowerMessage.includes('password') || lowerMessage.includes('mot de passe') || lowerMessage.includes('contraseña') || lowerMessage.includes('passwort')) ||
            lowerMessage.includes('nom d\'utilisateur') && (lowerMessage.includes('mot de passe')) ||
            lowerMessage.includes('nombre de usuario') && (lowerMessage.includes('contraseña')) ||
            lowerMessage.includes('benutzername') && (lowerMessage.includes('passwort'))) {
          return t('auth.login.errors.invalid_credentials')
        }
        
        return message
      }
      
      let errorMessage = t('auth.login.errors.invalid_credentials')
      
      if (err.response?.data) {
        const errorData = err.response.data
        if (typeof errorData === 'string') {
          errorMessage = mapErrorToTranslation(errorData)
        } else if (errorData.detail) {
          if (typeof errorData.detail === 'string') {
            errorMessage = mapErrorToTranslation(errorData.detail)
          } else if (Array.isArray(errorData.detail)) {
            const messages = errorData.detail.map(e => e.msg || e).join(', ')
            errorMessage = mapErrorToTranslation(messages)
          } else {
            errorMessage = t('auth.login.errors.invalid_credentials')
          }
        } else if (errorData.message) {
          errorMessage = mapErrorToTranslation(errorData.message)
        }
      } else if (err.message) {
        errorMessage = mapErrorToTranslation(err.message)
      }
      
      // Afficher l'erreur dans un toast (pas de rechargement de page)
      addToast(errorMessage, 'error', 6000)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    // Empêcher le comportement par défaut du formulaire
    e.preventDefault()
    e.stopPropagation()
    // Appeler la fonction de login
    handleLogin()
    return false
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-gray-900 dark:via-blue-900/20 dark:to-purple-900/20 relative overflow-hidden">
      {/* Background decorative elements */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-blue-400/10 rounded-full blur-3xl"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-purple-400/10 rounded-full blur-3xl"></div>
      </div>

      {/* Header avec contrôles */}
      <div className="relative z-10 flex justify-between items-center p-6">
        <Link 
          href="/"
          className="inline-flex items-center text-sm font-medium text-gray-700 hover:text-myfav-primary dark:text-gray-200 dark:hover:text-myfav-blue-400 transition-colors"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {t('navigation.home')}
        </Link>
        
        <div className="flex items-center space-x-3">
          <LanguageSelector />
          <ThemeToggle />
        </div>
      </div>

      {/* Main content */}
      <div className="relative z-10 flex items-center justify-center min-h-[calc(100vh-120px)] p-4">
        <div className="w-full max-w-md">
          {/* Logo et titre */}
          <div className="text-center mb-2">
           
            <h1 className="text-4xl font-bold dsm-title mb-3">
              {t('auth.login.title')}
            </h1>
            <p className="text-lg text-gray-700 dark:text-gray-200 max-w-md mx-auto">
              {t('auth.login.subtitle')}
            </p>
          </div>

          {/* Bannière code de parrainage */}
          {referralCode && (
            <div className="mb-4 p-4 bg-gradient-to-r from-myfav-primary/10 to-purple-500/10 dark:from-myfav-primary/20 dark:to-purple-500/20 rounded-xl border border-myfav-primary/20 dark:border-myfav-primary/30">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-myfav-primary/20 flex items-center justify-center">
                  <Gift className="w-5 h-5 text-myfav-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {t('auth.referral_detected') || 'Code de parrainage détecté !'}
                  </p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">
                    {t('auth.referral_code') || 'Code'}: <span className="font-mono font-bold text-myfav-primary">{referralCode}</span>
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Formulaire ou Succès */}
          <div className="bg-white/80 dark:bg-gray-800/90 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/20 dark:border-gray-700/50 p-8">
            {isSuccess ? (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="mb-6 animate-bounce">
                  <CheckCircle className="w-16 h-16 text-green-500" />
                </div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                  {t('common.success')}
                </h2>
                <p className="text-center text-gray-700 dark:text-gray-200 mb-6">
                  {t('common.redirecting')}
                </p>
                <div className="flex items-center space-x-2">
                  <Loader2 className="w-5 h-5 animate-spin text-myfav-primary" />
                  <span className="text-sm text-gray-600 dark:text-gray-400">{t('common.please_wait')}</span>
                </div>
              </div>
            ) : (
              <form 
                onSubmit={handleSubmit} 
                noValidate
                className="space-y-6"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && isLoading) {
                    e.preventDefault()
                    e.stopPropagation()
                  }
                }}
              >
              {/* Email/Username */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                  {t('auth.email')} {t('common.or')} {t('auth.username')} *
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                  <Input
                    type="text"
                    placeholder={t('auth.login.email_placeholder')}
                    value={formData.emailOrUsername}
                    onChange={(e) => handleInputChange('emailOrUsername', e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && isLoading) {
                        e.preventDefault()
                      }
                    }}
                    className="pl-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-myfav-primary focus:ring-myfav-primary dsm-input"
                    required
                    disabled={isLoading}
                  />
                </div>
              </div>

              {/* Password */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                  {t('auth.password')} *
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    placeholder={t('auth.login.password_placeholder')}
                    value={formData.password}
                    onChange={(e) => handleInputChange('password', e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && isLoading) {
                        e.preventDefault()
                      }
                    }}
                    className="pl-10 pr-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-myfav-primary focus:ring-myfav-primary dsm-input"
                    required
                    disabled={isLoading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                    disabled={isLoading}
                  >
                    {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </div>
              </div>

              {/* Forgot Password */}
              <div className="flex justify-end">
                <button
                  type="button"
                  className="text-sm text-myfav-primary hover:text-myfav-primary-dark dark:text-myfav-blue-400 dark:hover:text-myfav-blue-300 transition-colors"
                  onClick={() => {
                    // TODO: Implémenter mot de passe oublié
                    console.log("Mot de passe oublié")
                  }}
                >
                  {t('auth.login.forgot_password')}
                </button>
              </div>

              {/* Submit Button */}
              <Button
                type="button"
                className="w-full h-12 bg-myfav-primary hover:bg-myfav-primary-dark text-white font-semibold rounded-xl shadow-lg hover:shadow-xl transition-all duration-200"
                disabled={isLoading}
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  handleLogin()
                }}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    {t('auth.login.loading')}
                  </>
                ) : (
                  <>
                    <Heart className="mr-2 h-5 w-5" />
                    {t('auth.login.submit')}
                  </>
                )}
              </Button>

              {/* Register Link */}
              <div className="text-center pt-4">
                <span className="text-sm text-gray-700 dark:text-gray-200">
                  {t('auth.login.no_account')}{' '}
                </span>
                <Link
                  href={referralCode ? `/register?ref=${referralCode}` : '/register'}
                  className="text-sm font-semibold text-myfav-primary hover:text-myfav-primary-dark dark:text-myfav-blue-400 dark:hover:text-myfav-blue-300 transition-colors"
                >
                  {t('auth.login.register_link')}
                </Link>
              </div>
            </form>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
