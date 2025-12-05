'use client'

import { useState, useEffect } from 'react'
import { geographyService, type Continent, type Region, type Country, type City } from '@/services/geography-service'
import { useToast } from '@/components/ui/toast'

interface LocationSelectorProps {
  onLocationSelected: (cityId: number) => void
  isLoading?: boolean
}

export function LocationSelector({ onLocationSelected, isLoading }: LocationSelectorProps) {
  const { addToast } = useToast()
  const [continents, setContinents] = useState<Continent[]>([])
  const [regions, setRegions] = useState<Region[]>([])
  const [countries, setCountries] = useState<Country[]>([])
  const [cities, setCities] = useState<City[]>([])

  const [selectedContinent, setSelectedContinent] = useState<number | ''>('')
  const [selectedRegion, setSelectedRegion] = useState<number | ''>('')
  const [selectedCountry, setSelectedCountry] = useState<number | ''>('')
  const [selectedCity, setSelectedCity] = useState<number | ''>('')

  const [isLoadingData, setIsLoadingData] = useState(false)

  // Charger les continents au montage
  useEffect(() => {
    loadContinents()
  }, [])

  // Charger les régions quand un continent est sélectionné
  useEffect(() => {
    if (selectedContinent) {
      loadRegions(Number(selectedContinent))
      setSelectedRegion('')
      setSelectedCountry('')
      setSelectedCity('')
    }
  }, [selectedContinent])

  // Charger les pays quand une région est sélectionnée
  useEffect(() => {
    if (selectedRegion) {
      loadCountries(Number(selectedRegion))
      setSelectedCountry('')
      setSelectedCity('')
    }
  }, [selectedRegion])

  // Charger les villes quand un pays est sélectionné
  useEffect(() => {
    if (selectedCountry) {
      loadCities(Number(selectedCountry))
      setSelectedCity('')
    }
  }, [selectedCountry])

  // Notifier le parent quand une ville est sélectionnée
  useEffect(() => {
    if (selectedCity) {
      onLocationSelected(Number(selectedCity))
    }
  }, [selectedCity, onLocationSelected])

  const loadContinents = async () => {
    try {
      setIsLoadingData(true)
      const data = await geographyService.getContinents()
      setContinents(data)
    } catch (err) {
      addToast('Erreur lors du chargement des continents', 'error')
    } finally {
      setIsLoadingData(false)
    }
  }

  const loadRegions = async (continentId: number) => {
    try {
      setIsLoadingData(true)
      const data = await geographyService.getRegionsByContinent(continentId)
      setRegions(data)
    } catch (err) {
      addToast('Erreur lors du chargement des régions', 'error')
    } finally {
      setIsLoadingData(false)
    }
  }

  const loadCountries = async (regionId: number) => {
    try {
      setIsLoadingData(true)
      const data = await geographyService.getCountriesByRegion(regionId)
      setCountries(data)
    } catch (err) {
      addToast('Erreur lors du chargement des pays', 'error')
    } finally {
      setIsLoadingData(false)
    }
  }

  const loadCities = async (countryId: number) => {
    try {
      setIsLoadingData(true)
      const data = await geographyService.getCitiesByCountry(countryId)
      setCities(data)
    } catch (err) {
      addToast('Erreur lors du chargement des villes', 'error')
    } finally {
      setIsLoadingData(false)
    }
  }


  return (
    <div className="space-y-4">
      {/* Continent */}
      <div>
        <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
          Continent *
        </label>
        <select
          value={selectedContinent}
          onChange={(e) => setSelectedContinent(e.target.value ? Number(e.target.value) : '')}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
          disabled={isLoading || isLoadingData}
        >
          <option value="">Sélectionner un continent</option>
          {continents.map((continent) => (
            <option key={continent.id} value={continent.id}>
              {continent.name}
            </option>
          ))}
        </select>
      </div>

      {/* Region */}
      {selectedContinent && (
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            Région/État *
          </label>
          <select
            value={selectedRegion}
            onChange={(e) => setSelectedRegion(e.target.value ? Number(e.target.value) : '')}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            disabled={isLoading || isLoadingData}
          >
            <option value="">Sélectionner une région</option>
            {regions.map((region) => (
              <option key={region.id} value={region.id}>
                {region.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Country */}
      {selectedRegion && (
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            Pays *
          </label>
          <select
            value={selectedCountry}
            onChange={(e) => setSelectedCountry(e.target.value ? Number(e.target.value) : '')}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            disabled={isLoading || isLoadingData}
          >
            <option value="">Sélectionner un pays</option>
            {countries.map((country) => (
              <option key={country.id} value={country.id}>
                {country.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* City */}
      {selectedCountry && (
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            Ville *
          </label>
          <select
            value={selectedCity}
            onChange={(e) => setSelectedCity(e.target.value ? Number(e.target.value) : '')}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            disabled={isLoading || isLoadingData}
          >
            <option value="">Sélectionner une ville</option>
            {cities.map((city) => (
              <option key={city.id} value={city.id}>
                {city.name}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}
