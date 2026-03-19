'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { UploadButton } from '@/components/ui/upload-button'
import { User, FileText, Image as ImageIcon, MapPin } from 'lucide-react'
import { API_URL } from '@/lib/config'
import geographyData from '@/lib/geography-data-complete.json'
import { getCitiesByCountry } from '@/lib/geography'

interface SettingsProfileTabProps {
  user: any
  onUpdate?: () => Promise<void>
}

export function SettingsProfileTab({ user, onUpdate }: SettingsProfileTabProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [avatarUrl, setAvatarUrl] = useState('')
  const [bio, setBio] = useState('')
  const [city, setCity] = useState('')
  const [availableCities, setAvailableCities] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [errors, setErrors] = useState<{
    firstName?: string
    lastName?: string
    avatarUrl?: string
    bio?: string
    city?: string
  }>({})

  // Charger les données de l'utilisateur au montage
  useEffect(() => {
    if (user) {
      setFirstName(user.first_name || '')
      setLastName(user.last_name || '')
      setAvatarUrl(user.avatar_url || '')
      setBio(user.bio || '')
      setCity(user.city || '')

      // Charger les villes du pays de l'utilisateur
      if (user.country) {
        const countryName = user.country.trim().toLowerCase()
        const countryData = geographyData.countries.find(
          (c: any) => c.name.trim().toLowerCase() === countryName
        )
        if (countryData?.code) {
          try {
            const cities = getCitiesByCountry(countryData.code.toUpperCase())
            if (Array.isArray(cities) && cities.length > 0) {
              setAvailableCities(cities)
            }
          } catch (e) {
            console.error('Error loading cities:', e)
          }
        }
      }

      // Valider et afficher les erreurs par défaut
      const newErrors: typeof errors = {}

      if (!user.first_name?.trim()) {
        newErrors.firstName = t('profile_setup.first_name_required') || 'Le prénom est requis'
      }

      if (!user.last_name?.trim()) {
        newErrors.lastName = t('profile_setup.last_name_required') || 'Le nom est requis'
      }

      if (!user.avatar_url) {
        newErrors.avatarUrl = t('profile_setup.avatar_required') || 'L\'avatar est requis'
      }

      if (!user.bio?.trim()) {
        newErrors.bio = t('profile_setup.bio_required') || 'La bio est requise'
      }

      if (!user.city?.trim()) {
        newErrors.city = t('profile_setup.city_required') || 'La ville est requise'
      }

      setErrors(newErrors)
    }
  }, [user, t])

  const validateForm = () => {
    const newErrors: typeof errors = {}

    if (!firstName.trim()) {
      newErrors.firstName = t('profile_setup.first_name_required') || 'Le prénom est requis'
    }

    if (!lastName.trim()) {
      newErrors.lastName = t('profile_setup.last_name_required') || 'Le nom est requis'
    }

    if (!avatarUrl) {
      newErrors.avatarUrl = t('profile_setup.avatar_required') || 'L\'avatar est requis'
    }

    if (!bio.trim()) {
      newErrors.bio = t('profile_setup.bio_required') || 'La bio est requise'
    }

    if (!city.trim()) {
      newErrors.city = t('profile_setup.city_required') || 'La ville est requise'
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
          first_name: firstName,
          last_name: lastName,
          avatar_url: avatarUrl,
          bio: bio,
          city: city,
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

      addToast(t('profile_setup.success') || 'Profil mis à jour avec succès!', 'success')
      setErrors({})
    } catch (err: any) {
      console.error('Erreur:', err)
      addToast(err.message || 'Erreur lors de la mise à jour du profil', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleFieldChange = (field: 'firstName' | 'lastName' | 'bio' | 'city', value: string) => {
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }

    if (field === 'firstName') {
      setFirstName(value)
    } else if (field === 'lastName') {
      setLastName(value)
    } else if (field === 'bio') {
      setBio(value.slice(0, 500))
    } else if (field === 'city') {
      setCity(value)
    }
  }

  const handleAvatarChange = async (url: string) => {
    setAvatarUrl(url)
    if (errors.avatarUrl) {
      setErrors(prev => ({ ...prev, avatarUrl: undefined }))
    }

    // Sauvegarder automatiquement la photo de profil
    if (url) {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
        if (!token) {
          return
        }

        const response = await fetch(`${API_URL}/api/v1/users/me`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({
            avatar_url: url,
          }),
        })

        if (response.ok) {
          // Rafraîchir les données utilisateur pour mettre à jour l'affichage
          if (onUpdate) {
            await onUpdate()
          }
        }
      } catch (err) {
        console.error('Erreur lors de la sauvegarde automatique de la photo:', err)
      }
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Avatar Upload - En haut */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-4 flex items-center justify-center gap-2">
          <ImageIcon className="w-4 h-4" />
          {t('profile_setup.avatar') || 'Avatar'} *
        </label>
        <div className="flex justify-center mb-8">
          {avatarUrl ? (
            <div className="flex flex-col items-center gap-4">
              <img src={avatarUrl} alt="Avatar" className="w-32 h-32 rounded-full object-cover border-4 border-myhigh5-primary shadow-lg" />
              <div className="flex gap-2">
                <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-2 bg-gray-50 dark:bg-gray-700/50">
                  <UploadButton
                    endpoint="profileAvatar"
                    onClientUploadComplete={async (res) => {
                      if (res && res.length > 0) {
                        await handleAvatarChange(res[0].url)
                      }
                    }}
                    onUploadError={(error: Error) => {
                      addToast(`${t('profile_setup.upload_error') || 'Erreur d\'upload'}: ${error.message}`, 'error')
                    }}
                  />
                </div>
                <button
                  type="button"
                  onClick={async () => await handleAvatarChange('')}
                  className="px-3 py-1 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  {t('settings.remove') || 'Supprimer'}
                </button>
              </div>
            </div>
          ) : (
            <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-6 bg-gray-50 dark:bg-gray-700/50 w-full max-w-xs">
              <UploadButton
                endpoint="profileAvatar"
                onClientUploadComplete={async (res) => {
                  if (res && res.length > 0) {
                    await handleAvatarChange(res[0].url)
                  }
                }}
                onUploadError={(error: Error) => {
                  addToast(`${t('profile_setup.upload_error') || 'Erreur d\'upload'}: ${error.message}`, 'error')
                }}
              />
            </div>
          )}
        </div>
        {errors.avatarUrl && (
          <p className="text-sm text-red-600 dark:text-red-400 mt-2 text-center">
            {errors.avatarUrl}
          </p>
        )}
      </div>

      {/* First Name & Last Name */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            {t('profile_setup.first_name') || 'Prénom'} *
          </label>
          <input
            type="text"
            value={firstName}
            onChange={(e) => handleFieldChange('firstName', e.target.value)}
            placeholder={t('profile_setup.first_name_placeholder') || 'Votre prénom'}
            disabled={isLoading}
            className={`w-full px-4 py-3 border rounded-xl bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 transition-all ${errors.firstName
                ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500'
                : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
              }`}
          />
          {errors.firstName && (
            <p className="text-sm text-red-600 dark:text-red-400 mt-1">
              {errors.firstName}
            </p>
          )}
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            {t('profile_setup.last_name') || 'Nom'} *
          </label>
          <input
            type="text"
            value={lastName}
            onChange={(e) => handleFieldChange('lastName', e.target.value)}
            placeholder={t('profile_setup.last_name_placeholder') || 'Votre nom'}
            disabled={isLoading}
            className={`w-full px-4 py-3 border rounded-xl bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 transition-all ${errors.lastName
                ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500'
                : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
              }`}
          />
          {errors.lastName && (
            <p className="text-sm text-red-600 dark:text-red-400 mt-1">
              {errors.lastName}
            </p>
          )}
        </div>
      </div>

      {/* Bio */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2">
          <FileText className="w-4 h-4" />
          {t('profile_setup.bio') || 'Bio'} *
        </label>
        <textarea
          value={bio}
          onChange={(e) => handleFieldChange('bio', e.target.value)}
          placeholder={t('profile_setup.bio_placeholder') || 'Parlez un peu de vous...'}
          maxLength={500}
          rows={4}
          disabled={isLoading}
          className={`w-full px-4 py-3 border rounded-xl bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 resize-none transition-all ${errors.bio
              ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500'
              : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
            }`}
        />
        <div className="flex items-center justify-between mt-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {bio.length}/500 {t('profile_setup.characters') || 'caractères'}
          </p>
          {errors.bio && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {errors.bio}
            </p>
          )}
        </div>
      </div>

      {/* City */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2">
          <MapPin className="w-4 h-4" />
          {t('settings.city') || 'Ville'} *
        </label>
        <select
          value={city}
          onChange={(e) => handleFieldChange('city', e.target.value)}
          disabled={isLoading}
          className={`w-full px-4 py-3 border rounded-xl bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 transition-all ${errors.city
              ? 'border-red-500 dark:border-red-500 focus:ring-red-500 focus:border-red-500'
              : 'border-gray-300 dark:border-gray-600 focus:ring-myhigh5-primary focus:border-transparent'
            }`}
        >
          <option value="">{t('participation.select_city') || 'S\u00e9lectionnez une ville'}</option>
          {availableCities.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        {errors.city && (
          <p className="text-sm text-red-600 dark:text-red-400 mt-1">
            {errors.city}
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
