'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Calendar } from 'lucide-react'
import { API_URL } from '@/lib/config'

interface SettingsDemographicsTabProps {
  user: any
  onUpdate?: () => Promise<void>
}

export function SettingsDemographicsTab({ user, onUpdate }: SettingsDemographicsTabProps) {
  const { t, language } = useLanguage()
  const { addToast } = useToast()

  const [day, setDay] = useState('')
  const [month, setMonth] = useState('')
  const [year, setYear] = useState('')
  const [gender, setGender] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errors, setErrors] = useState<{
    dateOfBirth?: string
    gender?: string
  }>({})

  // Noms des mois selon la langue
  const monthNames: Record<string, string[]> = {
    fr: ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'],
    en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    es: ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
    de: ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
  }

  const months = monthNames[language] || monthNames['en']

  // Convertir une date YYYY-MM-DD en jour, mois, année
  const parseDate = (dateString: string) => {
    if (!dateString) return { day: '', month: '', year: '' }
    const date = new Date(dateString)
    return {
      day: date.getDate().toString(),
      month: (date.getMonth() + 1).toString(),
      year: date.getFullYear().toString()
    }
  }

  // Convertir jour, mois, année en date YYYY-MM-DD
  const formatDate = (day: string, month: string, year: string): string => {
    if (!day || !month || !year) return ''
    const dayNum = parseInt(day)
    const monthNum = parseInt(month)
    const yearNum = parseInt(year)

    // Valider la date
    const date = new Date(yearNum, monthNum - 1, dayNum)
    if (date.getDate() !== dayNum || date.getMonth() !== monthNum - 1 || date.getFullYear() !== yearNum) {
      return ''
    }

    return `${yearNum}-${monthNum.toString().padStart(2, '0')}-${dayNum.toString().padStart(2, '0')}`
  }

  // Générer les années (de 100 ans à aujourd'hui)
  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: 100 }, (_, i) => currentYear - i)
  const days = Array.from({ length: 31 }, (_, i) => (i + 1).toString())

  // Charger les données de l'utilisateur au montage
  useEffect(() => {
    if (user) {
      const parsedDate = parseDate(user.date_of_birth || '')
      setDay(parsedDate.day)
      setMonth(parsedDate.month)
      setYear(parsedDate.year)
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

    const dateStr = formatDate(day, month, year)
    if (!dateStr) {
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

      const response = await fetch(`${API_URL}/api/v1/users/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          date_of_birth: formatDate(day, month, year),
          gender: gender,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || t('profile_setup.update_error') || 'Erreur lors de la mise à jour')
      }

      // Rafraîchir les données utilisateur
      if (onUpdate) {
        await onUpdate()
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

  const handleDateChange = (field: 'day' | 'month' | 'year', value: string) => {
    if (errors.dateOfBirth) {
      setErrors(prev => ({ ...prev, dateOfBirth: undefined }))
    }

    if (field === 'day') {
      setDay(value)
    } else if (field === 'month') {
      setMonth(value)
    } else if (field === 'year') {
      setYear(value)
    }
  }

  const handleGenderChange = (value: string) => {
    if (errors.gender) {
      setErrors(prev => ({ ...prev, gender: undefined }))
    }
    setGender(value)
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
          ].map((option) => (
            <label
              key={option.value}
              className={`flex items-center gap-3 p-4 rounded-xl border-2 cursor-pointer transition-all ${gender === option.value
                  ? 'border-myhigh5-primary bg-myhigh5-primary/10'
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
                onChange={(e) => handleGenderChange(e.target.value)}
                disabled={isLoading}
                className="w-4 h-4 text-myhigh5-primary"
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
        <div className="grid grid-cols-3 gap-3">
          {/* Jour */}
          <div>
            <select
              value={day}
              onChange={(e) => handleDateChange('day', e.target.value)}
              disabled={isLoading}
              className={`w-full px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-700 border text-gray-900 dark:text-white focus:outline-none focus:ring-2 transition-all ${errors.dateOfBirth
                  ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500'
                  : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
                }`}
            >
              <option value="">{language === 'fr' ? 'Jour' : language === 'es' ? 'Día' : language === 'de' ? 'Tag' : 'Day'}</option>
              {days.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>

          {/* Mois */}
          <div>
            <select
              value={month}
              onChange={(e) => handleDateChange('month', e.target.value)}
              disabled={isLoading}
              className={`w-full px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-700 border text-gray-900 dark:text-white focus:outline-none focus:ring-2 transition-all ${errors.dateOfBirth
                  ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500'
                  : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
                }`}
            >
              <option value="">{language === 'fr' ? 'Mois' : language === 'es' ? 'Mes' : language === 'de' ? 'Monat' : 'Month'}</option>
              {months.map((m, index) => (
                <option key={index + 1} value={(index + 1).toString()}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          {/* Année */}
          <div>
            <select
              value={year}
              onChange={(e) => handleDateChange('year', e.target.value)}
              disabled={isLoading}
              className={`w-full px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-700 border text-gray-900 dark:text-white focus:outline-none focus:ring-2 transition-all ${errors.dateOfBirth
                  ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500'
                  : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
                }`}
            >
              <option value="">{language === 'fr' ? 'Année' : language === 'es' ? 'Año' : language === 'de' ? 'Jahr' : 'Year'}</option>
              {years.map((y) => (
                <option key={y} value={y.toString()}>
                  {y}
                </option>
              ))}
            </select>
          </div>
        </div>
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
          className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white font-bold px-6 py-2.5 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? t('common.submitting') || 'Enregistrement...' : t('settings.save') || 'Enregistrer'}
        </Button>
      </div>
    </form>
  )
}
