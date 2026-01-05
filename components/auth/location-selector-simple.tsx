'use client'

import { useState, useMemo } from 'react'
import { Globe } from 'lucide-react'
import geographyData from '@/lib/geography-data-complete.json'
import { useLanguage } from '@/contexts/language-context'

interface LocationSelectorSimpleProps {
  onCountryChange: (country: string) => void
  onCityChange: (city: string) => void
  onRegionChange: (region: string) => void
  onContinentChange: (continent: string) => void
  selectedCountry?: string
  selectedCity?: string
}

export function LocationSelectorSimple({
  onCountryChange,
  onCityChange,
  onRegionChange,
  onContinentChange,
  selectedCountry = '',
  selectedCity = '',
}: LocationSelectorSimpleProps) {
  const { t } = useLanguage()
  
  // Charger tous les pays depuis le JSON
  const allCountries = useMemo(() => 
    geographyData.countries.sort((a, b) => a.name.localeCompare(b.name)), 
    []
  )
  
  const [selectedCountryCode, setSelectedCountryCode] = useState('')

  // Quand le pays change
  const handleCountryChange = (countryCode: string) => {
    console.log('Pays sélectionné:', countryCode)
    setSelectedCountryCode(countryCode)
    
    const country = allCountries.find(c => c.code === countryCode)
    if (country) {
      console.log('Pays trouvé:', country)
      
      // Appeler les callbacks immédiatement
      console.log('Appel onCountryChange avec:', country.name)
      onCountryChange(country.name)
      
      console.log('Appel onRegionChange avec:', country.region)
      onRegionChange(country.region)
      
      console.log('Appel onContinentChange avec:', country.continent)
      onContinentChange(country.continent)
      
      // Réinitialiser la ville (callback vide si non utilisé)
      onCityChange('')
    }
  }

  return (
    <div className="space-y-4">
      {/* Country Selection */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
          <Globe className="inline mr-2 h-4 w-4" />
          {t('auth.register.country')} *
        </label>
        <select
          value={selectedCountryCode}
          onChange={(e) => handleCountryChange(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
          required
        >
          <option value="">{t('auth.register.country_placeholder')}</option>
          {allCountries.map((country) => (
            <option key={country.code} value={country.code}>
              {country.name}
            </option>
          ))}
        </select>
      </div>

    </div>
  )
}
