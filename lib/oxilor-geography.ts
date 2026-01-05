// Service géographique utilisant le backend comme proxy pour Oxilor API
// Le backend contourne le problème CORS

const BACKEND_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const API_V1_PREFIX = '/api/v1'
const GEOGRAPHY_ENDPOINT = `${BACKEND_BASE_URL}${API_V1_PREFIX}/geography`

console.log('GEOGRAPHY_ENDPOINT:', GEOGRAPHY_ENDPOINT)

export interface OxilorCountry {
  id: string
  name: string
  code: string
  continent: string
  region?: string
}

export interface OxilorCity {
  id: string
  name: string
  countryCode: string
  country: string
}

/**
 * Récupérer tous les pays
 */
export async function getCountriesFromOxilor(): Promise<OxilorCountry[]> {
  try {
    const url = `${GEOGRAPHY_ENDPOINT}/oxilor/countries`
    console.log('Appel API backend:', url)
    const response = await fetch(url)
    
    if (!response.ok) {
      console.error(`API Error: ${response.status} ${response.statusText}`)
      throw new Error(`API Error: ${response.status}`)
    }
    
    const data = await response.json()
    console.log('Réponse backend (pays):', data)
    
    // Adapter la réponse selon le format de l'API
    if (Array.isArray(data)) {
      return data
    } else if (data.data && Array.isArray(data.data)) {
      return data.data
    } else if (data.countries && Array.isArray(data.countries)) {
      return data.countries
    }
    
    return []
  } catch (error) {
    console.error('Erreur lors de la récupération des pays:', error)
    return []
  }
}

/**
 * Récupérer les villes d'un pays
 */
export async function getCitiesFromOxilor(countryCode: string): Promise<OxilorCity[]> {
  try {
    const url = `${GEOGRAPHY_ENDPOINT}/oxilor/cities?country_code=${countryCode}`
    console.log('Appel API backend:', url)
    const response = await fetch(url)
    
    if (!response.ok) {
      console.error(`API Error: ${response.status} ${response.statusText}`)
      throw new Error(`API Error: ${response.status}`)
    }
    
    const data = await response.json()
    console.log(`Réponse Oxilor (villes pour ${countryCode}):`, data)
    
    // Adapter la réponse selon le format de l'API
    if (Array.isArray(data)) {
      return data
    } else if (data.data && Array.isArray(data.data)) {
      return data.data
    } else if (data.cities && Array.isArray(data.cities)) {
      return data.cities
    }
    
    return []
  } catch (error) {
    console.error(`Erreur lors de la récupération des villes pour ${countryCode}:`, error)
    return []
  }
}

/**
 * Récupérer les régions d'un pays
 */
export async function getRegionsFromOxilor(countryCode: string): Promise<string[]> {
  try {
    const url = `${GEOGRAPHY_ENDPOINT}/oxilor/regions?country_code=${countryCode}`
    console.log('Appel API backend:', url)
    const response = await fetch(url)
    
    if (!response.ok) {
      console.error(`API Error: ${response.status} ${response.statusText}`)
      throw new Error(`API Error: ${response.status}`)
    }
    
    const data = await response.json()
    console.log(`Réponse Oxilor (régions pour ${countryCode}):`, data)
    
    // Adapter la réponse selon le format de l'API
    if (Array.isArray(data)) {
      return data.map(r => typeof r === 'string' ? r : r.name)
    } else if (data.data && Array.isArray(data.data)) {
      return data.data.map(r => typeof r === 'string' ? r : r.name)
    } else if (data.regions && Array.isArray(data.regions)) {
      return data.regions.map(r => typeof r === 'string' ? r : r.name)
    }
    
    return []
  } catch (error) {
    console.error(`Erreur lors de la récupération des régions pour ${countryCode}:`, error)
    return []
  }
}

/**
 * Récupérer les continents
 */
export async function getContinentsFromOxilor(): Promise<string[]> {
  try {
    const url = `${GEOGRAPHY_ENDPOINT}/oxilor/continents`
    console.log('Appel API backend continents:', url)
    const response = await fetch(url)
    
    console.log('Statut réponse:', response.status, response.statusText)
    
    if (!response.ok) {
      console.error(`API Error: ${response.status} ${response.statusText}`)
      throw new Error(`API Error: ${response.status}`)
    }
    
    const data = await response.json()
    console.log('Réponse Oxilor (continents):', data)
    
    // Adapter la réponse selon le format de l'API
    if (Array.isArray(data)) {
      const continents = data.map(c => typeof c === 'string' ? c : c.name)
      console.log('Continents extraits:', continents)
      return continents
    } else if (data.data && Array.isArray(data.data)) {
      const continents = data.data.map(c => typeof c === 'string' ? c : c.name)
      console.log('Continents extraits (data):', continents)
      return continents
    } else if (data.continents && Array.isArray(data.continents)) {
      const continents = data.continents.map(c => typeof c === 'string' ? c : c.name)
      console.log('Continents extraits (continents):', continents)
      return continents
    }
    
    console.warn('Format de réponse non reconnu:', data)
    return []
  } catch (error) {
    console.error('Erreur lors de la récupération des continents depuis Oxilor:', error)
    return []
  }
}

/**
 * Récupérer les pays par continent
 */
export async function getCountriesByContinent(continent: string): Promise<OxilorCountry[]> {
  try {
    const url = `${GEOGRAPHY_ENDPOINT}/oxilor/countries?continent=${continent}`
    console.log('Appel API backend:', url)
    const response = await fetch(url)
    
    if (!response.ok) {
      console.error(`API Error: ${response.status} ${response.statusText}`)
      throw new Error(`API Error: ${response.status}`)
    }
    
    const data = await response.json()
    console.log(`Réponse Oxilor (pays pour ${continent}):`, data)
    
    // Adapter la réponse selon le format de l'API
    if (Array.isArray(data)) {
      return data
    } else if (data.data && Array.isArray(data.data)) {
      return data.data
    } else if (data.countries && Array.isArray(data.countries)) {
      return data.countries
    }
    
    return []
  } catch (error) {
    console.error(`Erreur lors de la récupération des pays pour le continent ${continent}:`, error)
    return []
  }
}

/**
 * Rechercher des villes/régions par terme
 */
export async function searchCities(searchTerm: string, locationType: string = 'city', limit: number = 10): Promise<any[]> {
  try {
    const url = `${GEOGRAPHY_ENDPOINT}/oxilor/search?search_term=${encodeURIComponent(searchTerm)}&location_type=${locationType}&first=${limit}`
    console.log('Appel API recherche:', url)
    const response = await fetch(url)
    
    if (!response.ok) {
      console.error(`API Error: ${response.status} ${response.statusText}`)
      throw new Error(`API Error: ${response.status}`)
    }
    
    const data = await response.json()
    console.log('Résultats recherche:', data)
    
    // Adapter la réponse selon le format de l'API
    if (Array.isArray(data)) {
      return data
    } else if (data.data && Array.isArray(data.data)) {
      return data.data
    } else if (data.results && Array.isArray(data.results)) {
      return data.results
    }
    
    return []
  } catch (error) {
    console.error(`Erreur lors de la recherche de "${searchTerm}":`, error)
    return []
  }
}
