'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Calendar } from 'lucide-react'

interface SettingsDemographicsTabProps {
  user: any
}

export function SettingsDemographicsTab({ user }: SettingsDemographicsTabProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [dateOfBirth, setDateOfBirth] = useState('')
  const [gender, setGender] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errors, setErrors] = useState<{
    dateOfBirth?: string
    gender?: string
  }>({})

  // Charger les données de l'utilisateur au montage
  useEffect(() => {
    if (user) {
      setDateOfBirth(user.date_of_birth ? user.date_of_birth.split('T')[0] : '')
      setGender(user.gender || '')
      
      // Valider et afficher les erreurs par défaut
      const newErrors: typeof errors = {}
      
      if (!user.date_of_birth) {
        newErrors.dateOfBirth = t('profile_setup.dob_required') || 'La date de naissance est requise'
      }
      
      if (!user.gender) {
        newErrors.gender = t('profile_setup.gender_required') || 'Le genre est requis'
      }
      
      setErrors(newErrors)
    }
  }, [user, t])

  const validateForm = () => {
    const newErrors: typeof errors = {}
    
    if (!dateOfBirth.trim()) {
      newErrors.dateOfBirth = t('profile_setup.dob_required') || 'La date de naissance est requise'
    }
    
    if (!gender.trim()) {
      newErrors.gender = t('profile_setup.gender_required') || 'Le genre est requis'
    }
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!validateForm()) {
      return
    }

    try {
      setIsLoading(true)

      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      if (!token) {
        addToast(t('profile_setup.session_expired') || 'Session expirée', 'error')
        return
      }

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/v1/users/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          date_of_birth: dateOfBirth,
          gender: gender,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || t('profile_setup.update_error') || 'Erreur lors de la mise à jour')
      }

      addToast(t('profile_setup.success') || 'Informations mises à jour avec succès!', 'success')
      setErrors({})
    } catch (err: any) {
      console.error('Erreur:', err)
      addToast(err.message || 'Erreur lors de la mise à jour des informations', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleFieldChange = (field: 'dateOfBirth' | 'gender', value: string) => {
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }
    
    if (field === 'dateOfBirth') {
      setDateOfBirth(value)
    } else if (field === 'gender') {
      setGender(value)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Gender Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {t('profile_setup.gender') || 'Genre'} *
        </h3>
        <div className={`grid grid-cols-2 gap-3 ${errors.gender ? 'mb-2' : ''}`}>
          {[
            { value: 'male', label: t('profile_setup.male') || 'Homme' },
            { value: 'female', label: t('profile_setup.female') || 'Femme' },
            { value: 'other', label: t('profile_setup.other') || 'Autre' },
            { value: 'prefer_not_to_say', label: t('profile_setup.prefer_not_to_say') || 'Préfère ne pas dire' },
          ].map((option) => (
            <label
              key={option.value}
              className={`flex items-center gap-3 p-4 rounded-xl border-2 cursor-pointer transition-all ${
                gender === option.value
                  ? 'border-myfav-primary bg-myfav-primary/10'
                  : errors.gender
                  ? 'border-red-500 dark:border-red-500 bg-red-50 dark:bg-red-900/10'
                  : 'border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/50 hover:border-gray-300 dark:hover:border-gray-500'
              }`}
            >
              <input
                type="radio"
                name="gender"
                value={option.value}
                checked={gender === option.value}
                onChange={(e) => handleFieldChange('gender', e.target.value)}
                disabled={isLoading}
                className="w-4 h-4 text-myfav-primary"
              />
              <span className="text-gray-900 dark:text-white font-medium">{option.label}</span>
            </label>
          ))}
        </div>
        {errors.gender && (
          <p className="text-sm text-red-600 dark:text-red-400 mt-2">
            {errors.gender}
          </p>
        )}
      </div>

      {/* Date of Birth Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Calendar className="w-5 h-5" />
          {t('profile_setup.date_of_birth') || 'Date de Naissance'} *
        </h3>
        <input
          type="date"
          value={dateOfBirth}
          onChange={(e) => handleFieldChange('dateOfBirth', e.target.value)}
          disabled={isLoading}
          className={`w-full px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-700 border text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-all ${
            errors.dateOfBirth
              ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500'
              : 'border-gray-300 dark:border-gray-600 focus:ring-myfav-primary focus:border-transparent'
          }`}
        />
        {errors.dateOfBirth && (
          <p className="text-sm text-red-600 dark:text-red-400 mt-2">
            {errors.dateOfBirth}
          </p>
        )}
      </div>

      {/* Submit Button */}
      <div className="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700">
        <Button
          type="submit"
          disabled={isLoading}
          className="bg-myfav-primary hover:bg-myfav-primary/90 text-white font-bold px-6 py-2.5 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? t('common.submitting') || 'Enregistrement...' : t('settings.save') || 'Enregistrer'}
        </Button>
      </div>
    </form>
  )
}
