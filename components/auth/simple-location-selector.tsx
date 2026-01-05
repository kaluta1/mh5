'use client'

import { useState, useEffect } from 'react'
import { MapPin, Globe } from 'lucide-react'
import { getCountries, getCountryByCode, getCitiesByCountryCode } from '@/lib/countries-data'
import { useLanguage } from '@/contexts/language-context'

interface SimpleLocationSelectorProps {
  onCountryChange: (country: string) => void
  onCityChange: (city: string) => void
  onRegionChange: (region: string) => void
  onContinentChange: (continent: string) => void
  selectedCountry?: string
  selectedCity?: string
}

export function SimpleLocationSelector({
  onCountryChange,
  onCityChange,
  onRegionChange,
  onContinentChange,
  selectedCountry = '',
  selectedCity = '',
}: SimpleLocationSelectorProps) {
  const { t } = useLanguage()
  const countries = getCountries()
  
  // Trouver le code du pays sélectionné par son nom
  const findCountryCodeByName = (countryName: string): string => {
    if (!countryName) return ''
    const country = countries.find(c => c.name === countryName)
    return country?.code || ''
  }
  
  const [selectedCountryCode, setSelectedCountryCode] = useState(findCountryCodeByName(selectedCountry))
  const [city, setCity] = useState(selectedCity)
  
  // Mettre à jour le code du pays si selectedCountry change
  useEffect(() => {
    const code = findCountryCodeByName(selectedCountry)
    if (code && code !== selectedCountryCode) {
      setSelectedCountryCode(code)
    }
  }, [selectedCountry, selectedCountryCode])

  const handleCountryChange = (code: string) => {
    setSelectedCountryCode(code)
    
    if (code) {
      const country = getCountryByCode(code)
      if (country) {
        // Mettre à jour pays, région et continent
        onCountryChange(country.name)
        onRegionChange(country.region)
        onContinentChange(country.continent)
        
        // Réinitialiser la ville
        setCity('')
        onCityChange('')
      }
    } else {
      onCityChange('')
    }
  }

  const handleCityChange = (value: string) => {
    setCity(value)
    onCityChange(value)
  }

  return (
    <div className="space-y-4">
      {/* Country Selection */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
          <Globe className="inline mr-2 h-4 w-4" />
          {t('auth.register.country') || 'Pays'} *
        </label>
        <select
          value={selectedCountryCode}
          onChange={(e) => handleCountryChange(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
          required
        >
          <option value="">{t('auth.register.country_placeholder') || 'Sélectionner un pays'}</option>
          {countries.map((country) => (
            <option key={country.code} value={country.code}>
              {country.name}
            </option>
          ))}
        </select>
      </div>

      {/* City Input */}
      {selectedCountryCode && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <MapPin className="inline mr-2 h-4 w-4" />
            {t('auth.register.city') || 'Ville'} *
          </label>
          <input
            type="text"
            value={city}
            onChange={(e) => handleCityChange(e.target.value)}
            placeholder={t('auth.register.city_placeholder') || 'Entrez votre ville'}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            required
          />
        </div>
      )}
    </div>
  )
}
