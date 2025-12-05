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

  // Charger les données de l'utilisateur au montage
  useEffect(() => {
    if (user) {
      setDateOfBirth(user.date_of_birth ? user.date_of_birth.split('T')[0] : '')
      setGender(user.gender || '')
    }
  }, [user])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!dateOfBirth) {
      addToast(t('profile_setup.dob_required') || 'La date de naissance est requise', 'error')
      return
    }

    if (!gender) {
      addToast(t('profile_setup.gender_required') || 'Le genre est requis', 'error')
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
    } catch (err: any) {
      console.error('Erreur:', err)
      addToast(err.message || 'Erreur lors de la mise à jour des informations', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Gender Section */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4">
          {t('profile_setup.gender') || 'Genre'} *
        </h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            { value: 'male', label: t('profile_setup.male') || 'Homme' },
            { value: 'female', label: t('profile_setup.female') || 'Femme' },
            { value: 'other', label: t('profile_setup.other') || 'Autre' },
            { value: 'prefer_not_to_say', label: t('profile_setup.prefer_not_to_say') || 'Préfère ne pas dire' },
          ].map((option) => (
            <label
              key={option.value}
              className={`flex items-center gap-3 p-3 rounded-lg border-2 cursor-pointer transition ${
                gender === option.value
                  ? 'border-myfav-primary bg-myfav-primary/10'
                  : 'border-gray-600 bg-gray-700/50 hover:border-gray-500'
              }`}
            >
              <input
                type="radio"
                name="gender"
                value={option.value}
                checked={gender === option.value}
                onChange={(e) => setGender(e.target.value)}
                disabled={isLoading}
                className="w-4 h-4"
              />
              <span className="text-white font-medium">{option.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Date of Birth Section */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Calendar className="w-5 h-5" />
          {t('profile_setup.date_of_birth') || 'Date de Naissance'} *
        </h3>
        <input
          type="date"
          value={dateOfBirth}
          onChange={(e) => setDateOfBirth(e.target.value)}
          disabled={isLoading}
          className="w-full px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
        />
      </div>

      {/* Submit Button */}
      <div className="flex justify-end gap-3 pt-6 border-t border-gray-700">
        <Button
          type="submit"
          disabled={isLoading || !dateOfBirth || !gender}
          className="bg-myfav-primary hover:bg-myfav-primary-dark text-white font-bold"
        >
          {isLoading ? t('common.submitting') || 'Soumission...' : t('settings.save') || 'Enregistrer'}
        </Button>
      </div>
    </form>
  )
}
