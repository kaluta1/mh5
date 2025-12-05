'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { SimpleLocationSelector } from '@/components/auth/simple-location-selector'
import { MapPin, AlertCircle } from 'lucide-react'

interface SettingsLocationTabProps {
  user: any
}

export function SettingsLocationTab({ user }: SettingsLocationTabProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [continent, setContinent] = useState('')
  const [region, setRegion] = useState('')
  const [country, setCountry] = useState('')
  const [city, setCity] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hasParticipation, setHasParticipation] = useState(false)
  const [isCheckingParticipation, setIsCheckingParticipation] = useState(true)

  // Charger les données de l'utilisateur et vérifier la participation
  useEffect(() => {
    if (user) {
      setContinent(user.continent || '')
      setRegion(user.region || '')
      setCountry(user.country || '')
      setCity(user.city || '')
      checkUserParticipation()
    }
  }, [user])

  const checkUserParticipation = async () => {
    try {
      setIsCheckingParticipation(true)
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      if (!token) {
        setIsCheckingParticipation(false)
        return
      }

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/v1/contestants/user`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setHasParticipation(Array.isArray(data) && data.length > 0)
      }
    } catch (err) {
      console.error('Erreur lors de la vérification de la participation:', err)
    } finally {
      setIsCheckingParticipation(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!city) {
      addToast(t('profile_setup.city_required') || 'La ville est requise', 'error')
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

      addToast(t('profile_setup.success') || 'Localisation mise à jour avec succès!', 'success')
    } catch (err: any) {
      console.error('Erreur:', err)
      addToast(err.message || 'Erreur lors de la mise à jour de la localisation', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  if (isCheckingParticipation) {
    return <div className="text-white">{t('common.loading') || 'Chargement...'}</div>
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

      {/* Main Content with Layout */}
      <div className={`grid gap-6 ${hasLocationInfo ? 'md:grid-cols-2' : 'md:grid-cols-1'}`}>
        {/* Location Section - Left/Top */}
        <div>
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <MapPin className="w-5 h-5" />
            {t('profile_setup.location') || 'Localisation'} *
          </h3>
          
          {hasParticipation ? (
            // Display read-only location info if user has participation
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('settings.continent') || 'Continent'}
                </label>
                <div className="w-full px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 text-gray-400">
                  {continent || '-'}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('settings.region') || 'Région'}
                </label>
                <div className="w-full px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 text-gray-400">
                  {region || '-'}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('settings.country') || 'Pays'}
                </label>
                <div className="w-full px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 text-gray-400">
                  {country || '-'}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('settings.city') || 'Ville'}
                </label>
                <div className="w-full px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 text-gray-400">
                  {city || '-'}
                </div>
              </div>
            </div>
          ) : (
            // Use SimpleLocationSelector if no participation
            <SimpleLocationSelector
              onCountryChange={setCountry}
              onCityChange={setCity}
              onRegionChange={setRegion}
              onContinentChange={setContinent}
              selectedCountry={country}
              selectedCity={city}
            />
          )}
        </div>

        {/* Current Location Info - Right/Bottom (only if info exists) */}
        {hasLocationInfo && (
          <div className="bg-gray-700/50 rounded-lg p-6 border border-gray-600">
            <h4 className="text-lg font-semibold text-white mb-4">
              {t('settings.current_location') || 'Localisation actuelle'}
            </h4>
            <div className="space-y-3">
              <div>
                <p className="text-sm text-gray-400 mb-1">
                  {t('settings.continent') || 'Continent'}
                </p>
                <p className="text-white font-medium">{continent}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400 mb-1">
                  {t('settings.region') || 'Région'}
                </p>
                <p className="text-white font-medium">{region}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400 mb-1">
                  {t('settings.country') || 'Pays'}
                </p>
                <p className="text-white font-medium">{country}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400 mb-1">
                  {t('settings.city') || 'Ville'}
                </p>
                <p className="text-white font-medium">{city}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
