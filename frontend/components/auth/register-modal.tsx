'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { authService } from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'

interface RegisterModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSwitchToLogin?: () => void
}

export default function RegisterModal({ open, onOpenChange, onSwitchToLogin }: RegisterModalProps) {
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    confirmPassword: '',
    fullName: '',
    phone: '',
    referralCode: ''
  })
  
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  // Vérifier le code de parrainage au chargement
  useEffect(() => {
    if (open) {
      // Vérifier d'abord dans l'URL
      const urlReferralCode = searchParams.get('ref') || searchParams.get('referral')
      
      // Ensuite vérifier dans localStorage
      const storedReferralCode = localStorage.getItem('referralCode')
      
      // Prioriser l'URL sur localStorage
      const referralCode = urlReferralCode || storedReferralCode || ''
      
      if (referralCode) {
        setFormData(prev => ({ ...prev, referralCode }))
        
        // Sauvegarder dans localStorage si vient de l'URL
        if (urlReferralCode) {
          localStorage.setItem('referralCode', urlReferralCode)
        }
      }
    }
  }, [open, searchParams])

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    if (error) setError('')
  }

  const validateForm = () => {
    if (!formData.email || !formData.username || !formData.password || !formData.confirmPassword) {
      setError(t('auth.register.errors.required_fields'))
      return false
    }

    if (formData.password !== formData.confirmPassword) {
      setError(t('auth.register.errors.password_mismatch'))
      return false
    }

    if (formData.password.length < 6) {
      setError(t('auth.register.errors.password_min_length'))
      return false
    }

    if (!acceptTerms) {
      setError(t('auth.register.errors.terms_required'))
      return false
    }

    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateForm()) return

    setIsLoading(true)
    setError('')

    try {
      const registerData = {
        email: formData.email,
        username: formData.username,
        password: formData.password,
        full_name: formData.fullName || undefined,
        phone: formData.phone || undefined,
        referral_code: formData.referralCode || undefined
      }

      const response = await authService.register(registerData)
      
      // Stocker les tokens si fournis
      if (response.access_token) {
        localStorage.setItem('access_token', response.access_token)
      }
      if (response.refresh_token) {
        localStorage.setItem('refresh_token', response.refresh_token)
      }

      // Nettoyer le code de parrainage utilisé
      localStorage.removeItem('referralCode')
      
      // Fermer le modal et rediriger
      onOpenChange(false)
      router.push('/dashboard')
      
    } catch (err: any) {
      console.error('Registration error:', err)
      
      // Gérer les erreurs de validation Pydantic (tableau d'erreurs)
      if (Array.isArray(err.response?.data)) {
        const errorMessages = err.response.data
          .map((e: any) => e.msg || e.detail || 'Erreur inconnue')
          .join(', ')
        setError(errorMessages)
      } else if (err.response?.data?.detail) {
        // Gérer les erreurs simples avec un message detail
        setError(err.response.data.detail)
      } else {
        setError('Erreur lors de l\'inscription')
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleSwitchToLogin = () => {
    onOpenChange(false)
    if (onSwitchToLogin) {
      onSwitchToLogin()
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md dsm-bg-light">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-center dsm-title">
            {t('auth.register.title')}
          </DialogTitle>
          <DialogDescription className="text-center dsm-text-gray">
            {t('auth.register.subtitle')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
              {error}
            </div>
          )}

          <div className="space-y-3">
            <Input
              type="email"
              placeholder={t('auth.register.email_placeholder')}
              value={formData.email}
              onChange={(e) => handleInputChange('email', e.target.value)}
              className="dsm-input"
              required
            />

            <Input
              type="text"
              placeholder={t('auth.register.username_placeholder')}
              value={formData.username}
              onChange={(e) => handleInputChange('username', e.target.value)}
              className="dsm-input"
              required
            />

            <div className="relative">
              <Input
                type={showPassword ? 'text' : 'password'}
                placeholder={t('auth.register.password_placeholder')}
                value={formData.password}
                onChange={(e) => handleInputChange('password', e.target.value)}
                className="dsm-input pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>

            <div className="relative">
              <Input
                type={showConfirmPassword ? 'text' : 'password'}
                placeholder={t('auth.register.confirm_password_placeholder')}
                value={formData.confirmPassword}
                onChange={(e) => handleInputChange('confirmPassword', e.target.value)}
                className="dsm-input pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>

            <Input
              type="text"
              placeholder={t('auth.register.full_name_placeholder')}
              value={formData.fullName}
              onChange={(e) => handleInputChange('fullName', e.target.value)}
              className="dsm-input"
            />

            <Input
              type="tel"
              placeholder={t('auth.register.phone_placeholder')}
              value={formData.phone}
              onChange={(e) => handleInputChange('phone', e.target.value)}
              className="dsm-input"
            />

            <Input
              type="text"
              placeholder={t('auth.register.referral_code_placeholder')}
              value={formData.referralCode}
              onChange={(e) => handleInputChange('referralCode', e.target.value)}
              className="dsm-input"
            />
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="terms"
              checked={acceptTerms}
              onCheckedChange={setAcceptTerms}
            />
            <label
              htmlFor="terms"
              className="text-sm text-gray-700 dark:text-gray-200 cursor-pointer"
            >
              {t('auth.register.terms_accept')}
            </label>
          </div>

          <Button
            type="submit"
            className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white font-semibold"
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('auth.register.loading')}
              </>
            ) : (
              t('auth.register.submit')
            )}
          </Button>

          <div className="text-center">
            <span className="text-sm text-gray-700 dark:text-gray-200">
              {t('auth.register.have_account')}{' '}
            </span>
            <button
              type="button"
              onClick={handleSwitchToLogin}
              className="text-sm font-medium text-myhigh5-primary hover:text-myhigh5-primary-dark dark:text-myhigh5-blue-400 dark:hover:text-myhigh5-blue-300"
            >
              {t('auth.register.login_link')}
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
