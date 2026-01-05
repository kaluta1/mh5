'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { SimpleLocationSelector } from '@/components/auth/simple-location-selector'
import { MapPin, AlertCircle } from 'lucide-react'

interface SettingsLocationTabProps {
  user: any
  onUpdate?: () => Promise<void>
}

export function SettingsLocationTab({ user, onUpdate }: SettingsLocationTabProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [continent, setContinent] = useState('')
  const [region, setRegion] = useState('')
  const [country, setCountry] = useState('')
  const [city, setCity] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hasParticipation, setHasParticipation] = useState(false)
  const [isCheckingParticipation, setIsCheckingParticipation] = useState(true)
  const [errors, setErrors] = useState<{
    continent?: string
    region?: string
    country?: string
    city?: string
  }>({})

  // Charger les données de l'utilisateur et vérifier la participation
  useEffect(() => {
    if (user) {
      setContinent(user.continent || '')
      setRegion(user.region || '')
      setCountry(user.country || '')
      setCity(user.city || '')
      checkUserParticipation()
    }
  }, [user, t])

  // Valider et afficher les erreurs par défaut après vérification de participation
  useEffect(() => {
    if (!isCheckingParticipation && !hasParticipation) {
      // Valider directement avec les valeurs actuelles des états
      const newErrors: typeof errors = {}
      
      if (!continent.trim()) {
        newErrors.continent = t('profile_setup.continent_required') || 'Le continent est requis'
      }
      
      if (!region.trim()) {
        newErrors.region = t('profile_setup.region_required') || 'La région est requise'
      }
      
      if (!country.trim()) {
        newErrors.country = t('profile_setup.country_required') || 'Le pays est requis'
      }
      
      if (!city.trim()) {
        newErrors.city = t('profile_setup.city_required') || 'La ville est requise'
      }
      
      setErrors(newErrors)
    }
  }, [isCheckingParticipation, hasParticipation, continent, region, country, city, t])

  const checkUserParticipation = async () => {
    try {
      setIsCheckingParticipation(true)
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      if (!token) {
        setIsCheckingParticipation(false)
        return
      }

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/v1/contestants/user/my-entries`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        const hasPart = Array.isArray(data) && data.length > 0
        setHasParticipation(hasPart)
      }
    } catch (err) {
      console.error('Erreur lors de la vérification de la participation:', err)
    } finally {
      setIsCheckingParticipation(false)
    }
  }

  const validateForm = () => {
    const newErrors: typeof errors = {}
    
    if (!continent.trim()) {
      newErrors.continent = t('profile_setup.continent_required') || 'Le continent est requis'
    }
    
    if (!region.trim()) {
      newErrors.region = t('profile_setup.region_required') || 'La région est requise'
    }
    
    if (!country.trim()) {
      newErrors.country = t('profile_setup.country_required') || 'Le pays est requis'
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

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/v1/users/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          continent: continent,
          region: region,
          country: country,
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

      addToast(t('profile_setup.success') || 'Localisation mise à jour avec succès!', 'success')
      setErrors({})
    } catch (err: any) {
      console.error('Erreur:', err)
      addToast(err.message || 'Erreur lors de la mise à jour de la localisation', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleLocationChange = (field: 'continent' | 'region' | 'country' | 'city', value: string) => {
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }
    
    if (field === 'continent') {
      setContinent(value)
    } else if (field === 'region') {
      setRegion(value)
    } else if (field === 'country') {
      setCountry(value)
    } else if (field === 'city') {
      setCity(value)
    }
  }

  if (isCheckingParticipation) {
    return <div className="text-gray-600 dark:text-gray-300">{t('common.loading') || 'Chargement...'}</div>
  }

  // Vérifier si les informations sont remplies
  const hasLocationInfo = continent && region && country && city

  return (
    <div className="space-y-6">
      {/* Alert if user has participation */}
      {hasParticipation && (
        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-blue-900 dark:text-blue-200">
              {t('settings.location_locked_title') || 'Localisation verrouillée'}
            </p>
            <p className="text-sm text-blue-800 dark:text-blue-300">
              {t('settings.location_locked_message') || 'Vous avez déjà participé à un concours. Votre localisation ne peut pas être modifiée.'}
            </p>
          </div>
        </div>
      )}

      {/* Main Content */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {hasParticipation ? (
          // Display read-only location info if user has participation
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">
                {t('settings.continent') || 'Continent'}
              </label>
              <div className="w-full px-4 py-3 rounded-xl bg-gray-100 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300">
                {continent || '-'}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">
                {t('settings.region') || 'Région'}
              </label>
              <div className="w-full px-4 py-3 rounded-xl bg-gray-100 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300">
                {region || '-'}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">
                {t('settings.country') || 'Pays'}
              </label>
              <div className="w-full px-4 py-3 rounded-xl bg-gray-100 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300">
                {country || '-'}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-2">
                {t('settings.city') || 'Ville'}
              </label>
              <div className="w-full px-4 py-3 rounded-xl bg-gray-100 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300">
                {city || '-'}
              </div>
            </div>
          </div>
        ) : (
          // Use SimpleLocationSelector if no participation
          <div className="space-y-4">
            <SimpleLocationSelector
              onCountryChange={(value) => handleLocationChange('country', value)}
              onCityChange={(value) => handleLocationChange('city', value)}
              onRegionChange={(value) => handleLocationChange('region', value)}
              onContinentChange={(value) => handleLocationChange('continent', value)}
              selectedCountry={country}
              selectedCity={city}
            />
            
            {/* Error Messages */}
            {(errors.continent || errors.region || errors.country || errors.city) && (
              <div className="space-y-2">
                {errors.continent && (
                  <p className="text-sm text-red-600 dark:text-red-400">
                    {errors.continent}
                  </p>
                )}
                {errors.region && (
                  <p className="text-sm text-red-600 dark:text-red-400">
                    {errors.region}
                  </p>
                )}
                {errors.country && (
                  <p className="text-sm text-red-600 dark:text-red-400">
                    {errors.country}
                  </p>
                )}
                {errors.city && (
                  <p className="text-sm text-red-600 dark:text-red-400">
                    {errors.city}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Current Location Summary */}
        {hasLocationInfo && (
          <div className="bg-gradient-to-r from-myhigh5-primary/10 to-transparent rounded-xl p-4 border border-myhigh5-primary/20">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-myhigh5-primary/20 rounded-lg">
                <MapPin className="w-5 h-5 text-myhigh5-primary" />
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">{t('settings.current_location') || 'Localisation actuelle'}</p>
                <p className="text-gray-900 dark:text-white font-medium">
                  {city}, {country} • {region}, {continent}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Submit Button */}
        {!hasParticipation && (
          <div className="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700">
            <Button
              type="submit"
              disabled={isLoading}
              className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white font-bold px-6 py-2.5 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? t('common.submitting') || 'Enregistrement...' : t('settings.save') || 'Enregistrer'}
            </Button>
          </div>
        )}
      </form>
    </div>
  )
}
