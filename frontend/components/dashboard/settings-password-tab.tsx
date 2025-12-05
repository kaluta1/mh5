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

  // Validation du mot de passe
  const passwordValidation = {
    minLength: newPassword.length >= 6,
    hasUppercase: /[A-Z]/.test(newPassword),
    hasLowercase: /[a-z]/.test(newPassword),
    hasNumber: /[0-9]/.test(newPassword),
    matches: newPassword === confirmPassword && confirmPassword.length > 0
  }

  const isPasswordValid = passwordValidation.minLength && passwordValidation.matches

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!currentPassword) {
      addToast(t('settings.password.current_required') || 'Le mot de passe actuel est requis', 'error')
      return
    }

    if (!newPassword) {
      addToast(t('settings.password.new_required') || 'Le nouveau mot de passe est requis', 'error')
      return
    }

    if (newPassword.length < 6) {
      addToast(t('settings.password.min_length') || 'Le mot de passe doit contenir au moins 6 caractères', 'error')
      return
    }

    if (newPassword !== confirmPassword) {
      addToast(t('settings.password.mismatch') || 'Les mots de passe ne correspondent pas', 'error')
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
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('settings.password.current') || 'Mot de passe actuel'}
        </label>
        <div className="relative">
          <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type={showCurrentPassword ? 'text' : 'password'}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="w-full pl-10 pr-12 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-myfav-primary focus:border-transparent transition-all"
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
      </div>

      {/* New Password */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('settings.password.new') || 'Nouveau mot de passe'}
        </label>
        <div className="relative">
          <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type={showNewPassword ? 'text' : 'password'}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full pl-10 pr-12 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-myfav-primary focus:border-transparent transition-all"
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

        {/* Password Strength Indicators */}
        {newPassword.length > 0 && (
          <div className="mt-3 space-y-2">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className={`flex items-center gap-1.5 ${passwordValidation.minLength ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
                <CheckCircle2 className={`w-3.5 h-3.5 ${passwordValidation.minLength ? 'opacity-100' : 'opacity-40'}`} />
                {t('settings.password.min_6_chars') || '6 caractères minimum'}
              </div>
              <div className={`flex items-center gap-1.5 ${passwordValidation.hasUppercase ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
                <CheckCircle2 className={`w-3.5 h-3.5 ${passwordValidation.hasUppercase ? 'opacity-100' : 'opacity-40'}`} />
                {t('settings.password.uppercase') || 'Une majuscule'}
              </div>
              <div className={`flex items-center gap-1.5 ${passwordValidation.hasLowercase ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
                <CheckCircle2 className={`w-3.5 h-3.5 ${passwordValidation.hasLowercase ? 'opacity-100' : 'opacity-40'}`} />
                {t('settings.password.lowercase') || 'Une minuscule'}
              </div>
              <div className={`flex items-center gap-1.5 ${passwordValidation.hasNumber ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
                <CheckCircle2 className={`w-3.5 h-3.5 ${passwordValidation.hasNumber ? 'opacity-100' : 'opacity-40'}`} />
                {t('settings.password.number') || 'Un chiffre'}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Confirm Password */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('settings.password.confirm') || 'Confirmer le nouveau mot de passe'}
        </label>
        <div className="relative">
          <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type={showConfirmPassword ? 'text' : 'password'}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className={`w-full pl-10 pr-12 py-3 rounded-xl border bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-myfav-primary focus:border-transparent transition-all ${
              confirmPassword.length > 0 
                ? passwordValidation.matches 
                  ? 'border-green-500 dark:border-green-500' 
                  : 'border-red-500 dark:border-red-500'
                : 'border-gray-300 dark:border-gray-600'
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
        {confirmPassword.length > 0 && !passwordValidation.matches && (
          <p className="mt-1 text-xs text-red-500">
            {t('settings.password.mismatch') || 'Les mots de passe ne correspondent pas'}
          </p>
        )}
      </div>

      {/* Submit Button */}
      <div className="flex justify-end pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button
          type="submit"
          disabled={isLoading || !isPasswordValid || !currentPassword}
          className="bg-myfav-primary hover:bg-myfav-primary/90 text-white px-8 py-3 rounded-xl font-medium shadow-lg shadow-myfav-primary/25 disabled:opacity-50 disabled:cursor-not-allowed"
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
