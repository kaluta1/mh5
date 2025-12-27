'use client'

import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Eye, EyeOff, Lock, Shield, CheckCircle2 } from 'lucide-react'

interface SettingsPasswordTabProps {
  user: any
}

export function SettingsPasswordTab({ user }: SettingsPasswordTabProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [passwordErrors, setPasswordErrors] = useState({
    hasMinLength: false,
    hasUpperCase: false,
    hasLowerCase: false,
    hasNumber: false,
    hasSpecialChar: false
  })
  const [errors, setErrors] = useState<{
    currentPassword?: string
    newPassword?: string
    confirmPassword?: string
  }>({})

  // Validation du mot de passe en temps réel
  const validatePassword = (value: string) => {
    const errors = {
      hasMinLength: value.length >= 8,
      hasUpperCase: /[A-Z]/.test(value),
      hasLowerCase: /[a-z]/.test(value),
      hasNumber: /[0-9]/.test(value),
      hasSpecialChar: /[*_/@=]/.test(value)
    }
    setPasswordErrors(errors)
  }

  // Vérifier si toutes les exigences du mot de passe sont remplies
  const isPasswordValid = () => {
    if (!newPassword) return false
    return newPassword.length >= 8 &&
           passwordErrors.hasUpperCase &&
           passwordErrors.hasLowerCase &&
           passwordErrors.hasNumber &&
           passwordErrors.hasSpecialChar
  }

  const validateForm = () => {
    const newErrors: typeof errors = {}
    
    if (!currentPassword.trim()) {
      newErrors.currentPassword = t('settings.password.current_required') || 'Le mot de passe actuel est requis'
    }
    
    if (!newPassword.trim()) {
      newErrors.newPassword = t('settings.password.new_required') || 'Le nouveau mot de passe est requis'
    } else if (!isPasswordValid()) {
      newErrors.newPassword = t('auth.register.errors.password_requirements') || 'Le mot de passe doit contenir une majuscule, une minuscule, un chiffre et un caractère spécial (*_/@=)'
    }
    
    if (!confirmPassword.trim()) {
      newErrors.confirmPassword = t('settings.password.confirm_required') || 'La confirmation du mot de passe est requise'
    } else if (newPassword !== confirmPassword) {
      newErrors.confirmPassword = t('settings.password.mismatch') || 'Les mots de passe ne correspondent pas'
    }
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleFieldChange = (field: 'currentPassword' | 'newPassword' | 'confirmPassword', value: string) => {
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }
    
    if (field === 'currentPassword') {
      setCurrentPassword(value)
    } else if (field === 'newPassword') {
      setNewPassword(value)
      validatePassword(value)
    } else if (field === 'confirmPassword') {
      setConfirmPassword(value)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!validateForm()) {
      return
    }

    if (currentPassword === newPassword) {
      addToast(t('settings.password.same_password') || 'Le nouveau mot de passe doit être différent de l\'ancien', 'error')
      return
    }

    try {
      setIsLoading(true)

      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      if (!token) {
        addToast(t('settings.password.session_expired') || 'Session expirée', 'error')
        return
      }

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/v1/auth/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      })

      if (response.ok) {
        addToast(t('settings.password.success') || 'Mot de passe modifié avec succès', 'success')
        // Reset form
        setCurrentPassword('')
        setNewPassword('')
        setConfirmPassword('')
        setErrors({})
        setPasswordErrors({
          hasMinLength: false,
          hasUpperCase: false,
          hasLowerCase: false,
          hasNumber: false,
          hasSpecialChar: false
        })
      } else {
        const data = await response.json()
        addToast(data.detail || t('settings.password.error') || 'Erreur lors du changement de mot de passe', 'error')
      }
    } catch (error) {
      console.error('Error changing password:', error)
      addToast(t('settings.password.error') || 'Erreur lors du changement de mot de passe', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Security Info */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700/50 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <Shield className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-medium text-blue-900 dark:text-blue-100">
              {t('settings.password.security_info') || 'Sécurité de votre compte'}
            </h4>
            <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
              {t('settings.password.security_description') || 'Pour protéger votre compte, utilisez un mot de passe fort et unique.'}
            </p>
          </div>
        </div>
      </div>

      {/* Current Password */}
      <div>
        <label className={`block text-sm font-medium mb-2 ${errors.currentPassword ? 'text-red-500 dark:text-red-400' : 'text-gray-700 dark:text-gray-300'}`}>
          {t('settings.password.current') || 'Mot de passe actuel'} *
        </label>
        <div className="relative">
          <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${errors.currentPassword ? 'text-red-400' : 'text-gray-400'}`} />
          <input
            type={showCurrentPassword ? 'text' : 'password'}
            value={currentPassword}
            onChange={(e) => handleFieldChange('currentPassword', e.target.value)}
            className={`w-full pl-10 pr-12 py-3 rounded-xl border bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 transition-all ${
              errors.currentPassword
                ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500 bg-red-50 dark:bg-red-900/10'
                : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
            }`}
            placeholder="••••••••"
          />
          <button
            type="button"
            onClick={() => setShowCurrentPassword(!showCurrentPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            {showCurrentPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
          </button>
        </div>
        {errors.currentPassword && (
          <p className="text-sm text-red-600 dark:text-red-400 mt-2">
            {errors.currentPassword}
          </p>
        )}
      </div>

      {/* New Password */}
      <div>
        <label className={`block text-sm font-medium mb-2 ${errors.newPassword ? 'text-red-500 dark:text-red-400' : 'text-gray-700 dark:text-gray-300'}`}>
          {t('settings.password.new') || 'Nouveau mot de passe'} *
        </label>
        <div className="relative">
          <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${errors.newPassword || (newPassword && !isPasswordValid()) ? 'text-red-400' : 'text-gray-400'}`} />
          <input
            type={showNewPassword ? 'text' : 'password'}
            value={newPassword}
            onChange={(e) => handleFieldChange('newPassword', e.target.value)}
            className={`w-full pl-10 pr-12 py-3 rounded-xl border bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 transition-all ${
              errors.newPassword || (newPassword && !isPasswordValid())
                ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500 bg-red-50 dark:bg-red-900/10'
                : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
            }`}
            placeholder="••••••••"
          />
          <button
            type="button"
            onClick={() => setShowNewPassword(!showNewPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            {showNewPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
          </button>
        </div>
        {errors.newPassword && (
          <p className="text-sm text-red-600 dark:text-red-400 mt-2">
            {errors.newPassword}
          </p>
        )}

        {/* Password Strength Indicators */}
        {newPassword && (
          <div className="mt-2 space-y-1">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('auth.register.password_requirements_title') || 'Le mot de passe doit contenir :'}
            </p>
            <div className="space-y-0.5">
              <div className={`text-xs flex items-center gap-2 ${passwordErrors.hasMinLength ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                <span>{passwordErrors.hasMinLength ? '✓' : '○'}</span>
                <span>
                  {t('auth.register.password_requirement_min_length') || 'Au moins 8 caractères'}
                </span>
              </div>
              <div className={`text-xs flex items-center gap-2 ${passwordErrors.hasUpperCase ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                <span>{passwordErrors.hasUpperCase ? '✓' : '○'}</span>
                <span>
                  {t('auth.register.password_requirement_uppercase') || 'Une majuscule (A-Z)'}
                </span>
              </div>
              <div className={`text-xs flex items-center gap-2 ${passwordErrors.hasLowerCase ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                <span>{passwordErrors.hasLowerCase ? '✓' : '○'}</span>
                <span>
                  {t('auth.register.password_requirement_lowercase') || 'Une minuscule (a-z)'}
                </span>
              </div>
              <div className={`text-xs flex items-center gap-2 ${passwordErrors.hasNumber ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                <span>{passwordErrors.hasNumber ? '✓' : '○'}</span>
                <span>
                  {t('auth.register.password_requirement_number') || 'Un chiffre (0-9)'}
                </span>
              </div>
              <div className={`text-xs flex items-center gap-2 ${passwordErrors.hasSpecialChar ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                <span>{passwordErrors.hasSpecialChar ? '✓' : '○'}</span>
                <span>
                  {t('auth.register.password_requirement_special') || 'Un caractère spécial (*_/@=)'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Confirm Password */}
      <div>
        <label className={`block text-sm font-medium mb-2 ${errors.confirmPassword ? 'text-red-500 dark:text-red-400' : 'text-gray-700 dark:text-gray-300'}`}>
          {t('settings.password.confirm') || 'Confirmer le nouveau mot de passe'} *
        </label>
        <div className="relative">
          <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${errors.confirmPassword || (confirmPassword.length > 0 && newPassword !== confirmPassword) ? 'text-red-400' : confirmPassword.length > 0 && newPassword === confirmPassword ? 'text-green-400' : 'text-gray-400'}`} />
          <input
            type={showConfirmPassword ? 'text' : 'password'}
            value={confirmPassword}
            onChange={(e) => handleFieldChange('confirmPassword', e.target.value)}
            className={`w-full pl-10 pr-12 py-3 rounded-xl border bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 transition-all ${
              errors.confirmPassword || (confirmPassword.length > 0 && newPassword !== confirmPassword)
                ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500 bg-red-50 dark:bg-red-900/10'
                : confirmPassword.length > 0 && newPassword === confirmPassword
                ? 'border-green-500 dark:border-green-500 focus:ring-green-500 focus:border-green-500'
                : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
            }`}
            placeholder="••••••••"
          />
          <button
            type="button"
            onClick={() => setShowConfirmPassword(!showConfirmPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
          </button>
        </div>
        {errors.confirmPassword && (
          <p className="text-sm text-red-600 dark:text-red-400 mt-2">
            {errors.confirmPassword}
          </p>
        )}
        {confirmPassword.length > 0 && !errors.confirmPassword && newPassword !== confirmPassword && (
          <p className="text-sm text-red-600 dark:text-red-400 mt-2">
            {t('settings.password.mismatch') || 'Les mots de passe ne correspondent pas'}
          </p>
        )}
      </div>

      {/* Submit Button */}
      <div className="flex justify-end pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button
          type="submit"
          disabled={isLoading}
          className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white px-8 py-3 rounded-xl font-medium shadow-lg shadow-myhigh5-primary/25 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              {t('settings.password.saving') || 'Modification...'}
            </span>
          ) : (
            t('settings.password.save') || 'Modifier le mot de passe'
          )}
        </Button>
      </div>
    </form>
  )
}
