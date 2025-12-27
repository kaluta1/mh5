'use client'

import { useState, useEffect } from 'react'
import { MapPin, Globe, Loader2 } from 'lucide-react'
import { 
  getCountriesByContinent, 
  getRegions, 
  getCities,
  CONTINENT_CODES,
  CONTINENT_NAMES_TO_CODES
} from '@/lib/geonames'

interface CountryCitySelectorProps {
  onCountryChange: (country: string) => void
  onCityChange: (city: string) => void
  onRegionChange: (region: string) => void
  onContinentChange: (continent: string) => void
  selectedCountry?: string
  selectedCity?: string
}

// Données géographiques locales (fallback si API échoue)
const GEOGRAPHY_DATA: Record<string, Record<string, Record<string, string[]>>> = {
  'Africa': {
    'West Africa': {
      'Senegal': ['Dakar', 'Thiès', 'Kaolack', 'Tambacounda', 'Saint-Louis'],
      'Mali': ['Bamako', 'Ségou', 'Mopti', 'Gao', 'Koulikoro'],
      'Ivory Coast': ['Abidjan', 'Yamoussoukro', 'Bouaké', 'Daloa', 'San-Pédro'],
      'Ghana': ['Accra', 'Kumasi', 'Tamale', 'Sekondi', 'Cape Coast'],
      'Nigeria': ['Lagos', 'Abuja', 'Kano', 'Ibadan', 'Port Harcourt'],
      'Benin': ['Cotonou', 'Porto-Novo', 'Parakou', 'Djougou', 'Abomey'],
      'Togo': ['Lomé', 'Sokodé', 'Kara', 'Atakpamé', 'Dapaong'],
      'Burkina Faso': ['Ouagadougou', 'Bobo-Dioulasso', 'Koudougou', 'Ouahigouya', 'Banfora'],
      'Guinea': ['Conakry', 'Kindia', 'Mamou', 'Kindia', 'Faranah'],
      'Guinea-Bissau': ['Bissau', 'Bafatá', 'Gabu', 'Cacheu', 'Oio'],
      'Liberia': ['Monrovia', 'Gbarnga', 'Kakata', 'Voinjama', 'Buchanan'],
      'Sierra Leone': ['Freetown', 'Bo', 'Kenema', 'Makeni', 'Koidu'],
    },
    'South Africa': {
      'South Africa': ['Johannesburg', 'Cape Town', 'Durban', 'Pretoria', 'Bloemfontein'],
      'Botswana': ['Gaborone', 'Francistown', 'Molepolole', 'Selibe-Phikwe', 'Kasane'],
      'Namibia': ['Windhoek', 'Walvis Bay', 'Swakopmund', 'Oshakati', 'Rundu'],
      'Zimbabwe': ['Harare', 'Bulawayo', 'Chitungwiza', 'Mutare', 'Gweru'],
      'Zambia': ['Lusaka', 'Ndola', 'Kitwe', 'Livingstone', 'Mufulira'],
      'Malawi': ['Lilongwe', 'Blantyre', 'Mzuzu', 'Zomba', 'Kasungu'],
      'Mozambique': ['Maputo', 'Matola', 'Beira', 'Nampula', 'Chimoio'],
      'Eswatini': ['Mbabane', 'Manzini', 'Big Bend', 'Piggs Peak', 'Siteki'],
      'Lesotho': ['Maseru', 'Teyateyaneng', 'Mafeteng', 'Leribe', 'Butha-Buthe'],
    },
    'North Africa': {
      'Egypt': ['Cairo', 'Alexandria', 'Giza', 'Shubra El-Khema', 'Helwan'],
      'Libya': ['Tripoli', 'Benghazi', 'Misrata', 'Zawiya', 'Derna'],
      'Tunisia': ['Tunis', 'Sfax', 'Sousse', 'Kairouan', 'Gabès'],
      'Algeria': ['Algiers', 'Oran', 'Constantine', 'Annaba', 'Blida'],
      'Morocco': ['Casablanca', 'Fez', 'Marrakech', 'Tangier', 'Rabat'],
      'Sudan': ['Khartoum', 'Omdurman', 'Port Sudan', 'Kassala', 'Gedaref'],
    },
    'East Africa': {
      'Kenya': ['Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret'],
      'Tanzania': ['Dar es Salaam', 'Mwanza', 'Arusha', 'Dodoma', 'Mbeya'],
      'Uganda': ['Kampala', 'Gulu', 'Lira', 'Mbarara', 'Jinja'],
      'Ethiopia': ['Addis Ababa', 'Dire Dawa', 'Adama', 'Mekelle', 'Hawassa'],
      'Rwanda': ['Kigali', 'Butare', 'Gitarama', 'Ruhengeri', 'Kibuye'],
      'Burundi': ['Bujumbura', 'Gitega', 'Ngozi', 'Muyinga', 'Ruyigi'],
      'Somalia': ['Mogadishu', 'Hargeisa', 'Kismayo', 'Bosaso', 'Beledweyne'],
      'Djibouti': ['Djibouti City', 'Ali Sabieh', 'Tadjourah', 'Obock', 'Dikhil'],
    },
    'Central Africa': {
      'Cameroon': ['Douala', 'Yaoundé', 'Garoua', 'Bamenda', 'Bafoussam'],
      'Chad': ['N\'Djamena', 'Sarh', 'Moundou', 'Abéché', 'Koumra'],
      'Central African Republic': ['Bangui', 'Berberati', 'Bambari', 'Bouar', 'Bossangoa'],
      'Congo': ['Brazzaville', 'Pointe-Noire', 'Dolisie', 'Nkayi', 'Ouesso'],
      'Democratic Republic of Congo': ['Kinshasa', 'Lubumbashi', 'Mbuji-Mayi', 'Kananga', 'Tshikapa'],
      'Gabon': ['Libreville', 'Port-Gentil', 'Franceville', 'Oyem', 'Lambaréné'],
      'Equatorial Guinea': ['Malabo', 'Bata', 'Ebebiyin', 'Mongomo', 'Evinayong'],
      'São Tomé and Príncipe': ['São Tomé', 'Santo António', 'Trindade', 'Neves', 'Caué'],
    },
  },
  'Asia': {
    'Southeast Asia': {
      'Vietnam': ['Ho Chi Minh City', 'Hanoi', 'Da Nang', 'Can Tho', 'Hai Phong'],
      'Thailand': ['Bangkok', 'Chiang Mai', 'Phuket', 'Pattaya', 'Rayong'],
      'Philippines': ['Manila', 'Cebu', 'Davao', 'Quezon City', 'Caloocan'],
      'Indonesia': ['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Semarang'],
      'Malaysia': ['Kuala Lumpur', 'George Town', 'Ipoh', 'Johor Bahru', 'Petaling Jaya'],
      'Singapore': ['Singapore'],
      'Cambodia': ['Phnom Penh', 'Siem Reap', 'Battambang', 'Kampong Cham', 'Sihanoukville'],
      'Laos': ['Vientiane', 'Luang Prabang', 'Savannakhet', 'Pakse', 'Thakhek'],
      'Myanmar': ['Yangon', 'Mandalay', 'Naypyidaw', 'Bagan', 'Mawlamyine'],
      'Brunei': ['Bandar Seri Begawan', 'Kuala Belait', 'Tutong', 'Seria', 'Bangar'],
      'East Timor': ['Dili', 'Baucau', 'Maliana', 'Suai', 'Oecussi'],
    },
    'South Asia': {
      'India': ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai'],
      'Pakistan': ['Karachi', 'Lahore', 'Islamabad', 'Faisalabad', 'Rawalpindi'],
      'Bangladesh': ['Dhaka', 'Chittagong', 'Khulna', 'Rajshahi', 'Sylhet'],
      'Sri Lanka': ['Colombo', 'Kandy', 'Galle', 'Jaffna', 'Matara'],
      'Nepal': ['Kathmandu', 'Pokhara', 'Lalitpur', 'Bhaktapur', 'Biratnagar'],
      'Bhutan': ['Thimphu', 'Paro', 'Punakha', 'Trongsa', 'Mongar'],
      'Maldives': ['Malé', 'Addu City', 'Funadhoo', 'Eydhafushi', 'Kulhudhuffushi'],
    },
    'Middle East': {
      'Saudi Arabia': ['Riyadh', 'Jeddah', 'Mecca', 'Medina', 'Dammam'],
      'United Arab Emirates': ['Dubai', 'Abu Dhabi', 'Sharjah', 'Ajman', 'Ras Al Khaimah'],
      'Israel': ['Tel Aviv', 'Jerusalem', 'Haifa', 'Beersheba', 'Rishon LeZion'],
      'Palestine': ['Ramallah', 'Gaza City', 'Bethlehem', 'Hebron', 'Nablus'],
      'Jordan': ['Amman', 'Zarqa', 'Irbid', 'Aqaba', 'Jerash'],
      'Lebanon': ['Beirut', 'Tripoli', 'Sidon', 'Tyre', 'Baalbek'],
      'Syria': ['Damascus', 'Aleppo', 'Homs', 'Latakia', 'Hama'],
      'Iraq': ['Baghdad', 'Basra', 'Mosul', 'Kirkuk', 'Najaf'],
      'Iran': ['Tehran', 'Isfahan', 'Mashhad', 'Tabriz', 'Shiraz'],
      'Yemen': ['Sana\'a', 'Aden', 'Taiz', 'Hodeidah', 'Ibb'],
      'Oman': ['Muscat', 'Salalah', 'Sohar', 'Nizwa', 'Sur'],
      'Qatar': ['Doha', 'Al Rayyan', 'Umm Salal', 'Al Wakrah', 'Al Khor'],
      'Bahrain': ['Manama', 'Riffa', 'Muharraq', 'Hamad Town', 'Isa Town'],
      'Kuwait': ['Kuwait City', 'Al Ahmadi', 'Salmiya', 'Hawalli', 'Farwaniya'],
    },
  },
  'Europe': {
    'Western Europe': {
      'France': ['Paris', 'Marseille', 'Lyon', 'Toulouse', 'Nice'],
      'Germany': ['Berlin', 'Munich', 'Frankfurt', 'Cologne', 'Hamburg'],
      'United Kingdom': ['London', 'Manchester', 'Birmingham', 'Leeds', 'Glasgow'],
      'Spain': ['Madrid', 'Barcelona', 'Valencia', 'Seville', 'Bilbao'],
      'Italy': ['Rome', 'Milan', 'Naples', 'Turin', 'Venice'],
      'Netherlands': ['Amsterdam', 'Rotterdam', 'The Hague', 'Utrecht', 'Eindhoven'],
      'Belgium': ['Brussels', 'Antwerp', 'Ghent', 'Charleroi', 'Liège'],
      'Switzerland': ['Zurich', 'Geneva', 'Basel', 'Bern', 'Lausanne'],
      'Austria': ['Vienna', 'Graz', 'Linz', 'Salzburg', 'Innsbruck'],
      'Luxembourg': ['Luxembourg City', 'Esch-sur-Alzette', 'Differdange', 'Dudelange', 'Schifflange'],
    },
    'Northern Europe': {
      'Sweden': ['Stockholm', 'Gothenburg', 'Malmö', 'Uppsala', 'Västerås'],
      'Norway': ['Oslo', 'Bergen', 'Trondheim', 'Stavanger', 'Kristiansand'],
      'Denmark': ['Copenhagen', 'Aarhus', 'Odense', 'Aalborg', 'Esbjerg'],
      'Finland': ['Helsinki', 'Espoo', 'Tampere', 'Vantaa', 'Turku'],
      'Iceland': ['Reykjavik', 'Kópavogur', 'Hafnarfjörður', 'Akranes', 'Hveragerði'],
      'Ireland': ['Dublin', 'Cork', 'Limerick', 'Galway', 'Waterford'],
    },
    'Eastern Europe': {
      'Poland': ['Warsaw', 'Krakow', 'Wroclaw', 'Poznan', 'Gdansk'],
      'Czech Republic': ['Prague', 'Brno', 'Ostrava', 'Plzen', 'Liberec'],
      'Slovakia': ['Bratislava', 'Kosice', 'Presov', 'Zilina', 'Banska Bystrica'],
      'Hungary': ['Budapest', 'Debrecen', 'Szeged', 'Miskolc', 'Pecs'],
      'Romania': ['Bucharest', 'Cluj-Napoca', 'Timisoara', 'Iasi', 'Constanta'],
      'Bulgaria': ['Sofia', 'Plovdiv', 'Varna', 'Burgas', 'Ruse'],
      'Serbia': ['Belgrade', 'Nis', 'Zemun', 'Subotica', 'Kragujevac'],
      'Croatia': ['Zagreb', 'Split', 'Rijeka', 'Osijek', 'Zadar'],
      'Slovenia': ['Ljubljana', 'Maribor', 'Celje', 'Kranj', 'Novo Mesto'],
      'Bosnia and Herzegovina': ['Sarajevo', 'Banja Luka', 'Zenica', 'Tuzla', 'Mostar'],
    },
    'Southern Europe': {
      'Greece': ['Athens', 'Thessaloniki', 'Patras', 'Heraklion', 'Larissa'],
      'Portugal': ['Lisbon', 'Porto', 'Covilha', 'Braga', 'Funchal'],
      'Cyprus': ['Nicosia', 'Limassol', 'Larnaca', 'Paphos', 'Famagusta'],
      'Malta': ['Valletta', 'Birkirkara', 'Mosta', 'Naxxar', 'Sliema'],
    },
  },
  'Americas': {
    'North America': {
      'United States': ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix'],
      'Canada': ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa'],
      'Mexico': ['Mexico City', 'Guadalajara', 'Monterrey', 'Cancun', 'Playa del Carmen'],
    },
    'Central America': {
      'Guatemala': ['Guatemala City', 'Quetzaltenango', 'Escuintla', 'Mazatenango', 'Chimaltenango'],
      'Honduras': ['Tegucigalpa', 'San Pedro Sula', 'La Ceiba', 'Choloma', 'Comayagua'],
      'El Salvador': ['San Salvador', 'Santa Ana', 'San Miguel', 'Nueva San Salvador', 'Soyapango'],
      'Nicaragua': ['Managua', 'León', 'Granada', 'Masaya', 'Chinandega'],
      'Costa Rica': ['San José', 'Limón', 'Alajuela', 'Cartago', 'Puntarenas'],
      'Panama': ['Panama City', 'Colón', 'David', 'La Chorrera', 'Tocumen'],
      'Belize': ['Belmopan', 'Belize City', 'Orange Walk', 'San Ignacio', 'Dangriga'],
    },
    'South America': {
      'Brazil': ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Salvador', 'Fortaleza'],
      'Colombia': ['Bogotá', 'Medellín', 'Cali', 'Barranquilla', 'Cartagena'],
      'Venezuela': ['Caracas', 'Maracaibo', 'Valencia', 'Barquisimeto', 'Ciudad Guayana'],
      'Guyana': ['Georgetown', 'Linden', 'New Amsterdam', 'Corriverton', 'Bartica'],
      'Suriname': ['Paramaribo', 'Lelydorp', 'Lelydorp', 'Albina', 'Groningen'],
      'French Guiana': ['Cayenne', 'Kourou', 'Saint-Laurent-du-Maroni', 'Remire-Montjoly', 'Macouria'],
      'Ecuador': ['Quito', 'Guayaquil', 'Cuenca', 'Santo Domingo', 'Ambato'],
      'Peru': ['Lima', 'Arequipa', 'Cusco', 'Trujillo', 'Iquitos'],
      'Bolivia': ['La Paz', 'Santa Cruz', 'Cochabamba', 'Oruro', 'Potosí'],
      'Chile': ['Santiago', 'Valparaíso', 'Concepción', 'La Serena', 'Temuco'],
      'Argentina': ['Buenos Aires', 'Córdoba', 'Rosario', 'Mendoza', 'La Plata'],
      'Uruguay': ['Montevideo', 'Salto', 'Paysandú', 'Las Piedras', 'Rivera'],
      'Paraguay': ['Asunción', 'Ciudad del Este', 'Encarnación', 'Villarrica', 'Coronel Oviedo'],
    },
    'Caribbean': {
      'Cuba': ['Havana', 'Santiago de Cuba', 'Camagüey', 'Holguín', 'Santa Clara'],
      'Dominican Republic': ['Santo Domingo', 'Santiago', 'La Romana', 'San Cristóbal', 'Puerto Plata'],
      'Haiti': ['Port-au-Prince', 'Cap-Haïtien', 'Gonaïves', 'Les Cayes', 'Jérémie'],
      'Jamaica': ['Kingston', 'Montego Bay', 'Spanish Town', 'Portmore', 'May Pen'],
      'Trinidad and Tobago': ['Port of Spain', 'San Fernando', 'Arima', 'Point Fortin', 'Chaguanas'],
      'Bahamas': ['Nassau', 'Freeport', 'Marsh Harbour', 'Coopers Town', 'Staniel Cay'],
      'Barbados': ['Bridgetown', 'Speightstown', 'Oistins', 'Bathsheba', 'Holetown'],
      'Saint Lucia': ['Castries', 'Vieux Fort', 'Soufrière', 'Laborie', 'Choiseul'],
      'Grenada': ['Saint George\'s', 'Grenville', 'Gouyave', 'Victoria', 'Sauteurs'],
    },
  },
  'Oceania': {
    'Australasia': {
      'Australia': ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide'],
      'New Zealand': ['Auckland', 'Wellington', 'Christchurch', 'Hamilton', 'Tauranga'],
    },
    'Pacific Islands': {
      'Fiji': ['Suva', 'Nadi', 'Lautoka', 'Labasa', 'Ba'],
      'Samoa': ['Apia', 'Vaiusu', 'Falefa', 'Leulumoega', 'Satupaitea'],
      'Tonga': ['Nuku\'alofa', 'Neiafu', 'Pangai', 'Ohonua', 'Kolofo\'ou'],
      'Vanuatu': ['Port Vila', 'Luganville', 'Isangel', 'Lakatoi', 'Norsup'],
      'Kiribati': ['Tarawa', 'Betio', 'Bairiki', 'Buota', 'Marakei'],
      'Marshall Islands': ['Majuro', 'Ebeye', 'Kwajalein', 'Arno', 'Mili'],
      'Micronesia': ['Palikir', 'Kolonia', 'Weno', 'Tol', 'Udot'],
      'Palau': ['Koror', 'Melekeok', 'Airai', 'Peleliu', 'Angaur'],
      'Solomon Islands': ['Honiara', 'Gizo', 'Auki', 'Buala', 'Kira Kira'],
      'Papua New Guinea': ['Port Moresby', 'Lae', 'Madang', 'Mount Hagen', 'Goroka'],
    },
  },
}

