'use client'

import { useState, useEffect } from 'react'
import { MapPin, Globe } from 'lucide-react'
import { getAllCountries, getCitiesByCountry, type Country } from '@/lib/geography'

interface LocationSelectorProps {
  onCountryChange: (country: string) => void
  onCityChange: (city: string) => void
  onRegionChange: (region: string) => void
  onContinentChange: (continent: string) => void
  selectedCountry?: string
  selectedCity?: string
}

export function LocationSelector({
  onCountryChange,
  onCityChange,
  onRegionChange,
  onContinentChange,
  selectedCountry = '',
  selectedCity = '',
}: LocationSelectorProps) {
  const [countries, setCountries] = useState<Country[]>([])
  const [selectedCountryCode, setSelectedCountryCode] = useState('')
  const [cities, setCities] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Charger tous les pays au montage
  useEffect(() => {
    const loadCountries = async () => {
      setLoading(true)
      setError('')
      try {
        const data = await getAllCountries()
        console.log('Pays chargés:', data.length)
        if (data.length === 0) {
          setError('Impossible de charger les pays. Vérifiez votre connexion.')
        }
        setCountries(data)
      } catch (err) {
        console.error('Erreur lors du chargement des pays:', err)
        setError('Erreur lors du chargement des pays')
      } finally {
        setLoading(false)
      }
    }
    loadCountries()
  }, [])

  // Charger les villes quand le pays change
  useEffect(() => {
    if (selectedCountryCode && countries.length > 0) {
      const country = countries.find(c => c.code === selectedCountryCode)
      if (country) {
        console.log('Pays sélectionné:', country)
        // Mettre à jour le pays, région et continent
        onCountryChange(country.name)
        onRegionChange(country.subregion || country.region || '')
        onContinentChange(country.continent)

        // Charger les villes
        const loadCities = async () => {
          const cityList = await getCitiesByCountry(selectedCountryCode)
          console.log('Villes chargées:', cityList)
          setCities(cityList)
        }
        loadCities()
      }
    }
  }, [selectedCountryCode, countries, onCountryChange, onRegionChange, onContinentChange])

  return (
    <div className="space-y-4">
      {/* Error Message */}
      {error && (
        <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Country Selection */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
          <Globe className="inline mr-2 h-4 w-4" />
          Pays *
        </label>
        <select
          value={selectedCountryCode}
          onChange={(e) => {
            const code = e.target.value
            console.log('Changement de pays:', code)
            setSelectedCountryCode(code)
            setCities([])
          }}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary disabled:opacity-50"
          disabled={loading || countries.length === 0}
          required
        >
          <option value="">
            {loading ? 'Chargement des pays...' : countries.length === 0 ? 'Erreur de chargement' : 'Sélectionner un pays'}
          </option>
          {countries.map((country) => (
            <option key={country.code} value={country.code}>
              {country.name}
            </option>
          ))}
        </select>
        {countries.length > 0 && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {countries.length} pays disponibles
          </p>
        )}
      </div>

      {/* City Selection */}
      {selectedCountryCode && cities.length > 0 && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <MapPin className="inline mr-2 h-4 w-4" />
            Ville *
          </label>
          <select
            value={selectedCity}
            onChange={(e) => onCityChange(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          >
            <option value="">Sélectionner une ville</option>
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
            Ville *
          </label>
          <input
            type="text"
            value={selectedCity}
            onChange={(e) => onCityChange(e.target.value)}
            placeholder="Entrez votre ville"
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          />
        </div>
      )}
    </div>
  )
}
