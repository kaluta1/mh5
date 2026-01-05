'use client'

import { useState, useEffect } from 'react'
import { ChevronDown, Plus, X } from 'lucide-react'
import { locationService, type LocationData } from '@/services/location-service'
import { useToast } from '@/components/ui/toast'

interface LocationSelectorWithCreateProps {
  onContinentSelected: (id: number, name: string) => void
  onRegionSelected: (id: number, name: string) => void
  onCountrySelected: (id: number, name: string) => void
  onCitySelected: (id: number, name: string) => void
  isLoading?: boolean
}

export function LocationSelectorWithCreate({
  onContinentSelected,
  onRegionSelected,
  onCountrySelected,
  onCitySelected,
  isLoading,
}: LocationSelectorWithCreateProps) {
  const { addToast } = useToast()

  const [continents, setContinents] = useState<LocationData[]>([])
  const [regions, setRegions] = useState<LocationData[]>([])
  const [countries, setCountries] = useState<LocationData[]>([])
  const [cities, setCities] = useState<LocationData[]>([])

  const [selectedContinent, setSelectedContinent] = useState<number | ''>('')
  const [selectedRegion, setSelectedRegion] = useState<number | ''>('')
  const [selectedCountry, setSelectedCountry] = useState<number | ''>('')
  const [selectedCity, setSelectedCity] = useState<number | ''>('')

  const [continentInput, setContinentInput] = useState('')
  const [regionInput, setRegionInput] = useState('')
  const [countryInput, setCountryInput] = useState('')
  const [cityInput, setCityInput] = useState('')

  const [showContinentDropdown, setShowContinentDropdown] = useState(false)
  const [showRegionDropdown, setShowRegionDropdown] = useState(false)
  const [showCountryDropdown, setShowCountryDropdown] = useState(false)
  const [showCityDropdown, setShowCityDropdown] = useState(false)

  const [isLoadingData, setIsLoadingData] = useState(false)

  // Load continents on mount
  useEffect(() => {
    loadContinents()
  }, [])

  // Load regions when continent selected
  useEffect(() => {
    if (selectedContinent) {
      loadRegions(Number(selectedContinent))
      setSelectedRegion('')
      setSelectedCountry('')
      setSelectedCity('')
    }
  }, [selectedContinent])

  // Load countries when region selected
  useEffect(() => {
    if (selectedRegion) {
      loadCountries(Number(selectedRegion))
      setSelectedCountry('')
      setSelectedCity('')
    }
  }, [selectedRegion])

  // Load cities when country selected
  useEffect(() => {
    if (selectedCountry) {
      loadCities(Number(selectedCountry))
      setSelectedCity('')
    }
  }, [selectedCountry])

  const loadContinents = async () => {
    try {
      setIsLoadingData(true)
      const data = await locationService.getContinents()
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
      const data = await locationService.getRegionsByContinent(continentId)
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
      const data = await locationService.getCountriesByRegion(regionId)
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
      const data = await locationService.getCitiesByCountry(countryId)
      setCities(data)
    } catch (err) {
      addToast('Erreur lors du chargement des villes', 'error')
    } finally {
      setIsLoadingData(false)
    }
  }

  const handleContinentSelect = (continent: LocationData) => {
    setSelectedContinent(continent.id)
    setContinentInput(continent.name)
    setShowContinentDropdown(false)
    onContinentSelected(continent.id, continent.name)
  }

  const handleRegionSelect = (region: LocationData) => {
    setSelectedRegion(region.id)
    setRegionInput(region.name)
    setShowRegionDropdown(false)
    onRegionSelected(region.id, region.name)
  }

  const handleCountrySelect = (country: LocationData) => {
    setSelectedCountry(country.id)
    setCountryInput(country.name)
    setShowCountryDropdown(false)
    onCountrySelected(country.id, country.name)
  }

  const handleCitySelect = (city: LocationData) => {
    setSelectedCity(city.id)
    setCityInput(city.name)
    setShowCityDropdown(false)
    onCitySelected(city.id, city.name)
  }

  const handleCreateContinent = async () => {
    if (!continentInput.trim()) return
    try {
      const newContinent = await locationService.createOrGetContinent(continentInput)
      setContinents([...continents, newContinent])
      handleContinentSelect(newContinent)
    } catch (err) {
      addToast('Erreur lors de la création du continent', 'error')
    }
  }

  const handleCreateRegion = async () => {
    if (!regionInput.trim() || !selectedContinent) return
    try {
      const newRegion = await locationService.createOrGetRegion(regionInput, Number(selectedContinent))
      setRegions([...regions, newRegion])
      handleRegionSelect(newRegion)
    } catch (err) {
      addToast('Erreur lors de la création de la région', 'error')
    }
  }

  const handleCreateCountry = async () => {
    if (!countryInput.trim() || !selectedRegion) return
    try {
      const newCountry = await locationService.createOrGetCountry(countryInput, Number(selectedRegion))
      setCountries([...countries, newCountry])
      handleCountrySelect(newCountry)
    } catch (err) {
      addToast('Erreur lors de la création du pays', 'error')
    }
  }

  const handleCreateCity = async () => {
    if (!cityInput.trim() || !selectedCountry) return
    try {
      const newCity = await locationService.createOrGetCity(cityInput, Number(selectedCountry))
      setCities([...cities, newCity])
      handleCitySelect(newCity)
    } catch (err) {
      addToast('Erreur lors de la création de la ville', 'error')
    }
  }

  const filteredContinents = continents.filter((c) =>
    c.name.toLowerCase().includes(continentInput.toLowerCase())
  )

  const filteredRegions = regions.filter((r) =>
    r.name.toLowerCase().includes(regionInput.toLowerCase())
  )

  const filteredCountries = countries.filter((c) =>
    c.name.toLowerCase().includes(countryInput.toLowerCase())
  )

  const filteredCities = cities.filter((c) =>
    c.name.toLowerCase().includes(cityInput.toLowerCase())
  )

  return (
    <div className="space-y-4">
      {/* Continent */}
      <div className="relative">
        <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
          Continent *
        </label>
        <div className="relative">
          <input
            type="text"
            value={continentInput}
            onChange={(e) => {
              setContinentInput(e.target.value)
              setShowContinentDropdown(true)
            }}
            onFocus={() => setShowContinentDropdown(true)}
            placeholder="Sélectionner ou créer un continent"
            disabled={isLoading || isLoadingData}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
          />
          <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>

        {showContinentDropdown && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg z-10">
            <div className="max-h-48 overflow-y-auto">
              {filteredContinents.length > 0 ? (
                filteredContinents.map((continent) => (
                  <button
                    key={continent.id}
                    onClick={() => handleContinentSelect(continent)}
                    className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-900 dark:text-white"
                  >
                    {continent.name}
                  </button>
                ))
              ) : (
                <div className="px-4 py-2 text-gray-500 dark:text-gray-400">Aucun résultat</div>
              )}
            </div>
            {continentInput.trim() && !filteredContinents.some((c) => c.name.toLowerCase() === continentInput.toLowerCase()) && (
              <button
                onClick={handleCreateContinent}
                className="w-full text-left px-4 py-2 border-t border-gray-300 dark:border-gray-600 text-myhigh5-primary hover:bg-gray-50 dark:hover:bg-gray-600 flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                Créer "{continentInput}"
              </button>
            )}
          </div>
        )}
      </div>

      {/* Region */}
      {selectedContinent && (
        <div className="relative">
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            Région/État *
          </label>
          <div className="relative">
            <input
              type="text"
              value={regionInput}
              onChange={(e) => {
                setRegionInput(e.target.value)
                setShowRegionDropdown(true)
              }}
              onFocus={() => setShowRegionDropdown(true)}
              placeholder="Sélectionner ou créer une région"
              disabled={isLoading || isLoadingData}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            />
            <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>

          {showRegionDropdown && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg z-10">
              <div className="max-h-48 overflow-y-auto">
                {filteredRegions.length > 0 ? (
                  filteredRegions.map((region) => (
                    <button
                      key={region.id}
                      onClick={() => handleRegionSelect(region)}
                      className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-900 dark:text-white"
                    >
                      {region.name}
                    </button>
                  ))
                ) : (
                  <div className="px-4 py-2 text-gray-500 dark:text-gray-400">Aucun résultat</div>
                )}
              </div>
              {regionInput.trim() && !filteredRegions.some((r) => r.name.toLowerCase() === regionInput.toLowerCase()) && (
                <button
                  onClick={handleCreateRegion}
                  className="w-full text-left px-4 py-2 border-t border-gray-300 dark:border-gray-600 text-myhigh5-primary hover:bg-gray-50 dark:hover:bg-gray-600 flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Créer "{regionInput}"
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Country */}
      {selectedRegion && (
        <div className="relative">
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            Pays *
          </label>
          <div className="relative">
            <input
              type="text"
              value={countryInput}
              onChange={(e) => {
                setCountryInput(e.target.value)
                setShowCountryDropdown(true)
              }}
              onFocus={() => setShowCountryDropdown(true)}
              placeholder="Sélectionner ou créer un pays"
              disabled={isLoading || isLoadingData}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            />
            <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>

          {showCountryDropdown && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg z-10">
              <div className="max-h-48 overflow-y-auto">
                {filteredCountries.length > 0 ? (
                  filteredCountries.map((country) => (
                    <button
                      key={country.id}
                      onClick={() => handleCountrySelect(country)}
                      className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-900 dark:text-white"
                    >
                      {country.name}
                    </button>
                  ))
                ) : (
                  <div className="px-4 py-2 text-gray-500 dark:text-gray-400">Aucun résultat</div>
                )}
              </div>
              {countryInput.trim() && !filteredCountries.some((c) => c.name.toLowerCase() === countryInput.toLowerCase()) && (
                <button
                  onClick={handleCreateCountry}
                  className="w-full text-left px-4 py-2 border-t border-gray-300 dark:border-gray-600 text-myhigh5-primary hover:bg-gray-50 dark:hover:bg-gray-600 flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Créer "{countryInput}"
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* City */}
      {selectedCountry && (
        <div className="relative">
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            Ville *
          </label>
          <div className="relative">
            <input
              type="text"
              value={cityInput}
              onChange={(e) => {
                setCityInput(e.target.value)
                setShowCityDropdown(true)
              }}
              onFocus={() => setShowCityDropdown(true)}
              placeholder="Sélectionner ou créer une ville"
              disabled={isLoading || isLoadingData}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
            />
            <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>

          {showCityDropdown && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg z-10">
              <div className="max-h-48 overflow-y-auto">
                {filteredCities.length > 0 ? (
                  filteredCities.map((city) => (
                    <button
                      key={city.id}
                      onClick={() => handleCitySelect(city)}
                      className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-900 dark:text-white"
                    >
                      {city.name}
                    </button>
                  ))
                ) : (
                  <div className="px-4 py-2 text-gray-500 dark:text-gray-400">Aucun résultat</div>
                )}
              </div>
              {cityInput.trim() && !filteredCities.some((c) => c.name.toLowerCase() === cityInput.toLowerCase()) && (
                <button
                  onClick={handleCreateCity}
                  className="w-full text-left px-4 py-2 border-t border-gray-300 dark:border-gray-600 text-myhigh5-primary hover:bg-gray-50 dark:hover:bg-gray-600 flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Créer "{cityInput}"
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