export function CountryCitySelector({
  onCountryChange,
  onCityChange,
  onRegionChange,
  onContinentChange,
  selectedCountry = '',
  selectedCity = '',
}: CountryCitySelectorProps) {
  const [continents, setContinents] = useState<string[]>([])
  const [selectedContinent, setSelectedContinent] = useState('')
  const [countries, setCountries] = useState<Array<{ name: string; code: string }>>([])
  const [selectedCountryCode, setSelectedCountryCode] = useState('')
  const [regions, setRegions] = useState<Array<{ name: string; code: string }>>([])
  const [selectedRegion, setSelectedRegion] = useState('')
  const [cities, setCities] = useState<Array<{ name: string; code: string }>>([])
  const [loading, setLoading] = useState(false)

  // Initialiser les continents
  useEffect(() => {
    setContinents(Object.values(CONTINENT_CODES))
  }, [])

  // Charger les pays quand le continent change
  useEffect(() => {
    if (selectedContinent) {
      setLoading(true)
      const continentCode = CONTINENT_NAMES_TO_CODES[selectedContinent]
      
      getCountriesByContinent(continentCode)
        .then((data) => {
          const countryList = data.map(c => ({
            name: c.name,
            code: c.isoAlpha2
          })).sort((a, b) => a.name.localeCompare(b.name))
          setCountries(countryList)
          setSelectedCountryCode('')
          setRegions([])
          setCities([])
          onContinentChange(selectedContinent)
        })
        .catch(() => {
          // Fallback aux données locales
          const regionsList = Object.keys(GEOGRAPHY_DATA[selectedContinent] || {})
          const countrySet = new Set<string>()
          regionsList.forEach(region => {
            Object.keys(GEOGRAPHY_DATA[selectedContinent][region]).forEach(country => {
              countrySet.add(country)
            })
          })
          setCountries(Array.from(countrySet).map(name => ({ name, code: name })))
        })
        .finally(() => setLoading(false))
    }
  }, [selectedContinent, onContinentChange])

  // Charger les régions quand le pays change
  useEffect(() => {
    if (selectedCountryCode) {
      setLoading(true)
      getRegions(selectedCountryCode)
        .then((data) => {
          const regionList = data.map(r => ({
            name: r.adminName1,
            code: r.adminCode1
          })).sort((a, b) => a.name.localeCompare(b.name))
          setRegions(regionList)
          setSelectedRegion('')
          setCities([])
        })
        .catch(() => {
          setRegions([])
        })
        .finally(() => setLoading(false))
    }
  }, [selectedCountryCode])

  // Charger les villes quand la région change (ou le pays si pas de région)
  useEffect(() => {
    if (selectedCountryCode) {
      setLoading(true)
      getCities(selectedCountryCode, selectedRegion || undefined)
        .then((data) => {
          const cityList = data.map(c => ({
            name: c.name,
            code: c.name
          })).sort((a, b) => a.name.localeCompare(b.name))
          setCities(cityList)
          onRegionChange(selectedRegion)
        })
        .catch(() => {
          setCities([])
        })
        .finally(() => setLoading(false))
    }
  }, [selectedCountryCode, selectedRegion, onRegionChange])

  return (
    <div className="space-y-4">
      {/* Continent */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
          <Globe className="inline mr-2 h-4 w-4" />
          Continent *
        </label>
        <select
          value={selectedContinent}
          onChange={(e) => setSelectedContinent(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
          required
        >
          <option value="">Sélectionner un continent</option>
          {continents.map((continent) => (
            <option key={continent} value={continent}>
              {continent}
            </option>
          ))}
        </select>
      </div>

      {/* Country */}
      {selectedContinent && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <Globe className="inline mr-2 h-4 w-4" />
            Pays *
          </label>
          <select
            value={selectedCountryCode}
            onChange={(e) => {
              setSelectedCountryCode(e.target.value)
              const country = countries.find(c => c.code === e.target.value)
              if (country) onCountryChange(country.name)
            }}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary disabled:opacity-50"
            disabled={loading || countries.length === 0}
            required
          >
            <option value="">{loading ? 'Chargement...' : 'Sélectionner un pays'}</option>
            {countries.map((country) => (
              <option key={country.code} value={country.code}>
                {country.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Region */}
      {selectedCountryCode && regions.length > 0 && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <MapPin className="inline mr-2 h-4 w-4" />
            Région
          </label>
          <select
            value={selectedRegion}
            onChange={(e) => setSelectedRegion(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary disabled:opacity-50"
            disabled={loading}
          >
            <option value="">Toutes les régions</option>
            {regions.map((region) => (
              <option key={region.code} value={region.code}>
                {region.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* City */}
      {selectedCountryCode && cities.length > 0 && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
            <MapPin className="inline mr-2 h-4 w-4" />
            Ville *
          </label>
          <select
            value={selectedCity}
            onChange={(e) => onCityChange(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary disabled:opacity-50"
            disabled={loading || cities.length === 0}
            required
          >
            <option value="">{loading ? 'Chargement...' : 'Sélectionner une ville'}</option>
            {cities.map((city) => (
              <option key={city.code} value={city.code}>
                {city.name}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}
