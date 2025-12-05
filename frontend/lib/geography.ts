// Service géographique utilisant RestCountries API (gratuit, sans clé)
// Documentation: https://restcountries.com/

export interface Country {
  name: string
  code: string // ISO 3166-1 alpha-2
  region: string
  subregion: string
  continent: string
}

/**
 * Récupérer tous les pays avec leurs continents et régions
 */
export async function getAllCountries(): Promise<Country[]> {
  try {
    const response = await fetch('https://restcountries.com/v3.1/all')
    const data = await response.json()
    
    const countries: Country[] = data.map((country: any) => ({
      name: country.name.common,
      code: country.cca2,
      region: country.region || '',
      subregion: country.subregion || '',
      continent: country.continents?.[0] || ''
    })).sort((a: Country, b: Country) => a.name.localeCompare(b.name))
    
    return countries
  } catch (error) {
    console.error('Erreur lors de la récupération des pays:', error)
    return []
  }
}

/**
 * Récupérer les pays par continent
 */
export async function getCountriesByContinent(continent: string): Promise<Country[]> {
  const allCountries = await getAllCountries()
  return allCountries.filter(c => c.continent === continent)
}

/**
 * Récupérer les informations d'un pays (continent, région)
 */
export async function getCountryInfo(countryCode: string): Promise<Country | null> {
  try {
    const response = await fetch(`https://restcountries.com/v3.1/alpha/${countryCode}`)
    const data = await response.json()
    
    if (Array.isArray(data) && data.length > 0) {
      const country = data[0]
      return {
        name: country.name.common,
        code: country.cca2,
        region: country.region || '',
        subregion: country.subregion || '',
        continent: country.continents?.[0] || ''
      }
    }
    return null
  } catch (error) {
    console.error(`Erreur lors de la récupération du pays ${countryCode}:`, error)
    return null
  }
}

/**
 * Récupérer les continents uniques
 */
export async function getContinents(): Promise<string[]> {
  const countries = await getAllCountries()
  const continents = new Set(countries.map(c => c.continent).filter(Boolean))
  return Array.from(continents).sort()
}

/**
 * Récupérer les villes principales d'un pays
 * Utilise une liste prédéfinie car il n'existe pas d'API gratuite complète pour les villes
 */
