/**
 * Script pour récupérer les données géographiques depuis l'API backend
 * et les sauvegarder dans un fichier JSON
 * 
 * À exécuter une seule fois pour générer geography-data.json
 */

const BACKEND_URL = 'http://localhost:8000/api/v1/geography'

export interface GeographyData {
  continents: string[]
  countries: CountryData[]
  regions: RegionData[]
  cities: CityData[]
}

export interface CountryData {
  id: string
  name: string
  code: string
  continent: string
  region: string
}

export interface RegionData {
  id: string
  name: string
  continent: string
}

export interface CityData {
  id: string
  name: string
  countryCode: string
  country: string
  region?: string
}

/**
 * Récupérer tous les continents
 */
async function fetchContinents(): Promise<string[]> {
  try {
    const response = await fetch(`${BACKEND_URL}/oxilor/continents`)
    const data = await response.json()
    console.log('Continents récupérés:', data)
    
    if (Array.isArray(data)) {
      return data
    } else if (data.data && Array.isArray(data.data)) {
      return data.data
    }
    return []
  } catch (error) {
    console.error('Erreur continents:', error)
    return []
  }
}

/**
 * Récupérer tous les pays
 */
async function fetchCountries(): Promise<CountryData[]> {
  try {
    const response = await fetch(`${BACKEND_URL}/oxilor/countries`)
    const data = await response.json()
    console.log('Pays récupérés:', data)
    
    if (Array.isArray(data)) {
      return data
    } else if (data.data && Array.isArray(data.data)) {
      return data.data
    }
    return []
  } catch (error) {
    console.error('Erreur pays:', error)
    return []
  }
}

/**
 * Récupérer les villes d'un pays
 */
async function fetchCitiesByCountry(countryCode: string): Promise<CityData[]> {
  try {
    const response = await fetch(`${BACKEND_URL}/oxilor/cities?country_code=${countryCode}`)
    const data = await response.json()
    console.log(`Villes pour ${countryCode}:`, data)
    
    if (Array.isArray(data)) {
      return data
    } else if (data.data && Array.isArray(data.data)) {
      return data.data
    }
    return []
  } catch (error) {
    console.error(`Erreur villes pour ${countryCode}:`, error)
    return []
  }
}

/**
 * Récupérer les régions d'un pays
 */
async function fetchRegionsByCountry(countryCode: string): Promise<RegionData[]> {
  try {
    const response = await fetch(`${BACKEND_URL}/oxilor/regions?country_code=${countryCode}`)
    const data = await response.json()
    console.log(`Régions pour ${countryCode}:`, data)
    
    if (Array.isArray(data)) {
      return data
    } else if (data.data && Array.isArray(data.data)) {
      return data.data
    }
    return []
  } catch (error) {
    console.error(`Erreur régions pour ${countryCode}:`, error)
    return []
  }
}

/**
 * Récupérer toutes les données géographiques
 */
export async function fetchAllGeographyData(): Promise<GeographyData> {
  console.log('Récupération des données géographiques...')
  
  const continents = await fetchContinents()
  console.log(`${continents.length} continents trouvés`)
  
  const countries = await fetchCountries()
  console.log(`${countries.length} pays trouvés`)
  
  // Récupérer les villes et régions pour chaque pays
  const allCities: CityData[] = []
  const allRegions: RegionData[] = []
  
  for (const country of countries) {
    const cities = await fetchCitiesByCountry(country.code)
    allCities.push(...cities)
    
    const regions = await fetchRegionsByCountry(country.code)
    allRegions.push(...regions)
    
    // Petit délai pour ne pas surcharger l'API
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  
  console.log(`${allCities.length} villes trouvées`)
  console.log(`${allRegions.length} régions trouvées`)
  
  return {
    continents,
    countries,
    regions: allRegions,
    cities: allCities,
  }
}

/**
 * Exporter les données en JSON (à utiliser dans Node.js ou un script)
 */
export async function exportGeographyDataToJSON() {
  const data = await fetchAllGeographyData()
  const json = JSON.stringify(data, null, 2)
  console.log('Données géographiques:')
  console.log(json)
  return json
}
