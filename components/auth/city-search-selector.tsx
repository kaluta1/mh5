'use client'

import { useState } from 'react'
import { MapPin } from 'lucide-react'
import { searchCities } from '@/lib/oxilor-geography'

interface CitySearchSelectorProps {
  onCitySelect: (city: string) => void
  onCountryChange: (country: string) => void
  onRegionChange: (region: string) => void
  onContinentChange: (continent: string) => void
}

export function CitySearchSelector({
  onCitySelect,
  onCountryChange,
  onRegionChange,
  onContinentChange,
}: CitySearchSelectorProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedCity, setSelectedCity] = useState('')

  const handleSearch = async (value: string) => {
    setSearchTerm(value)
    
    if (value.length < 2) {
      setSuggestions([])
      return
    }

    setLoading(true)
    try {
      const results = await searchCities(value, 'city', 5)
      console.log('Résultats recherche:', results)
      setSuggestions(results)
    } catch (error) {
      console.error('Erreur recherche:', error)
      setSuggestions([])
    } finally {
      setLoading(false)
    }
  }

  const handleSelectCity = (city: any) => {
    setSelectedCity(city.name || city.displayName || '')
    setSearchTerm(city.name || city.displayName || '')
    onCitySelect(city.name || city.displayName || '')
    
    // Mettre à jour les autres champs si disponibles
    if (city.country) onCountryChange(city.country)
    if (city.region) onRegionChange(city.region)
    if (city.continent) onContinentChange(city.continent)
    
    setSuggestions([])
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
          <MapPin className="inline mr-2 h-4 w-4" />
          Chercher votre ville *
        </label>
        <div className="relative">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Entrez le nom de votre ville (ex: Dakar, Paris, Lome...)"
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            required
          />
          
          {/* Suggestions dropdown */}
          {suggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg z-10 max-h-64 overflow-y-auto">
              {suggestions.map((city, index) => (
                <button
                  key={index}
                  onClick={() => handleSelectCity(city)}
                  className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-600 border-b border-gray-200 dark:border-gray-600 last:border-b-0 transition-colors"
                >
                  <div className="font-medium text-gray-900 dark:text-white">
                    {city.name || city.displayName}
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {city.region && `${city.region}, `}
                    {city.country}
                  </div>
                </button>
              ))}
            </div>
          )}
          
          {/* Loading indicator */}
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="animate-spin h-4 w-4 border-2 border-myhigh5-primary border-t-transparent rounded-full" />
            </div>
          )}
        </div>
      </div>

      {/* Selected city display */}
      {selectedCity && (
        <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
          <p className="text-sm text-green-700 dark:text-green-400">
            ✓ Ville sélectionnée: <strong>{selectedCity}</strong>
          </p>
        </div>
      )}
    </div>
  )
}