export async function getCitiesByCountry(countryCode: string): Promise<string[]> {
  // Liste des villes principales par code pays (sélection)
  const citiesByCountry: Record<string, string[]> = {
    'SN': ['Dakar', 'Thiès', 'Kaolack', 'Tambacounda', 'Saint-Louis'],
    'ML': ['Bamako', 'Ségou', 'Mopti', 'Gao', 'Koulikoro'],
    'CI': ['Abidjan', 'Yamoussoukro', 'Bouaké', 'Daloa', 'San-Pédro'],
    'GH': ['Accra', 'Kumasi', 'Tamale', 'Sekondi', 'Cape Coast'],
    'NG': ['Lagos', 'Abuja', 'Kano', 'Ibadan', 'Port Harcourt'],
    'ZA': ['Johannesburg', 'Cape Town', 'Durban', 'Pretoria', 'Bloemfontein'],
    'EG': ['Cairo', 'Alexandria', 'Giza', 'Shubra El-Khema', 'Helwan'],
    'KE': ['Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret'],
    'VN': ['Ho Chi Minh City', 'Hanoi', 'Da Nang', 'Can Tho', 'Hai Phong'],
    'TH': ['Bangkok', 'Chiang Mai', 'Phuket', 'Pattaya', 'Rayong'],
    'PH': ['Manila', 'Cebu', 'Davao', 'Quezon City', 'Caloocan'],
    'ID': ['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Semarang'],
    'MY': ['Kuala Lumpur', 'George Town', 'Ipoh', 'Johor Bahru', 'Petaling Jaya'],
    'SG': ['Singapore'],
    'IN': ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai'],
    'PK': ['Karachi', 'Lahore', 'Islamabad', 'Faisalabad', 'Rawalpindi'],
    'BD': ['Dhaka', 'Chittagong', 'Khulna', 'Rajshahi', 'Sylhet'],
    'FR': ['Paris', 'Marseille', 'Lyon', 'Toulouse', 'Nice'],
    'DE': ['Berlin', 'Munich', 'Frankfurt', 'Cologne', 'Hamburg'],
    'GB': ['London', 'Manchester', 'Birmingham', 'Leeds', 'Glasgow'],
    'ES': ['Madrid', 'Barcelona', 'Valencia', 'Seville', 'Bilbao'],
    'IT': ['Rome', 'Milan', 'Naples', 'Turin', 'Venice'],
    'NL': ['Amsterdam', 'Rotterdam', 'The Hague', 'Utrecht', 'Eindhoven'],
    'BE': ['Brussels', 'Antwerp', 'Ghent', 'Charleroi', 'Liège'],
    'CH': ['Zurich', 'Geneva', 'Basel', 'Bern', 'Lausanne'],
    'AT': ['Vienna', 'Graz', 'Linz', 'Salzburg', 'Innsbruck'],
    'SE': ['Stockholm', 'Gothenburg', 'Malmö', 'Uppsala', 'Västerås'],
    'NO': ['Oslo', 'Bergen', 'Trondheim', 'Stavanger', 'Kristiansand'],
    'DK': ['Copenhagen', 'Aarhus', 'Odense', 'Aalborg', 'Esbjerg'],
    'FI': ['Helsinki', 'Espoo', 'Tampere', 'Vantaa', 'Turku'],
    'PL': ['Warsaw', 'Krakow', 'Wroclaw', 'Poznan', 'Gdansk'],
    'CZ': ['Prague', 'Brno', 'Ostrava', 'Plzen', 'Liberec'],
    'HU': ['Budapest', 'Debrecen', 'Szeged', 'Miskolc', 'Pecs'],
    'RO': ['Bucharest', 'Cluj-Napoca', 'Timisoara', 'Iasi', 'Constanta'],
    'GR': ['Athens', 'Thessaloniki', 'Patras', 'Heraklion', 'Larissa'],
    'PT': ['Lisbon', 'Porto', 'Covilha', 'Braga', 'Funchal'],
    'US': ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix'],
    'CA': ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa'],
    'MX': ['Mexico City', 'Guadalajara', 'Monterrey', 'Cancun', 'Playa del Carmen'],
    'BR': ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Salvador', 'Fortaleza'],
    'CO': ['Bogotá', 'Medellín', 'Cali', 'Barranquilla', 'Cartagena'],
    'AR': ['Buenos Aires', 'Córdoba', 'Rosario', 'Mendoza', 'La Plata'],
    'CL': ['Santiago', 'Valparaíso', 'Concepción', 'La Serena', 'Temuco'],
    'PE': ['Lima', 'Arequipa', 'Cusco', 'Trujillo', 'Iquitos'],
    'AU': ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide'],
    'NZ': ['Auckland', 'Wellington', 'Christchurch', 'Hamilton', 'Tauranga'],
    'SA': ['Riyadh', 'Jeddah', 'Mecca', 'Medina', 'Dammam'],
    'AE': ['Dubai', 'Abu Dhabi', 'Sharjah', 'Ajman', 'Ras Al Khaimah'],
    'IL': ['Tel Aviv', 'Jerusalem', 'Haifa', 'Beersheba', 'Rishon LeZion'],
    'JO': ['Amman', 'Zarqa', 'Irbid', 'Aqaba', 'Jerash'],
    'LB': ['Beirut', 'Tripoli', 'Sidon', 'Tyre', 'Baalbek'],
    'IR': ['Tehran', 'Isfahan', 'Mashhad', 'Tabriz', 'Shiraz'],
    'IQ': ['Baghdad', 'Basra', 'Mosul', 'Kirkuk', 'Najaf'],
  }
  
  return citiesByCountry[countryCode] || []
}
