// Service pour l'API Geonames
// Documentation: https://www.geonames.org/export/web-services.html
// Inscription gratuite: https://www.geonames.org/login

const GEONAMES_USERNAME = process.env.NEXT_PUBLIC_GEONAMES_USERNAME || 'demo'
const GEONAMES_BASE_URL = 'https://secure.geonames.org'

interface Country {
  geonameId: number
  name: string
  isoAlpha2: string
  isoAlpha3: string
  continentCode: string
  continentName: string
}

interface Admin1 {
  geonameId: number
  name: string
  adminName1: string
  adminCode1: string
  countryCode: string
}

interface City {
  geonameId: number
  name: string
  lat: number
  lng: number
  countryCode: string
  adminCode1: string
}

/**
 * Récupérer tous les pays avec leurs continents
 */
export async function getCountries(): Promise<Country[]> {
  try {
    const response = await fetch(
      `${GEONAMES_BASE_URL}/getJSON?featureClass=A&featureCode=PCLI&maxRows=300&username=${GEONAMES_USERNAME}`
    )
    const data = await response.json()
    return data.geonames || []
  } catch (error) {
    console.error('Erreur lors de la récupération des pays:', error)
    return []
  }
}

/**
 * Récupérer les régions (admin1) d'un pays
 */
export async function getRegions(countryCode: string): Promise<Admin1[]> {
  try {
    const response = await fetch(
      `${GEONAMES_BASE_URL}/getJSON?featureClass=A&featureCode=ADM1&countryCode=${countryCode}&maxRows=500&username=${GEONAMES_USERNAME}`
    )
    const data = await response.json()
    return data.geonames || []
  } catch (error) {
    console.error(`Erreur lors de la récupération des régions pour ${countryCode}:`, error)
    return []
  }
}

/**
 * Récupérer les villes d'un pays (ou d'une région)
 */
export async function getCities(countryCode: string, adminCode?: string): Promise<City[]> {
  try {
    let url = `${GEONAMES_BASE_URL}/getJSON?featureClass=P&featureCode=PPLA,PPLA2,PPLA3,PPLC&countryCode=${countryCode}&maxRows=1000&username=${GEONAMES_USERNAME}`
    
    if (adminCode) {
      url += `&adminCode1=${adminCode}`
    }

    const response = await fetch(url)
    const data = await response.json()
    return data.geonames || []
  } catch (error) {
    console.error(`Erreur lors de la récupération des villes pour ${countryCode}:`, error)
    return []
  }
}

/**
 * Rechercher des villes par nom
 */
export async function searchCities(query: string, countryCode?: string): Promise<City[]> {
  try {
    let url = `${GEONAMES_BASE_URL}/searchJSON?featureClass=P&featureCode=PPLA,PPLA2,PPLA3,PPLC&maxRows=50&username=${GEONAMES_USERNAME}&q=${encodeURIComponent(query)}`
    
    if (countryCode) {
      url += `&countryCode=${countryCode}`
    }

    const response = await fetch(url)
    const data = await response.json()
    return data.geonames || []
  } catch (error) {
    console.error('Erreur lors de la recherche de villes:', error)
    return []
  }
}

/**
 * Récupérer les pays par continent
 */
export async function getCountriesByContinent(continentCode: string): Promise<Country[]> {
  try {
    const response = await fetch(
      `${GEONAMES_BASE_URL}/getJSON?featureClass=A&featureCode=PCLI&continentCode=${continentCode}&maxRows=300&username=${GEONAMES_USERNAME}`
    )
    const data = await response.json()
    return data.geonames || []
  } catch (error) {
    console.error(`Erreur lors de la récupération des pays pour le continent ${continentCode}:`, error)
    return []
  }
}

/**
 * Mapper les codes de continent Geonames aux noms
 */
export const CONTINENT_CODES: Record<string, string> = {
  'AF': 'Africa',
  'AS': 'Asia',
  'EU': 'Europe',
  'NA': 'North America',
  'SA': 'South America',
  'OC': 'Oceania',
  'AN': 'Antarctica'
}

/**
 * Mapper les noms de continent aux codes Geonames
 */
export const CONTINENT_NAMES_TO_CODES: Record<string, string> = {
  'Africa': 'AF',
  'Asia': 'AS',
  'Europe': 'EU',
  'North America': 'NA',
  'South America': 'SA',
  'Oceania': 'OC',
  'Antarctica': 'AN'
}
