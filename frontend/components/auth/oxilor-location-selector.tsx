'use client'

import { useState, useEffect, useCallback } from 'react'
import { MapPin, Globe, Loader2 } from 'lucide-react'
import {
  getCountriesFromOxilor,
  getCitiesFromOxilor,
  getContinentsFromOxilor,
  getCountriesByContinent,
  type OxilorCountry,
  type OxilorCity,
} from '@/lib/oxilor-geography'
import { COUNTRIES_DATA } from '@/lib/countries-data'

interface OxilorLocationSelectorProps {
  onCountryChange: (country: string) => void
  onCityChange: (city: string) => void
  onRegionChange: (region: string) => void
  onContinentChange: (continent: string) => void
  selectedCountry?: string
  selectedCity?: string
}

export function OxilorLocationSelector({
  onCountryChange,
  onCityChange,
  onRegionChange,
  onContinentChange,
  selectedCountry = '',
  selectedCity = '',
}: OxilorLocationSelectorProps) {
  const [continents, setContinents] = useState<string[]>([])
  const [selectedContinent, setSelectedContinent] = useState('')
  const [countries, setCountries] = useState<OxilorCountry[]>([])
  const [selectedCountryCode, setSelectedCountryCode] = useState('')
  const [cities, setCities] = useState<OxilorCity[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Charger les continents au montage
  useEffect(() => {
    const loadContinents = async () => {
      setLoading(true)
      setError('')
      try {
        const data = await getContinentsFromOxilor()
        console.log('Continents chargés depuis Oxilor:', data)
        
        if (data && data.length > 0) {
          setContinents(data)
        } else {
          // Fallback aux données statiques
          console.log('Fallback aux données statiques')
          const staticContinents = Array.from(new Set(COUNTRIES_DATA.map(c => c.continent)))
          setContinents(staticContinents)
        }
      } catch (err) {
        console.error('Erreur continents:', err)
        // Fallback aux données statiques en cas d'erreur
        const staticContinents = Array.from(new Set(COUNTRIES_DATA.map(c => c.continent)))
        setContinents(staticContinents)
      } finally {
        setLoading(false)
      }
    }
    loadContinents()
  }, [])

  // Charger les pays quand le continent change
  useEffect(() => {
    if (selectedContinent) {
      setLoading(true)
      setError('')
      const loadCountries = async () => {
        try {
          const data = await getCountriesByContinent(selectedContinent)
          console.log(`Pays pour ${selectedContinent}:`, data)
          
          if (data && data.length > 0) {
            setCountries(data)
          } else {
            // Fallback aux données statiques
            console.log('Fallback aux données statiques pour les pays')
            const staticCountries = COUNTRIES_DATA
              .filter(c => c.continent === selectedContinent)
              .map(c => ({
                id: c.code,
                name: c.name,
                code: c.code,
                continent: c.continent,
                region: c.region,
              }))
            setCountries(staticCountries)
          }
          
          setSelectedCountryCode('')
          setCities([])
          console.log('Appel onContinentChange avec:', selectedContinent)
          onContinentChange(selectedContinent)
        } catch (err) {
          console.error('Erreur pays:', err)
          // Fallback aux données statiques en cas d'erreur
          const staticCountries = COUNTRIES_DATA
            .filter(c => c.continent === selectedContinent)
            .map(c => ({
              id: c.code,
              name: c.name,
              code: c.code,
              continent: c.continent,
              region: c.region,
            }))
          setCountries(staticCountries)
          onContinentChange(selectedContinent)
        } finally {
          setLoading(false)
        }
      }
      loadCountries()
    }
  }, [selectedContinent, onContinentChange]) // Inclure onContinentChange

  // Charger les villes quand le pays change
  useEffect(() => {
    if (selectedCountryCode && countries.length > 0) {
      setLoading(true)
      setError('')
      const loadCities = async () => {
        try {
          const country = countries.find(c => c.code === selectedCountryCode)
          if (country) {
            console.log('Pays trouvé:', country)
            console.log('Appel onCountryChange avec:', country.name)
            console.log('Appel onRegionChange avec:', country.region || '')
            
            onCountryChange(country.name)
            onRegionChange(country.region || '')

            const data = await getCitiesFromOxilor(selectedCountryCode)
            console.log(`Villes pour ${selectedCountryCode}:`, data)
            setCities(data)
          }
        } catch (err) {
          console.error('Erreur villes:', err)
          setError('Erreur lors du chargement des villes')
        } finally {
          setLoading(false)
        }
      }
      loadCities()
    }
  }, [selectedCountryCode, countries, onCountryChange, onRegionChange]) // Inclure les callbacks pour s'assurer qu'ils sont appelés

  return (
    <div className="space-y-4">
      {/* Error Message */}
      {error && (
        <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Continent Selection */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
          <Globe className="inline mr-2 h-4 w-4" />
          Continent *
        </label>
        <select
          value={selectedContinent}
          onChange={(e) => setSelectedContinent(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary disabled:opacity-50"
          disabled={loading || continents.length === 0}
          required
        >
          <option value="">
            {loading ? 'Chargement...' : 'Sélectionner un continent'}
          </option>
          {continents.map((continent) => (
            <option key={continent} value={continent}>
              {continent}
            </option>
          ))}
        </select>
      </div>

      {/* Country Selection */}
      {selectedContinent && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <Globe className="inline mr-2 h-4 w-4" />
            Pays * ({countries.length} pays)
          </label>
          <select
            value={selectedCountryCode}
            onChange={(e) => {
              console.log('Sélection pays:', e.target.value)
              setSelectedCountryCode(e.target.value)
            }}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary disabled:opacity-50"
            disabled={loading || countries.length === 0}
            required
          >
            <option value="">
              {loading ? 'Chargement...' : countries.length === 0 ? 'Aucun pays trouvé' : 'Sélectionner un pays'}
            </option>
            {countries.map((country) => (
              <option key={country.code} value={country.code}>
                {country.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* City Selection */}
      {selectedCountryCode && cities.length > 0 && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <MapPin className="inline mr-2 h-4 w-4" />
            Ville * ({cities.length} villes)
          </label>
          <select
            value={selectedCity}
            onChange={(e) => {
              console.log('Sélection ville:', e.target.value)
              onCityChange(e.target.value)
            }}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            required
          >
            <option value="">Sélectionner une ville</option>
            {cities.map((city) => (
              <option key={city.id || city.name} value={city.name}>
                {city.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Manual City Input if no cities available */}
      {selectedCountryCode && cities.length === 0 && !loading && (
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
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            required
          />
        </div>
      )}

      {/* Loading Indicator */}
      {loading && (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="h-5 w-5 animate-spin text-myhigh5-primary" />
          <span className="ml-2 text-sm text-gray-600 dark:text-gray-400">Chargement...</span>
        </div>
      )}
    </div>
  )
}
