// Données statiques des pays avec continent et région
export interface CountryData {
  name: string
  code: string
  continent: string
  region: string
  cities: string[]
}

export const COUNTRIES_DATA: CountryData[] = [
  // Afrique - West Africa
  { name: 'Senegal', code: 'SN', continent: 'Africa', region: 'West Africa', cities: ['Dakar', 'Thiès', 'Kaolack', 'Tambacounda', 'Saint-Louis'] },
  { name: 'Mali', code: 'ML', continent: 'Africa', region: 'West Africa', cities: ['Bamako', 'Ségou', 'Mopti', 'Gao', 'Koulikoro'] },
  { name: "Côte d'Ivoire", code: 'CI', continent: 'Africa', region: 'West Africa', cities: ['Abidjan', 'Yamoussoukro', 'Bouaké', 'Daloa', 'San-Pédro'] },
  { name: 'Ghana', code: 'GH', continent: 'Africa', region: 'West Africa', cities: ['Accra', 'Kumasi', 'Tamale', 'Sekondi', 'Cape Coast'] },
  { name: 'Nigeria', code: 'NG', continent: 'Africa', region: 'West Africa', cities: ['Lagos', 'Abuja', 'Kano', 'Ibadan', 'Port Harcourt'] },
  { name: 'Benin', code: 'BJ', continent: 'Africa', region: 'West Africa', cities: ['Cotonou', 'Porto-Novo', 'Parakou', 'Djougou', 'Abomey'] },
  { name: 'Togo', code: 'TG', continent: 'Africa', region: 'West Africa', cities: ['Lomé', 'Sokodé', 'Kara', 'Atakpamé', 'Dapaong'] },
  { name: 'Burkina Faso', code: 'BF', continent: 'Africa', region: 'West Africa', cities: ['Ouagadougou', 'Bobo-Dioulasso', 'Koudougou', 'Ouahigouya', 'Banfora'] },
  { name: 'Guinea', code: 'GN', continent: 'Africa', region: 'West Africa', cities: ['Conakry', 'Kindia', 'Mamou', 'Faranah', 'Kissidougou'] },
  { name: 'Guinea-Bissau', code: 'GW', continent: 'Africa', region: 'West Africa', cities: ['Bissau', 'Bafatá', 'Gabu', 'Cacheu', 'Oio'] },
  { name: 'Liberia', code: 'LR', continent: 'Africa', region: 'West Africa', cities: ['Monrovia', 'Gbarnga', 'Kakata', 'Voinjama', 'Buchanan'] },
  { name: 'Sierra Leone', code: 'SL', continent: 'Africa', region: 'West Africa', cities: ['Freetown', 'Bo', 'Kenema', 'Makeni', 'Koidu'] },

  // Afrique - South Africa
  { name: 'South Africa', code: 'ZA', continent: 'Africa', region: 'South Africa', cities: ['Johannesburg', 'Cape Town', 'Durban', 'Pretoria', 'Bloemfontein'] },
  { name: 'Botswana', code: 'BW', continent: 'Africa', region: 'South Africa', cities: ['Gaborone', 'Francistown', 'Molepolole', 'Selibe-Phikwe', 'Kasane'] },
  { name: 'Namibia', code: 'NA', continent: 'Africa', region: 'South Africa', cities: ['Windhoek', 'Walvis Bay', 'Swakopmund', 'Oshakati', 'Rundu'] },
  { name: 'Zimbabwe', code: 'ZW', continent: 'Africa', region: 'South Africa', cities: ['Harare', 'Bulawayo', 'Chitungwiza', 'Mutare', 'Gweru'] },
  { name: 'Zambia', code: 'ZM', continent: 'Africa', region: 'South Africa', cities: ['Lusaka', 'Ndola', 'Kitwe', 'Livingstone', 'Mufulira'] },
  { name: 'Malawi', code: 'MW', continent: 'Africa', region: 'South Africa', cities: ['Lilongwe', 'Blantyre', 'Mzuzu', 'Zomba', 'Kasungu'] },
  { name: 'Mozambique', code: 'MZ', continent: 'Africa', region: 'South Africa', cities: ['Maputo', 'Matola', 'Beira', 'Nampula', 'Chimoio'] },
  { name: 'Eswatini', code: 'SZ', continent: 'Africa', region: 'South Africa', cities: ['Mbabane', 'Manzini', 'Big Bend', 'Piggs Peak', 'Siteki'] },
  { name: 'Lesotho', code: 'LS', continent: 'Africa', region: 'South Africa', cities: ['Maseru', 'Teyateyaneng', 'Mafeteng', 'Leribe', 'Butha-Buthe'] },

  // Afrique - North Africa
  { name: 'Egypt', code: 'EG', continent: 'Africa', region: 'North Africa', cities: ['Cairo', 'Alexandria', 'Giza', 'Shubra El-Khema', 'Helwan'] },
  { name: 'Libya', code: 'LY', continent: 'Africa', region: 'North Africa', cities: ['Tripoli', 'Benghazi', 'Misrata', 'Zawiya', 'Derna'] },
  { name: 'Tunisia', code: 'TN', continent: 'Africa', region: 'North Africa', cities: ['Tunis', 'Sfax', 'Sousse', 'Kairouan', 'Gabès'] },
  { name: 'Algeria', code: 'DZ', continent: 'Africa', region: 'North Africa', cities: ['Algiers', 'Oran', 'Constantine', 'Annaba', 'Blida'] },
  { name: 'Morocco', code: 'MA', continent: 'Africa', region: 'North Africa', cities: ['Casablanca', 'Fez', 'Marrakech', 'Tangier', 'Rabat'] },
  { name: 'Sudan', code: 'SD', continent: 'Africa', region: 'North Africa', cities: ['Khartoum', 'Omdurman', 'Port Sudan', 'Kassala', 'Gedaref'] },

  // Afrique - East Africa
  { name: 'Kenya', code: 'KE', continent: 'Africa', region: 'East Africa', cities: ['Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret'] },
  { name: 'Tanzania', code: 'TZ', continent: 'Africa', region: 'East Africa', cities: ['Dar es Salaam', 'Mwanza', 'Arusha', 'Dodoma', 'Mbeya'] },
  { name: 'Uganda', code: 'UG', continent: 'Africa', region: 'East Africa', cities: ['Kampala', 'Gulu', 'Lira', 'Mbarara', 'Jinja'] },
  { name: 'Ethiopia', code: 'ET', continent: 'Africa', region: 'East Africa', cities: ['Addis Ababa', 'Dire Dawa', 'Adama', 'Mekelle', 'Hawassa'] },
  { name: 'Rwanda', code: 'RW', continent: 'Africa', region: 'East Africa', cities: ['Kigali', 'Butare', 'Gitarama', 'Ruhengeri', 'Kibuye'] },
  { name: 'Burundi', code: 'BI', continent: 'Africa', region: 'East Africa', cities: ['Bujumbura', 'Gitega', 'Ngozi', 'Muyinga', 'Ruyigi'] },
  { name: 'Somalia', code: 'SO', continent: 'Africa', region: 'East Africa', cities: ['Mogadishu', 'Hargeisa', 'Kismayo', 'Bosaso', 'Beledweyne'] },
  { name: 'Djibouti', code: 'DJ', continent: 'Africa', region: 'East Africa', cities: ['Djibouti City', 'Ali Sabieh', 'Tadjourah', 'Obock', 'Dikhil'] },

  // Asie - Southeast Asia
  { name: 'Vietnam', code: 'VN', continent: 'Asia', region: 'Southeast Asia', cities: ['Ho Chi Minh City', 'Hanoi', 'Da Nang', 'Can Tho', 'Hai Phong'] },
  { name: 'Thailand', code: 'TH', continent: 'Asia', region: 'Southeast Asia', cities: ['Bangkok', 'Chiang Mai', 'Phuket', 'Pattaya', 'Rayong'] },
  { name: 'Philippines', code: 'PH', continent: 'Asia', region: 'Southeast Asia', cities: ['Manila', 'Cebu', 'Davao', 'Quezon City', 'Caloocan'] },
  { name: 'Indonesia', code: 'ID', continent: 'Asia', region: 'Southeast Asia', cities: ['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Semarang'] },
  { name: 'Malaysia', code: 'MY', continent: 'Asia', region: 'Southeast Asia', cities: ['Kuala Lumpur', 'George Town', 'Ipoh', 'Johor Bahru', 'Petaling Jaya'] },
  { name: 'Singapore', code: 'SG', continent: 'Asia', region: 'Southeast Asia', cities: ['Singapore'] },
  { name: 'Cambodia', code: 'KH', continent: 'Asia', region: 'Southeast Asia', cities: ['Phnom Penh', 'Siem Reap', 'Battambang', 'Kampong Cham', 'Sihanoukville'] },
  { name: 'Laos', code: 'LA', continent: 'Asia', region: 'Southeast Asia', cities: ['Vientiane', 'Luang Prabang', 'Savannakhet', 'Pakse', 'Thakhek'] },
  { name: 'Myanmar', code: 'MM', continent: 'Asia', region: 'Southeast Asia', cities: ['Yangon', 'Mandalay', 'Naypyidaw', 'Bagan', 'Mawlamyine'] },

  // Asie - South Asia
  { name: 'India', code: 'IN', continent: 'Asia', region: 'South Asia', cities: ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai'] },
  { name: 'Pakistan', code: 'PK', continent: 'Asia', region: 'South Asia', cities: ['Karachi', 'Lahore', 'Islamabad', 'Faisalabad', 'Rawalpindi'] },
  { name: 'Bangladesh', code: 'BD', continent: 'Asia', region: 'South Asia', cities: ['Dhaka', 'Chittagong', 'Khulna', 'Rajshahi', 'Sylhet'] },
  { name: 'Sri Lanka', code: 'LK', continent: 'Asia', region: 'South Asia', cities: ['Colombo', 'Kandy', 'Galle', 'Jaffna', 'Matara'] },
  { name: 'Nepal', code: 'NP', continent: 'Asia', region: 'South Asia', cities: ['Kathmandu', 'Pokhara', 'Lalitpur', 'Bhaktapur', 'Biratnagar'] },

  // Asie - Middle East
  { name: 'Saudi Arabia', code: 'SA', continent: 'Asia', region: 'Middle East', cities: ['Riyadh', 'Jeddah', 'Mecca', 'Medina', 'Dammam'] },
  { name: 'United Arab Emirates', code: 'AE', continent: 'Asia', region: 'Middle East', cities: ['Dubai', 'Abu Dhabi', 'Sharjah', 'Ajman', 'Ras Al Khaimah'] },
  { name: 'Israel', code: 'IL', continent: 'Asia', region: 'Middle East', cities: ['Tel Aviv', 'Jerusalem', 'Haifa', 'Beersheba', 'Rishon LeZion'] },
  { name: 'Jordan', code: 'JO', continent: 'Asia', region: 'Middle East', cities: ['Amman', 'Zarqa', 'Irbid', 'Aqaba', 'Jerash'] },
  { name: 'Lebanon', code: 'LB', continent: 'Asia', region: 'Middle East', cities: ['Beirut', 'Tripoli', 'Sidon', 'Tyre', 'Baalbek'] },
  { name: 'Iran', code: 'IR', continent: 'Asia', region: 'Middle East', cities: ['Tehran', 'Isfahan', 'Mashhad', 'Tabriz', 'Shiraz'] },
  { name: 'Iraq', code: 'IQ', continent: 'Asia', region: 'Middle East', cities: ['Baghdad', 'Basra', 'Mosul', 'Kirkuk', 'Najaf'] },

  // Europe - Western Europe
  { name: 'France', code: 'FR', continent: 'Europe', region: 'Western Europe', cities: ['Paris', 'Marseille', 'Lyon', 'Toulouse', 'Nice'] },
  { name: 'Germany', code: 'DE', continent: 'Europe', region: 'Western Europe', cities: ['Berlin', 'Munich', 'Frankfurt', 'Cologne', 'Hamburg'] },
  { name: 'United Kingdom', code: 'GB', continent: 'Europe', region: 'Western Europe', cities: ['London', 'Manchester', 'Birmingham', 'Leeds', 'Glasgow'] },
  { name: 'Spain', code: 'ES', continent: 'Europe', region: 'Western Europe', cities: ['Madrid', 'Barcelona', 'Valencia', 'Seville', 'Bilbao'] },
  { name: 'Italy', code: 'IT', continent: 'Europe', region: 'Western Europe', cities: ['Rome', 'Milan', 'Naples', 'Turin', 'Venice'] },
  { name: 'Netherlands', code: 'NL', continent: 'Europe', region: 'Western Europe', cities: ['Amsterdam', 'Rotterdam', 'The Hague', 'Utrecht', 'Eindhoven'] },
  { name: 'Belgium', code: 'BE', continent: 'Europe', region: 'Western Europe', cities: ['Brussels', 'Antwerp', 'Ghent', 'Charleroi', 'Liège'] },
  { name: 'Switzerland', code: 'CH', continent: 'Europe', region: 'Western Europe', cities: ['Zurich', 'Geneva', 'Basel', 'Bern', 'Lausanne'] },
  { name: 'Austria', code: 'AT', continent: 'Europe', region: 'Western Europe', cities: ['Vienna', 'Graz', 'Linz', 'Salzburg', 'Innsbruck'] },

  // Europe - Northern Europe
  { name: 'Sweden', code: 'SE', continent: 'Europe', region: 'Northern Europe', cities: ['Stockholm', 'Gothenburg', 'Malmö', 'Uppsala', 'Västerås'] },
  { name: 'Norway', code: 'NO', continent: 'Europe', region: 'Northern Europe', cities: ['Oslo', 'Bergen', 'Trondheim', 'Stavanger', 'Kristiansand'] },
  { name: 'Denmark', code: 'DK', continent: 'Europe', region: 'Northern Europe', cities: ['Copenhagen', 'Aarhus', 'Odense', 'Aalborg', 'Esbjerg'] },
  { name: 'Finland', code: 'FI', continent: 'Europe', region: 'Northern Europe', cities: ['Helsinki', 'Espoo', 'Tampere', 'Vantaa', 'Turku'] },
  { name: 'Iceland', code: 'IS', continent: 'Europe', region: 'Northern Europe', cities: ['Reykjavik', 'Kópavogur', 'Hafnarfjörður', 'Akranes', 'Hveragerði'] },
  { name: 'Ireland', code: 'IE', continent: 'Europe', region: 'Northern Europe', cities: ['Dublin', 'Cork', 'Limerick', 'Galway', 'Waterford'] },

  // Europe - Eastern Europe
  { name: 'Poland', code: 'PL', continent: 'Europe', region: 'Eastern Europe', cities: ['Warsaw', 'Krakow', 'Wroclaw', 'Poznan', 'Gdansk'] },
  { name: 'Czech Republic', code: 'CZ', continent: 'Europe', region: 'Eastern Europe', cities: ['Prague', 'Brno', 'Ostrava', 'Plzen', 'Liberec'] },
  { name: 'Slovakia', code: 'SK', continent: 'Europe', region: 'Eastern Europe', cities: ['Bratislava', 'Kosice', 'Presov', 'Zilina', 'Banska Bystrica'] },
  { name: 'Hungary', code: 'HU', continent: 'Europe', region: 'Eastern Europe', cities: ['Budapest', 'Debrecen', 'Szeged', 'Miskolc', 'Pecs'] },
  { name: 'Romania', code: 'RO', continent: 'Europe', region: 'Eastern Europe', cities: ['Bucharest', 'Cluj-Napoca', 'Timisoara', 'Iasi', 'Constanta'] },
  { name: 'Bulgaria', code: 'BG', continent: 'Europe', region: 'Eastern Europe', cities: ['Sofia', 'Plovdiv', 'Varna', 'Burgas', 'Ruse'] },

  // Americas - North America
  { name: 'United States', code: 'US', continent: 'North America', region: 'North America', cities: ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix'] },
  { name: 'Canada', code: 'CA', continent: 'North America', region: 'North America', cities: ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa'] },
  { name: 'Mexico', code: 'MX', continent: 'North America', region: 'North America', cities: ['Mexico City', 'Guadalajara', 'Monterrey', 'Cancun', 'Playa del Carmen'] },

  // Americas - South America
  { name: 'Brazil', code: 'BR', continent: 'South America', region: 'South America', cities: ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Salvador', 'Fortaleza'] },
  { name: 'Colombia', code: 'CO', continent: 'South America', region: 'South America', cities: ['Bogotá', 'Medellín', 'Cali', 'Barranquilla', 'Cartagena'] },
  { name: 'Argentina', code: 'AR', continent: 'South America', region: 'South America', cities: ['Buenos Aires', 'Córdoba', 'Rosario', 'Mendoza', 'La Plata'] },
  { name: 'Chile', code: 'CL', continent: 'South America', region: 'South America', cities: ['Santiago', 'Valparaíso', 'Concepción', 'La Serena', 'Temuco'] },
  { name: 'Peru', code: 'PE', continent: 'South America', region: 'South America', cities: ['Lima', 'Arequipa', 'Cusco', 'Trujillo', 'Iquitos'] },
  { name: 'Ecuador', code: 'EC', continent: 'South America', region: 'South America', cities: ['Quito', 'Guayaquil', 'Cuenca', 'Santo Domingo', 'Ambato'] },
  { name: 'Venezuela', code: 'VE', continent: 'South America', region: 'South America', cities: ['Caracas', 'Maracaibo', 'Valencia', 'Barquisimeto', 'Ciudad Guayana'] },

  // Oceania
  { name: 'Australia', code: 'AU', continent: 'Oceania', region: 'Oceania', cities: ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide'] },
  { name: 'New Zealand', code: 'NZ', continent: 'Oceania', region: 'Oceania', cities: ['Auckland', 'Wellington', 'Christchurch', 'Hamilton', 'Tauranga'] },
  { name: 'Fiji', code: 'FJ', continent: 'Oceania', region: 'Oceania', cities: ['Suva', 'Nadi', 'Lautoka', 'Labasa', 'Ba'] },
]

export function getCountries(): CountryData[] {
  return COUNTRIES_DATA.sort((a, b) => a.name.localeCompare(b.name))
}

export function getCountryByCode(code: string): CountryData | undefined {
  return COUNTRIES_DATA.find(c => c.code === code)
}

export function getCitiesByCountryCode(code: string): string[] {
  const country = getCountryByCode(code)
  return country?.cities || []
}
