'use client'

import { useState, useMemo } from 'react'
import { MapPin, Globe } from 'lucide-react'
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
  const [cities, setCities] = useState<string[]>([])

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
      
      // Charger les villes (pour maintenant, tableau vide)
      const cityList: string[] = []
      setCities(cityList)
      console.log('Villes chargées:', cityList.length)
      
      // Réinitialiser la ville
      onCityChange('')
    }
  }

  // Quand la ville change
  const handleCityChange = (city: string) => {
    console.log('Ville sélectionnée:', city)
    onCityChange(city)
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

      {/* City Selection */}
      {selectedCountryCode && cities.length > 0 && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <MapPin className="inline mr-2 h-4 w-4" />
            {t('auth.register.city')} *
          </label>
          <select
            value={selectedCity}
            onChange={(e) => handleCityChange(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            required
          >
            <option value="">{t('auth.register.city_placeholder')}</option>
            {cities.map((city) => (
              <option key={city} value={city}>
                {city}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Manual City Input if no cities available */}
      {selectedCountryCode && cities.length === 0 && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <MapPin className="inline mr-2 h-4 w-4" />
            {t('auth.register.city')} *
          </label>
          <input
            type="text"
            value={selectedCity}
            onChange={(e) => handleCityChange(e.target.value)}
            placeholder={t('auth.register.city_placeholder')}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            required
          />
        </div>
      )}
    </div>
  )
}
