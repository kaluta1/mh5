/**
 * Service géographique utilisant les données JSON
 */

import geographyData from './geography-data.json'

export interface Country {
  id: string
  name: string
  code: string
  continent: string
  region: string
}

export interface GeographyData {
  continents: string[]
  countries: Country[]
  regions: any[]
  cities: any[]
}

// Charger les données
const data: GeographyData = geographyData

/**
 * Obtenir tous les continents
 */
export function getContinents(): string[] {
  return data.continents.sort()
}

/**
 * Obtenir tous les pays
 */
export function getCountries(): Country[] {
  return data.countries.sort((a, b) => a.name.localeCompare(b.name))
}

/**
 * Obtenir les pays d'un continent
 */
export function getCountriesByContinent(continent: string): Country[] {
  return data.countries
    .filter(c => c.continent === continent)
    .sort((a, b) => a.name.localeCompare(b.name))
}

/**
 * Obtenir un pays par code
 */
export function getCountryByCode(code: string): Country | undefined {
  return data.countries.find(c => c.code === code)
}

/**
 * Obtenir les villes d'un pays
 */
export function getCitiesByCountry(countryCode: string): string[] {
  const country = getCountryByCode(countryCode)
  if (!country) return []
  
  // Pour maintenant, retourner un tableau vide
  // À remplir avec les données de l'API Oxilor
  return []
}

/**
 * Rechercher des lieux
 */
export function searchLocations(searchTerm: string): any[] {
  const term = searchTerm.toLowerCase()
  
  const results = [
    ...data.countries
      .filter(c => c.name.toLowerCase().includes(term))
      .map(c => ({
        type: 'country',
        id: c.code,
        name: c.name,
        country: c.name,
        region: c.region,
        continent: c.continent,
      })),
  ]
  
  return results.slice(0, 10)
}

console.log('Service géographique chargé avec', data.countries.length, 'pays')
