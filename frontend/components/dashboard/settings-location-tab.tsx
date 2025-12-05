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

      {/* Main Content */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {hasParticipation ? (
          // Display read-only location info if user has participation
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t('settings.continent') || 'Continent'}
              </label>
              <div className="w-full px-4 py-3 rounded-lg bg-gray-700/50 border border-gray-600 text-gray-300">
                {continent || '-'}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t('settings.region') || 'Région'}
              </label>
              <div className="w-full px-4 py-3 rounded-lg bg-gray-700/50 border border-gray-600 text-gray-300">
                {region || '-'}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t('settings.country') || 'Pays'}
              </label>
              <div className="w-full px-4 py-3 rounded-lg bg-gray-700/50 border border-gray-600 text-gray-300">
                {country || '-'}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t('settings.city') || 'Ville'}
              </label>
              <div className="w-full px-4 py-3 rounded-lg bg-gray-700/50 border border-gray-600 text-gray-300">
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

        {/* Current Location Summary */}
        {hasLocationInfo && (
          <div className="bg-gradient-to-r from-myfav-primary/10 to-transparent rounded-lg p-4 border border-myfav-primary/20">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-myfav-primary/20 rounded-lg">
                <MapPin className="w-5 h-5 text-myfav-primary" />
              </div>
              <div>
                <p className="text-sm text-gray-400">{t('settings.current_location') || 'Localisation actuelle'}</p>
                <p className="text-white font-medium">
                  {city}, {country} • {region}, {continent}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Submit Button */}
        {!hasParticipation && (
          <div className="flex justify-end gap-3 pt-6 border-t border-gray-700">
            <Button
              type="submit"
              disabled={isLoading || !city}
              className="bg-myfav-primary hover:bg-myfav-primary/90 text-white font-bold"
            >
              {isLoading ? t('common.submitting') || 'Enregistrement...' : t('settings.save') || 'Enregistrer'}
            </Button>
          </div>
        )}
      </form>
    </div>
  )
}
