'use client'

import { useState } from 'react'
import { MapPin, Globe } from 'lucide-react'
import { getCountries, getCountryByCode, getCitiesByCountryCode } from '@/lib/countries-data'

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
  const [selectedCountryCode, setSelectedCountryCode] = useState('')
  const [city, setCity] = useState(selectedCity)
  const countries = getCountries()

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
          Pays *
        </label>
        <select
          value={selectedCountryCode}
          onChange={(e) => handleCountryChange(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
          required
        >
          <option value="">Sélectionner un pays</option>
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
            Ville *
          </label>
          <input
            type="text"
            value={city}
            onChange={(e) => handleCityChange(e.target.value)}
            placeholder="Entrez votre ville"
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          />
        </div>
      )}
    </div>
  )
}
