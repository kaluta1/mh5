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
export function getCitiesByCountry(countryCode: string): string[] {
  // Validate input
  if (!countryCode || typeof countryCode !== 'string') {
    console.warn(`[getCitiesByCountry] Invalid country code provided: ${countryCode}`)
    return []
  }
  
  // Normalize country code to uppercase
  const normalizedCode = countryCode.trim().toUpperCase()
  
  // Validate country code format
  if (!/^[A-Z]{2}$/.test(normalizedCode)) {
    console.warn(`[getCitiesByCountry] Invalid country code format: ${normalizedCode}`)
    return []
  }
  
  // CRITICAL: If requesting Tanzania, return early to avoid any filtering issues
  if (normalizedCode === 'TZ') {
    const tzCities = ['Dar es Salaam', 'Mwanza', 'Arusha', 'Dodoma', 'Mbeya', 'Zanzibar City', 'Morogoro', 'Tanga', 'Mtwara', 'Tabora', 'Kigoma', 'Iringa', 'Songea', 'Shinyanga', 'Musoma', 'Bukoba', 'Sumbawanga', 'Singida', 'Lindi', 'Moshi', 'Kilimanjaro', 'Bagamoyo', 'Pemba', 'Unguja', 'Stone Town', 'Kibaha', 'Ifakara', 'Mpanda', 'Kasulu', 'Njombe', 'Babati', 'Geita', 'Kahama', 'Same', 'Korogwe', 'Handeni']
    console.log(`[getCitiesByCountry] Returning Tanzania cities for TZ`)
    return Array.from(tzCities)
  }
  
  // Complete list of Tanzania cities to filter out
  const TANZANIA_CITIES = new Set([
    'Dar es Salaam', 'Mwanza', 'Arusha', 'Dodoma', 'Mbeya', 'Zanzibar City', 
    'Morogoro', 'Tanga', 'Mtwara', 'Tabora', 'Kigoma', 'Iringa', 
    'Songea', 'Shinyanga', 'Musoma', 'Bukoba', 'Sumbawanga', 'Singida', 
    'Lindi', 'Moshi', 'Kilimanjaro', 'Bagamoyo', 'Pemba', 'Unguja', 
    'Stone Town', 'Kibaha', 'Ifakara', 'Mpanda', 'Kasulu', 'Njombe', 
    'Babati', 'Geita', 'Kahama', 'Same', 'Korogwe', 'Handeni'
  ])
  
  // Liste complète des villes principales par code pays
  const citiesByCountry: Record<string, string[]> = {
    // Africa
    'DZ': ['Algiers', 'Oran', 'Constantine', 'Annaba', 'Blida', 'Batna', 'Djelfa', 'Sétif', 'Sidi Bel Abbès', 'Biskra', 'Tébessa', 'Tlemcen', 'Béjaïa', 'Bordj Bou Arréridj', 'Mostaganem', 'M\'Sila', 'Tiaret', 'Ouargla', 'Guelma', 'Chlef', 'Laghouat', 'Mascara', 'Jijel', 'Skikda', 'Tizi Ouzou', 'Médéa', 'Relizane', 'Saïda', 'Mila', 'Aïn Temouchent', 'Ghardaïa', 'El Oued', 'Boumerdès', 'Khenchela', 'Souk Ahras', 'Tipaza', 'Mila', 'Aïn Defla', 'Naâma', 'Tamanrasset', 'El Bayadh', 'Illizi', 'Bordj Badji Mokhtar', 'Ouled Djellal', 'Béni Abbès', 'Timimoun', 'Adrar', 'Aoulef', 'Reggane', 'In Salah', 'Djanet'],
    'AO': ['Luanda', 'Huambo', 'Lobito', 'Benguela', 'Lubango', 'Kuito', 'Malanje', 'Namibe', 'Soyo', 'Cabinda', 'Uíge', 'Sumbe', 'Menongue', 'Luena', 'N\'dalatando', 'Ondjiva', 'Mbanza Kongo', 'Dundo', 'Saurimo', 'Caxito', 'M\'banza-Kongo', 'N\'zeto', 'Cuito', 'Chitato', 'Lucapa', 'Dundo', 'Saurimo', 'Caxito', 'M\'banza-Kongo', 'N\'zeto', 'Cuito', 'Chitato', 'Lucapa'],
    'BJ': ['Cotonou', 'Porto-Novo', 'Parakou', 'Djougou', 'Abomey', 'Natitingou', 'Lokossa', 'Ouidah', 'Kandi', 'Bohicon', 'Abomey-Calavi', 'Sakété', 'Kétou', 'Comé', 'Allada', 'Aplahoué', 'Bassila', 'Bembèrèkè', 'Dassa-Zoumé', 'Dogbo', 'Grand-Popo', 'Kouandé', 'Malanville', 'Nikki', 'Pobé', 'Savalou', 'Tanguiéta', 'Tchaourou', 'Zogbodomey', 'Banikoara', 'Boukoumbé', 'Cobly', 'Copargo', 'Djakotomey', 'Gogounou', 'Karimama', 'Kouandé', 'Malanville', 'N\'Dali', 'Nikki', 'Péhunco', 'Ségbana', 'Sinendé', 'Tanguiéta', 'Tchaourou'],
    'BW': ['Gaborone', 'Francistown', 'Molepolole', 'Serowe', 'Maun', 'Mogoditshane', 'Palapye', 'Selibe Phikwe', 'Tlokweng', 'Ramotswa', 'Mochudi', 'Kanye', 'Mahalapye', 'Moshupa', 'Lobatse', 'Tutume', 'Jwaneng', 'Orapa', 'Sowa Town', 'Letlhakane', 'Tonota', 'Masunga', 'Nata', 'Kasane', 'Ghanzi', 'Tshabong', 'Hukuntsi', 'Kang', 'Tsau', 'Shakawe', 'Gumare', 'Nokaneng', 'Toteng', 'Sehithwa', 'Shorobe', 'Etsha', 'Gudigwa', 'Seronga', 'Kachikau', 'Kazungula', 'Pandamatenga', 'Lephepe', 'Lentswe-le-Tau', 'Mmathubudukwane', 'Mogoditshane', 'Palapye', 'Selibe Phikwe', 'Tlokweng', 'Ramotswa', 'Mochudi', 'Kanye', 'Mahalapye', 'Moshupa', 'Lobatse', 'Tutume', 'Jwaneng', 'Orapa', 'Sowa Town', 'Letlhakane', 'Tonota', 'Masunga', 'Nata', 'Kasane', 'Ghanzi', 'Tshabong', 'Hukuntsi', 'Kang', 'Tsau', 'Shakawe', 'Gumare', 'Nokaneng', 'Toteng', 'Sehithwa', 'Shorobe', 'Etsha', 'Gudigwa', 'Seronga', 'Kachikau', 'Kazungula', 'Pandamatenga', 'Lephepe', 'Lentswe-le-Tau', 'Mmathubudukwane'],
    'BF': ['Ouagadougou', 'Bobo-Dioulasso', 'Koudougou', 'Ouahigouya', 'Banfora', 'Kaya', 'Tenkodogo', 'Fada N\'gourma', 'Dédougou', 'Dori', 'Gaoua', 'Koupéla', 'Manga', 'Nouna', 'Pô', 'Réo', 'Sapouy', 'Zorgho', 'Bogandé', 'Boulsa', 'Boussé', 'Garango', 'Gourcy', 'Houndé', 'Kombissiri', 'Kongoussi', 'Koudougou', 'Koupéla', 'Léo', 'Manga', 'Niangoloko', 'Nouna', 'Orodara', 'Ouahigouya', 'Pama', 'Pô', 'Pouytenga', 'Réo', 'Sapouy', 'Séguénéga', 'Titao', 'Tougan', 'Yako', 'Ziniaré', 'Zorgho', 'Bogandé', 'Boulsa', 'Boussé', 'Garango', 'Gourcy', 'Houndé', 'Kombissiri', 'Kongoussi', 'Koudougou', 'Koupéla', 'Léo', 'Manga', 'Niangoloko', 'Nouna', 'Orodara', 'Ouahigouya', 'Pama', 'Pô', 'Pouytenga', 'Réo', 'Sapouy', 'Séguénéga', 'Titao', 'Tougan', 'Yako', 'Ziniaré', 'Zorgho'],
    'BI': ['Bujumbura', 'Gitega', 'Muyinga', 'Ruyigi', 'Ngozi', 'Rutana', 'Bururi', 'Makamba', 'Muramvya', 'Karuzi', 'Kayanza', 'Kirundo', 'Cibitoke', 'Bubanza', 'Rumonge', 'Isale', 'Mwaro', 'Gihanga', 'Muhanga', 'Kibuye', 'Kiganda', 'Kinyinya', 'Kiremba', 'Matana', 'Mugamba', 'Muyinga', 'Ngozi', 'Rutana', 'Ruyigi', 'Rutovu', 'Ruyigi', 'Rutovu', 'Ruyigi'],
    'CM': ['Douala', 'Yaoundé', 'Garoua', 'Bafoussam', 'Bamenda', 'Buea', 'Limbe', 'Kribi', 'Ebolowa', 'Sangmélima', 'Mbalmayo', 'Edea', 'Kumba', 'Bafang', 'Foumban', 'Dschang', 'Mbouda', 'Bangangté', 'Bafoussam', 'Foumbot', 'Koutaba', 'Bandjoun', 'Bafang', 'Dschang', 'Mbouda', 'Bangangté', 'Bafoussam', 'Foumbot', 'Koutaba', 'Bandjoun', 'Bafang', 'Dschang', 'Mbouda', 'Bangangté', 'Bafoussam', 'Foumbot', 'Koutaba', 'Bandjoun'],
    'CV': ['Praia', 'Mindelo', 'Santa Maria', 'São Filipe', 'Assomada', 'Cidade Velha', 'Tarrafal', 'Ribeira Grande', 'Porto Novo', 'Vila do Maio', 'Sal Rei', 'Vila Nova Sintra', 'Pombas', 'Pedra Badejo', 'Calheta', 'Cova Figueira', 'Mosteiros', 'São Domingos', 'Ribeira Brava', 'Espargos', 'Santa Cruz', 'Picos', 'São Miguel', 'Tarrafal de São Nicolau', 'Ribeira da Prata', 'Ribeira Grande', 'Porto Novo', 'Vila do Maio', 'Sal Rei', 'Vila Nova Sintra', 'Pombas', 'Pedra Badejo', 'Calheta', 'Cova Figueira', 'Mosteiros', 'São Domingos', 'Ribeira Brava', 'Espargos', 'Santa Cruz', 'Picos', 'São Miguel', 'Tarrafal de São Nicolau', 'Ribeira da Prata'],
    'CF': ['Bangui', 'Bimbo', 'Berbérati', 'Carnot', 'Bambari', 'Bouar', 'Bossangoa', 'Bria', 'Bangassou', 'Mbaïki', 'Bozoum', 'Kaga-Bandoro', 'Sibut', 'Nola', 'Birao', 'Obo', 'Zémio', 'Bakouma', 'Alindao', 'Mobaye', 'Rafai', 'Gambo', 'Ouadda', 'Bakouma', 'Alindao', 'Mobaye', 'Rafai', 'Gambo', 'Ouadda', 'Bakouma', 'Alindao', 'Mobaye', 'Rafai', 'Gambo', 'Ouadda'],
    'TD': ['N\'Djamena', 'Moundou', 'Sarh', 'Abéché', 'Kelo', 'Koumra', 'Pala', 'Am Timan', 'Bongor', 'Mongo', 'Doba', 'Ati', 'Laï', 'Oum Hadjer', 'Am Dam', 'Biltine', 'Faya-Largeau', 'Fada', 'Goz Beïda', 'Massakory', 'Massaguet', 'Moussoro', 'N\'Djamena', 'Oum Hadjer', 'Pala', 'Sarh', 'Zouar', 'Abéché', 'Adré', 'Am Dam', 'Am Timan', 'Ati', 'Biltine', 'Bokoro', 'Bongor', 'Doba', 'Fada', 'Faya-Largeau', 'Goz Beïda', 'Kelo', 'Koumra', 'Laï', 'Mao', 'Massakory', 'Massaguet', 'Mongo', 'Moussoro', 'Moundou', 'Oum Hadjer', 'Pala', 'Sarh', 'Zouar'],
    'KM': ['Moroni', 'Mutsamudu', 'Fomboni', 'Domoni', 'Tsimbeo', 'Ouani', 'Mitsamiouli', 'Iconi', 'Nioumachoua', 'M\'Ramani', 'Hajoho', 'Moya', 'M\'Réni', 'M\'Ramani', 'Hajoho', 'Moya', 'M\'Réni', 'M\'Ramani', 'Hajoho', 'Moya', 'M\'Réni'],
    'CG': ['Brazzaville', 'Pointe-Noire', 'Dolisie', 'Kayes', 'Owando', 'Nkayi', 'Loandjili', 'Mossendjo', 'Ouesso', 'Impfondo', 'Sibiti', 'Lékana', 'Gamboma', 'Djambala', 'Ewo', 'Makoua', 'Ollombo', 'Kinkala', 'Mindouli', 'Madingou', 'Bouansa', 'Mossendjo', 'Nkayi', 'Loandjili', 'Mossendjo', 'Ouesso', 'Impfondo', 'Sibiti', 'Lékana', 'Gamboma', 'Djambala', 'Ewo', 'Makoua', 'Ollombo', 'Kinkala', 'Mindouli', 'Madingou', 'Bouansa', 'Mossendjo', 'Nkayi', 'Loandjili'],
    'CD': ['Kinshasa', 'Lubumbashi', 'Mbuji-Mayi', 'Kananga', 'Kisangani', 'Bukavu', 'Goma', 'Kikwit', 'Mbandaka', 'Matadi', 'Kolwezi', 'Likasi', 'Bunia', 'Uvira', 'Butembo', 'Kalemie', 'Kindu', 'Isiro', 'Boma', 'Mbanza-Ngungu', 'Tshikapa', 'Kabinda', 'Kamina', 'Kisangani', 'Lubumbashi', 'Mbuji-Mayi', 'Kananga', 'Kikwit', 'Mbandaka', 'Matadi', 'Kolwezi', 'Likasi', 'Bunia', 'Uvira', 'Butembo', 'Kalemie', 'Kindu', 'Isiro', 'Boma', 'Mbanza-Ngungu', 'Tshikapa', 'Kabinda', 'Kamina', 'Kisangani', 'Lubumbashi', 'Mbuji-Mayi', 'Kananga', 'Kikwit', 'Mbandaka', 'Matadi', 'Kolwezi', 'Likasi', 'Bunia', 'Uvira', 'Butembo', 'Kalemie', 'Kindu', 'Isiro', 'Boma', 'Mbanza-Ngungu', 'Tshikapa', 'Kabinda', 'Kamina'],
    'CI': ['Abidjan', 'Yamoussoukro', 'Bouaké', 'Daloa', 'San-Pédro', 'Korhogo', 'Man', 'Divo', 'Gagnoa', 'Abengourou', 'Grand-Bassam', 'Agboville', 'Dabou', 'Bingerville', 'Anyama', 'Cocody', 'Marcory', 'Yopougon', 'Adjamé', 'Attécoubé', 'Plateau', 'Treichville', 'Koumassi', 'Port-Bouët', 'Abobo', 'Songon', 'Bonoua', 'Tiassalé', 'Sikensi', 'Lakota', 'Oumé', 'Gagnoa', 'Divo', 'Lakota', 'Oumé', 'Gagnoa', 'Divo', 'Lakota', 'Oumé', 'Gagnoa', 'Divo', 'Lakota', 'Oumé'],
    'DJ': ['Djibouti', 'Ali Sabieh', 'Tadjoura', 'Obock', 'Dikhil', 'Arta', 'Dorra', 'Holhol', 'Loyada', 'Randa', 'Yoboki', 'Goubetto', 'Goubetto', 'Goubetto'],
    'EG': ['Cairo', 'Alexandria', 'Giza', 'Shubra El-Khema', 'Helwan', 'Luxor', 'Aswan', 'Port Said', 'Suez', 'Tanta', 'Asyut', 'Ismailia', 'Faiyum', 'Zagazig', 'Damietta', 'Aswan', 'Minya', 'Damanhur', 'Beni Suef', 'Qena', 'Sohag', 'Hurghada', 'Sharm El Sheikh', 'Marsa Alam', 'El Arish', 'Ras Ghareb', 'Safaga', 'Qusair', 'Marsa Matruh', 'Siwa', 'Bahariya', 'Farafra', 'Dakhla', 'Kharga', 'New Valley', 'El Minya', 'Mallawi', 'Abu Qurqas', 'Maghagha', 'Beni Mazar', 'Samalut', 'Matai', 'Tima', 'Ashmoun', 'Shibin El Kom', 'Menouf', 'Quesna', 'Berket El Saba', 'Tala', 'Kafr El Zayat', 'Zefta', 'Mahalla El Kubra', 'Kafr El Sheikh', 'Desouk', 'Baltim', 'Ras El Bar', 'El Mansoura', 'Talkha', 'Mit Ghamr', 'Aga', 'Dikirnis', 'El Senbellawein', 'El Matareya', 'El Gamaliya', 'El Manzala', 'El Qanater El Khayreya', 'Shubra El Kheima', 'Qalyub', 'Banha', 'Toukh', 'Quesna', 'Tanta', 'Kafr El Sheikh', 'Desouk', 'Fuwa', 'Biyala', 'El Hamoul', 'Sidi Salem', 'El Reyad', 'El Hamam', 'Baltim', 'Ras El Bar', 'El Burullus', 'El Matareya', 'El Gamaliya', 'El Manzala', 'El Qanater El Khayreya', 'Shubra El Kheima', 'Qalyub', 'Banha', 'Toukh', 'Quesna'],
    'GQ': ['Malabo', 'Bata', 'Ebebiyín', 'Aconibe', 'Añisoc', 'Mongomo', 'Evinayong', 'Luba', 'Mbini', 'Nsok', 'Anisok', 'Niefang', 'Bicurga', 'Mikomeseng', 'Nkimi', 'Nsang', 'Nsok-Nsomo', 'Río Campo', 'Río Muni', 'San Antonio de Palé', 'Valladolid de los Bimbiles', 'Valladolid de los Bimbiles', 'Valladolid de los Bimbiles'],
    'ER': ['Asmara', 'Keren', 'Massawa', 'Assab', 'Mendefera', 'Adi Keyh', 'Agordat', 'Barentu', 'Dekemhare', 'Edd', 'Ghinda', 'Mai-Mne', 'Nakfa', 'Teseney', 'Tio', 'Zula', 'Adi Quala', 'Adi Tekelezan', 'Afabet', 'Barentu', 'Dekemhare', 'Edd', 'Ghinda', 'Mai-Mne', 'Nakfa', 'Teseney', 'Tio', 'Zula', 'Adi Quala', 'Adi Tekelezan', 'Afabet', 'Barentu', 'Dekemhare', 'Edd', 'Ghinda', 'Mai-Mne', 'Nakfa', 'Teseney', 'Tio', 'Zula'],
    'SZ': ['Mbabane', 'Manzini', 'Big Bend', 'Malkerns', 'Nhlangano', 'Siteki', 'Piggs Peak', 'Lobamba', 'Mhlume', 'Matsapha', 'Kwaluseni', 'Malkerns', 'Bhunya', 'Hlatikulu', 'Lavumisa', 'Nhlangano', 'Sidvokodvo', 'Siphofaneni', 'Tshaneni', 'Vuvulane', 'Ezulwini', 'Malkerns', 'Bhunya', 'Hlatikulu', 'Lavumisa', 'Nhlangano', 'Sidvokodvo', 'Siphofaneni', 'Tshaneni', 'Vuvulane', 'Ezulwini', 'Malkerns', 'Bhunya', 'Hlatikulu', 'Lavumisa', 'Nhlangano', 'Sidvokodvo', 'Siphofaneni', 'Tshaneni', 'Vuvulane', 'Ezulwini'],
    'ET': ['Addis Ababa', 'Dire Dawa', 'Mekele', 'Gondar', 'Awassa', 'Bahir Dar', 'Dessie', 'Jimma', 'Jijiga', 'Shashamane', 'Arba Minch', 'Hosaena', 'Harar', 'Dila', 'Nekemte', 'Debre Markos', 'Asella', 'Sodo', 'Goba', 'Adama', 'Hawassa', 'Wolaita Sodo', 'Debre Birhan', 'Kombolcha', 'Gode', 'Jinka', 'Mekelle', 'Semera', 'Gambela', 'Assosa', 'Bahir Dar', 'Dessie', 'Jimma', 'Jijiga', 'Shashamane', 'Arba Minch', 'Hosaena', 'Harar', 'Dila', 'Nekemte', 'Debre Markos', 'Asella', 'Sodo', 'Goba', 'Adama', 'Hawassa', 'Wolaita Sodo', 'Debre Birhan', 'Kombolcha', 'Gode', 'Jinka', 'Mekelle', 'Semera', 'Gambela', 'Assosa'],
    'GA': ['Libreville', 'Port-Gentil', 'Franceville', 'Oyem', 'Moanda', 'Mouila', 'Tchibanga', 'Koulamoutou', 'Lastoursville', 'Gamba', 'Makokou', 'Lambaréné', 'Bitam', 'Mitzic', 'Okondja', 'Ndjolé', 'Fougamou', 'Mbigou', 'Mimongo', 'Mouila', 'Tchibanga', 'Koulamoutou', 'Lastoursville', 'Gamba', 'Makokou', 'Lambaréné', 'Bitam', 'Mitzic', 'Okondja', 'Ndjolé', 'Fougamou', 'Mbigou', 'Mimongo', 'Mouila', 'Tchibanga', 'Koulamoutou', 'Lastoursville', 'Gamba', 'Makokou', 'Lambaréné', 'Bitam', 'Mitzic', 'Okondja', 'Ndjolé', 'Fougamou', 'Mbigou', 'Mimongo'],
    'GM': ['Banjul', 'Serekunda', 'Brikama', 'Bakau', 'Farafenni', 'Basse Santa Su', 'Gunjur', 'Sukuta', 'Brufut', 'Lamin', 'Bakoteh', 'Fajara', 'Kotu', 'Kololi', 'Bijilo', 'Tanji', 'Kartong', 'Gunjur', 'Sanyang', 'Tujereng', 'Kartong', 'Gunjur', 'Sanyang', 'Tujereng', 'Kartong', 'Gunjur', 'Sanyang', 'Tujereng'],
    'GH': ['Accra', 'Kumasi', 'Tamale', 'Sekondi', 'Cape Coast', 'Sunyani', 'Obuasi', 'Teshie', 'Tema', 'Ashaiman', 'Takoradi', 'Bolgatanga', 'Ho', 'Koforidua', 'Wa', 'Techiman', 'Nkawkaw', 'Sefwi Wiawso', 'Goaso', 'Berekum', 'Dunkwa-on-Offin', 'Bibiani', 'Axim', 'Elmina', 'Winneba', 'Kasoa', 'Mampong', 'Konongo', 'Ejura', 'Agogo', 'Mpraeso', 'Abetifi', 'Kibi', 'Nsawam', 'Dodowa', 'Madina', 'Tema', 'Ashaiman', 'Nungua', 'Teshie', 'Labadi', 'Osu', 'Cantonments', 'East Legon', 'West Legon', 'Dansoman', 'Kokomlemle', 'Adabraka', 'Kaneshie', 'Mamprobi', 'Chorkor', 'Jamestown', 'Ussher Town', 'Osu', 'Labadi', 'Teshie', 'Nungua', 'Tema', 'Ashaiman', 'Madina', 'Dodowa', 'Nsawam', 'Aburi', 'Mampong', 'Koforidua', 'Nkawkaw', 'Konongo', 'Ejura', 'Agogo', 'Mpraeso', 'Abetifi', 'Kibi', 'Kumasi', 'Obuasi', 'Tafo', 'Asokwa', 'Suame', 'Bantama', 'Manhyia', 'Asafo', 'Adum', 'Kejetia', 'Bantama', 'Manhyia', 'Asafo', 'Adum', 'Kejetia'],
    'GN': ['Conakry', 'Nzérékoré', 'Kindia', 'Kankan', 'Mamou', 'Labé', 'Kissidougou', 'Faranah', 'Siguiri', 'Boké', 'Guéckédou', 'Macenta', 'Kouroussa', 'Télimélé', 'Pita', 'Dalaba', 'Lola', 'Yomou', 'Beyla', 'Mandiana', 'Kérouané', 'Dabola', 'Dinguiraye', 'Fria', 'Gaoual', 'Koundara', 'Koubia', 'Lélouma', 'Mali', 'Tougué', 'Labé', 'Kissidougou', 'Faranah', 'Siguiri', 'Boké', 'Guéckédou', 'Macenta', 'Kouroussa', 'Télimélé', 'Pita', 'Dalaba', 'Lola', 'Yomou', 'Beyla', 'Mandiana', 'Kérouané', 'Dabola', 'Dinguiraye', 'Fria', 'Gaoual', 'Koundara', 'Koubia', 'Lélouma', 'Mali', 'Tougué'],
    'GW': ['Bissau', 'Bafatá', 'Gabú', 'Bissorã', 'Bolama', 'Cacheu', 'Catió', 'Farim', 'Mansôa', 'Buba', 'Canchungo', 'Fulacunda', 'Quebo', 'São Domingos', 'Bissorã', 'Bolama', 'Cacheu', 'Catió', 'Farim', 'Mansôa', 'Buba', 'Canchungo', 'Fulacunda', 'Quebo', 'São Domingos', 'Bissorã', 'Bolama', 'Cacheu', 'Catió', 'Farim', 'Mansôa', 'Buba', 'Canchungo', 'Fulacunda', 'Quebo', 'São Domingos'],
    'KE': ['Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret', 'Thika', 'Malindi', 'Kitale', 'Garissa', 'Kakamega', 'Kisii', 'Meru', 'Nyeri', 'Machakos', 'Embu', 'Narok', 'Kericho', 'Bungoma', 'Busia', 'Homa Bay', 'Migori', 'Siaya', 'Vihiga', 'Bomet', 'Nyamira', 'Kilifi', 'Kwale', 'Lamu', 'Tana River', 'Taita-Taveta', 'Makueni', 'Kitui', 'Marsabit', 'Isiolo', 'Mandera', 'Wajir', 'Turkana', 'West Pokot', 'Samburu', 'Trans Nzoia', 'Uasin Gishu', 'Nandi', 'Baringo', 'Laikipia', 'Nakuru', 'Bomet', 'Nyandarua', 'Murang\'a', 'Kiambu', 'Kirinyaga', 'Nyeri', 'Nyeri', 'Laikipia', 'Nyeri', 'Nyeri', 'Nyeri'],
    'LS': ['Maseru', 'Teyateyaneng', 'Mafeteng', 'Hlotse', 'Mohale\'s Hoek', 'Maputsoe', 'Quthing', 'Butha-Buthe', 'Mokhotlong', 'Thaba-Tseka', 'Qacha\'s Nek', 'Semonkong', 'Roma', 'Teyateyaneng', 'Mafeteng', 'Hlotse', 'Mohale\'s Hoek', 'Maputsoe', 'Quthing', 'Butha-Buthe', 'Mokhotlong', 'Thaba-Tseka', 'Qacha\'s Nek', 'Semonkong', 'Roma', 'Teyateyaneng', 'Mafeteng', 'Hlotse', 'Mohale\'s Hoek', 'Maputsoe', 'Quthing', 'Butha-Buthe', 'Mokhotlong', 'Thaba-Tseka', 'Qacha\'s Nek', 'Semonkong', 'Roma'],
    'LR': ['Monrovia', 'Gbarnga', 'Buchanan', 'Ganta', 'Kakata', 'Harper', 'Voinjama', 'Zwedru', 'Greenville', 'Robertsport', 'Sanniquellie', 'Tubmanburg', 'Barclayville', 'Fish Town', 'River Cess', 'Buchanan', 'Gbarnga', 'Ganta', 'Harper', 'Kakata', 'Monrovia', 'Robertsport', 'Sanniquellie', 'Tubmanburg', 'Voinjama', 'Zwedru', 'Barclayville', 'Fish Town', 'River Cess', 'Buchanan', 'Gbarnga', 'Ganta', 'Harper', 'Kakata', 'Monrovia', 'Robertsport', 'Sanniquellie', 'Tubmanburg', 'Voinjama', 'Zwedru', 'Barclayville', 'Fish Town', 'River Cess'],
    'LY': ['Tripoli', 'Benghazi', 'Misrata', 'Bayda', 'Zawiya', 'Sabha', 'Sirte', 'Tarhuna', 'Khoms', 'Zintan', 'Yafran', 'Gharyan', 'Murzuq', 'Ghat', 'Kufra', 'Tobruk', 'Derna', 'Ajdabiya', 'Sabhā', 'Bani Walid', 'Zliten', 'Tajura', 'Al Khums', 'Al Marj', 'Al Bayda', 'Al Qubbah', 'Awbari', 'Brak', 'Ghadames', 'Hun', 'Jalu', 'Jufra', 'Kufra', 'Nalut', 'Sabha', 'Surt', 'Tazirbu', 'Tripoli', 'Benghazi', 'Misrata', 'Bayda', 'Zawiya', 'Sabha', 'Sirte', 'Tarhuna', 'Khoms', 'Zintan', 'Yafran', 'Gharyan', 'Murzuq', 'Ghat', 'Kufra', 'Tobruk', 'Derna', 'Ajdabiya', 'Sabhā', 'Bani Walid', 'Zliten', 'Tajura', 'Al Khums', 'Al Marj', 'Al Bayda', 'Al Qubbah', 'Awbari', 'Brak', 'Ghadames', 'Hun', 'Jalu', 'Jufra', 'Kufra', 'Nalut', 'Sabha', 'Surt', 'Tazirbu'],
    'MG': ['Antananarivo', 'Toamasina', 'Antsirabe', 'Mahajanga', 'Fianarantsoa', 'Toliara', 'Antsiranana', 'Mahajanga', 'Ambovombe', 'Ambanja', 'Ambatondrazaka', 'Ambilobe', 'Amboasary', 'Andapa', 'Antalaha', 'Antanifotsy', 'Arivonimamo', 'Betioky', 'Farafangana', 'Fenoarivo', 'Fort Dauphin', 'Manakara', 'Mananjary', 'Maroantsetra', 'Miandrivazo', 'Moramanga', 'Morondava', 'Nosy Be', 'Sambava', 'Soavinandriana', 'Tôlanaro', 'Vatomandry', 'Vohipeno', 'Vohibinany', 'Antananarivo', 'Toamasina', 'Antsirabe', 'Mahajanga', 'Fianarantsoa', 'Toliara', 'Antsiranana', 'Mahajanga', 'Ambovombe', 'Ambanja', 'Ambatondrazaka', 'Ambilobe', 'Amboasary', 'Andapa', 'Antalaha', 'Antanifotsy', 'Arivonimamo', 'Betioky', 'Farafangana', 'Fenoarivo', 'Fort Dauphin', 'Manakara', 'Mananjary', 'Maroantsetra', 'Miandrivazo', 'Moramanga', 'Morondava', 'Nosy Be', 'Sambava', 'Soavinandriana', 'Tôlanaro', 'Vatomandry', 'Vohipeno', 'Vohibinany'],
    'MW': ['Lilongwe', 'Blantyre', 'Mzuzu', 'Zomba', 'Kasungu', 'Mangochi', 'Karonga', 'Salima', 'Nkhotakota', 'Liwonde', 'Nsanje', 'Rumphi', 'Mzimba', 'Dedza', 'Ntcheu', 'Mchinji', 'Dowa', 'Ntchisi', 'Mchinji', 'Dowa', 'Ntchisi', 'Mchinji', 'Dowa', 'Ntchisi'],
    'ML': ['Bamako', 'Ségou', 'Mopti', 'Gao', 'Koulikoro', 'Kayes', 'Kidal', 'Timbuktu', 'Koutiala', 'Sikasso', 'Bougouni', 'Djenné', 'Kita', 'Nioro du Sahel', 'San', 'Tessalit', 'Yanfolila', 'Ansongo', 'Bandiagara', 'Banamba', 'Bourem', 'Diré', 'Douentza', 'Goundam', 'Kéniéba', 'Kolokani', 'Kolondiéba', 'Koro', 'Macina', 'Markala', 'Ménaka', 'Nara', 'Niafunké', 'Niono', 'Taoudenni', 'Ténenkou', 'Tominian', 'Yélimané', 'Bamako', 'Ségou', 'Mopti', 'Gao', 'Koulikoro', 'Kayes', 'Kidal', 'Timbuktu', 'Koutiala', 'Sikasso', 'Bougouni', 'Djenné', 'Kita', 'Nioro du Sahel', 'San', 'Tessalit', 'Yanfolila', 'Ansongo', 'Bandiagara', 'Banamba', 'Bourem', 'Diré', 'Douentza', 'Goundam', 'Kéniéba', 'Kolokani', 'Kolondiéba', 'Koro', 'Macina', 'Markala', 'Ménaka', 'Nara', 'Niafunké', 'Niono', 'Taoudenni', 'Ténenkou', 'Tominian', 'Yélimané'],
    'MR': ['Nouakchott', 'Nouadhibou', 'Rosso', 'Kaédi', 'Zouérat', 'Atar', 'Néma', 'Aleg', 'Kiffa', 'Tidjikja', 'Selibaby', 'Akjoujt', 'Boutilimit', 'Magta-Lahjar', 'Timbedra', 'Aioun', 'Barkéol', 'Bogué', 'Chinguetti', 'Fdérik', 'Guérou', 'Kankossa', 'M\'Bout', 'Nouadhibou', 'Nouakchott', 'Rosso', 'R\'Kiz', 'Sélibaby', 'Tidjikja', 'Timbedra', 'Zouérat', 'Atar', 'Néma', 'Aleg', 'Kiffa', 'Tidjikja', 'Selibaby', 'Akjoujt', 'Boutilimit', 'Magta-Lahjar', 'Timbedra', 'Aioun', 'Barkéol', 'Bogué', 'Chinguetti', 'Fdérik', 'Guérou', 'Kankossa', 'M\'Bout', 'Nouadhibou', 'Nouakchott', 'Rosso', 'R\'Kiz', 'Sélibaby', 'Tidjikja', 'Timbedra', 'Zouérat'],
    'MU': ['Port Louis', 'Beau Bassin-Rose Hill', 'Vacoas-Phoenix', 'Curepipe', 'Quatre Bornes', 'Triolet', 'Goodlands', 'Centre de Flacq', 'Bel Air', 'Mahébourg', 'Saint Pierre', 'Le Hochet', 'Rose Belle', 'Chemin Grenier', 'Rivière du Rempart', 'Grand Baie', 'Flic en Flac', 'Tamarin', 'Black River', 'Souillac', 'Mahebourg', 'Grand Gaube', 'Pamplemousses', 'Roches Noires', 'Poste de Flacq', 'Rivière des Anguilles', 'Chamarel', 'Case Noyale', 'La Gaulette', 'Baie du Cap', 'Port Louis', 'Beau Bassin-Rose Hill', 'Vacoas-Phoenix', 'Curepipe', 'Quatre Bornes', 'Triolet', 'Goodlands', 'Centre de Flacq', 'Bel Air', 'Mahébourg', 'Saint Pierre', 'Le Hochet', 'Rose Belle', 'Chemin Grenier', 'Rivière du Rempart', 'Grand Baie', 'Flic en Flac', 'Tamarin', 'Black River', 'Souillac', 'Mahebourg', 'Grand Gaube', 'Pamplemousses', 'Roches Noires', 'Poste de Flacq', 'Rivière des Anguilles', 'Chamarel', 'Case Noyale', 'La Gaulette', 'Baie du Cap'],
    'MA': ['Casablanca', 'Rabat', 'Fes', 'Marrakech', 'Tangier', 'Agadir', 'Meknes', 'Oujda', 'Kenitra', 'Tetouan', 'Safi', 'Mohammedia', 'Khouribga', 'El Jadida', 'Beni Mellal', 'Taza', 'Nador', 'Settat', 'Larache', 'Ksar el-Kebir', 'Guelmim', 'Berrechid', 'Fquih Ben Salah', 'Taourirt', 'Berkane', 'Sidi Slimane', 'Sidi Kacem', 'Tifelt', 'Sefrou', 'Youssoufia', 'Tan-Tan', 'Ouarzazate', 'Souk El Arbaa', 'Oulad Teima', 'Tiznit', 'Sidi Bennour', 'Larache', 'Ksar el-Kebir', 'Guelmim', 'Berrechid', 'Fquih Ben Salah', 'Taourirt', 'Berkane', 'Sidi Slimane', 'Sidi Kacem', 'Tifelt', 'Sefrou', 'Youssoufia', 'Tan-Tan', 'Ouarzazate', 'Souk El Arbaa', 'Oulad Teima', 'Tiznit', 'Sidi Bennour', 'Larache', 'Ksar el-Kebir', 'Guelmim', 'Berrechid', 'Fquih Ben Salah', 'Taourirt', 'Berkane', 'Sidi Slimane', 'Sidi Kacem', 'Tifelt', 'Sefrou', 'Youssoufia', 'Tan-Tan', 'Ouarzazate', 'Souk El Arbaa', 'Oulad Teima', 'Tiznit', 'Sidi Bennour'],
    'MZ': ['Maputo', 'Matola', 'Beira', 'Nampula', 'Chimoio', 'Nacala', 'Quelimane', 'Tete', 'Lichinga', 'Pemba', 'Xai-Xai', 'Inhambane', 'Maxixe', 'Dondo', 'Angoche', 'Montepuez', 'Cuamba', 'Mocuba', 'Gurue', 'Moatize', 'Manica', 'Chokwe', 'Macia', 'Vilankulo', 'Chibuto', 'Macia', 'Vilankulo', 'Chibuto', 'Macia', 'Vilankulo', 'Chibuto'],
    'NA': ['Windhoek', 'Walvis Bay', 'Swakopmund', 'Oshakati', 'Rundu', 'Katima Mulilo', 'Grootfontein', 'Rehoboth', 'Otjiwarongo', 'Okahandja', 'Keetmanshoop', 'Lüderitz', 'Mariental', 'Omaruru', 'Outjo', 'Tsumeb', 'Usakos', 'Karibib', 'Gobabis', 'Maltahöhe', 'Bethanie', 'Karasburg', 'Aranos', 'Stampriet', 'Aranos', 'Stampriet', 'Aranos', 'Stampriet'],
    'NE': ['Niamey', 'Zinder', 'Maradi', 'Agadez', 'Tahoua', 'Dosso', 'Diffa', 'Tillabéri', 'Arlit', 'Ayorou', 'Birni-N\'Konni', 'Dakoro', 'Dogondoutchi', 'Filingué', 'Gaya', 'Gouré', 'Illéla', 'Kantché', 'Keita', 'Magaria', 'Madaoua', 'Matameye', 'Mayahi', 'Mirriah', 'N\'Guigmi', 'Say', 'Tânout', 'Téra', 'Tessaoua', 'Tibiri', 'Torodi', 'Niamey', 'Zinder', 'Maradi', 'Agadez', 'Tahoua', 'Dosso', 'Diffa', 'Tillabéri', 'Arlit', 'Ayorou', 'Birni-N\'Konni', 'Dakoro', 'Dogondoutchi', 'Filingué', 'Gaya', 'Gouré', 'Illéla', 'Kantché', 'Keita', 'Magaria', 'Madaoua', 'Matameye', 'Mayahi', 'Mirriah', 'N\'Guigmi', 'Say', 'Tânout', 'Téra', 'Tessaoua', 'Tibiri', 'Torodi'],
    'NG': ['Lagos', 'Abuja', 'Kano', 'Ibadan', 'Port Harcourt', 'Benin City', 'Kaduna', 'Maiduguri', 'Zaria', 'Aba', 'Jos', 'Ilorin', 'Oyo', 'Abeokuta', 'Onitsha', 'Warri', 'Enugu', 'Calabar', 'Uyo', 'Akure', 'Bauchi', 'Gombe', 'Damaturu', 'Sokoto', 'Katsina', 'Minna', 'Makurdi', 'Lafia', 'Jalingo', 'Yola', 'Birnin Kebbi', 'Gusau', 'Dutse', 'Yenagoa', 'Asaba', 'Awka', 'Owerri', 'Umuahia', 'Abakaliki', 'Ado Ekiti', 'Ondo', 'Osogbo', 'Ilesa', 'Iwo', 'Ede', 'Ife', 'Iseyin', 'Saki', 'Ogbomoso', 'Iseyin', 'Ikare', 'Owo', 'Okene', 'Lokoja', 'Idah', 'Anyigba', 'Keffi', 'Nasarawa', 'Keffi', 'Karu', 'New Bussa', 'Bida', 'Kontagora', 'Suleja', 'Garki', 'Kubwa', 'Nyanya', 'Mararaba', 'Gwagwalada', 'Kuje', 'Bwari', 'Abaji', 'Kwali'],
    'RW': ['Kigali', 'Butare', 'Gitarama', 'Ruhengeri', 'Gisenyi', 'Cyangugu', 'Kibungo', 'Kibuye', 'Byumba', 'Gikongoro', 'Ruhengeri', 'Gisenyi', 'Kibungo', 'Kibuye', 'Byumba', 'Gikongoro', 'Ruhengeri', 'Gisenyi', 'Kibungo', 'Kibuye', 'Byumba', 'Gikongoro'],
    'ST': ['São Tomé', 'Trindade', 'Santana', 'Neves', 'Guadalupe', 'Santo António', 'São Tomé', 'Trindade', 'Santana', 'Neves', 'Guadalupe', 'Santo António', 'São Tomé', 'Trindade', 'Santana', 'Neves', 'Guadalupe', 'Santo António'],
    'SN': ['Dakar', 'Thiès', 'Kaolack', 'Tambacounda', 'Saint-Louis', 'Ziguinchor', 'Rufisque', 'Mbour', 'Louga', 'Richard Toll', 'Tivaouane', 'Joal-Fadiout', 'Kolda', 'Médina Gounass', 'Sédhiou', 'Kédougou', 'Matam', 'Podor', 'Bakel', 'Kaffrine', 'Fatick', 'Gossas', 'Koungheul', 'Vélingara', 'Bignona', 'Oussouye', 'Ziguinchor', 'Sédhiou', 'Kolda', 'Vélingara', 'Kédougou', 'Tambacounda', 'Bakel', 'Kidira', 'Diamou', 'Kayes', 'Nioro du Rip', 'Koungheul', 'Kaffrine', 'Koumpentoum', 'Malem Hodar', 'Gossas', 'Fatick', 'Foundiougne', 'Sokone', 'Mbour', 'Thiès', 'M\'Bao', 'Rufisque', 'Bargny', 'Diamniadio', 'Sébikotane', 'Pikine', 'Guédiawaye', 'Mermoz-Sacré-Cœur', 'Almadies', 'Ouakam', 'Ngor', 'Yoff', 'Cambérène', 'Grand-Yoff', 'Parcelles Assainies', 'Hann', 'Bel-Air', 'Plateau', 'Médina', 'Fass', 'Colobane', 'Ouakam', 'Ngor', 'Yoff', 'Cambérène', 'Grand-Yoff', 'Parcelles Assainies', 'Hann', 'Bel-Air', 'Plateau', 'Médina', 'Fass', 'Colobane'],
    'SC': ['Victoria', 'Anse Boileau', 'Beau Vallon', 'Cascade', 'Takamaka', 'Anse Royale', 'Baie Lazare', 'Baie Sainte Anne', 'Beau Vallon', 'Bel Air', 'Bel Ombre', 'Cascade', 'Glacis', 'Grand\'Anse', 'La Digue', 'La Rivière Anglaise', 'Mont Buxton', 'Mont Fleuri', 'Plaisance', 'Pointe La Rue', 'Port Glaud', 'Saint Louis', 'Takamaka', 'Victoria', 'Anse Boileau', 'Beau Vallon', 'Cascade', 'Takamaka', 'Anse Royale', 'Baie Lazare', 'Baie Sainte Anne', 'Beau Vallon', 'Bel Air', 'Bel Ombre', 'Cascade', 'Glacis', 'Grand\'Anse', 'La Digue', 'La Rivière Anglaise', 'Mont Buxton', 'Mont Fleuri', 'Plaisance', 'Pointe La Rue', 'Port Glaud', 'Saint Louis', 'Takamaka', 'Victoria'],
    'SL': ['Freetown', 'Bo', 'Kenema', 'Makeni', 'Koidu', 'Port Loko', 'Kabala', 'Magburaka', 'Kailahun', 'Bonthe', 'Pujehun', 'Moyamba', 'Yengema', 'Segbwema', 'Lunsar', 'Makeni', 'Bo', 'Kenema', 'Koidu', 'Port Loko', 'Kabala', 'Magburaka', 'Kailahun', 'Bonthe', 'Pujehun', 'Moyamba', 'Yengema', 'Segbwema', 'Lunsar', 'Makeni', 'Bo', 'Kenema', 'Koidu', 'Port Loko', 'Kabala', 'Magburaka', 'Kailahun', 'Bonthe', 'Pujehun', 'Moyamba', 'Yengema', 'Segbwema', 'Lunsar'],
    'SO': ['Mogadishu', 'Hargeisa', 'Kismayo', 'Berbera', 'Baidoa', 'Bosaso', 'Galkayo', 'Garowe', 'Jowhar', 'Kismayo', 'Merca', 'Beledweyne', 'Burao', 'Borama', 'Erigavo', 'Las Anod', 'Qardho', 'Ceerigaabo', 'Bardera', 'Dhuusamarreeb', 'Afgooye', 'Jamaame', 'Kismayo', 'Merca', 'Beledweyne', 'Burao', 'Borama', 'Erigavo', 'Las Anod', 'Qardho', 'Ceerigaabo', 'Bardera', 'Dhuusamarreeb', 'Afgooye', 'Jamaame', 'Kismayo', 'Merca', 'Beledweyne', 'Burao', 'Borama', 'Erigavo', 'Las Anod', 'Qardho', 'Ceerigaabo', 'Bardera', 'Dhuusamarreeb', 'Afgooye', 'Jamaame'],
    'ZA': ['Johannesburg', 'Cape Town', 'Durban', 'Pretoria', 'Bloemfontein', 'Port Elizabeth', 'East London', 'Pietermaritzburg', 'Nelspruit', 'Polokwane', 'Kimberley', 'Rustenburg', 'Welkom', 'Newcastle', 'Klerksdorp', 'Upington', 'George', 'Oudtshoorn', 'Mossel Bay', 'Knysna', 'Plettenberg Bay', 'Jeffreys Bay', 'Port Alfred', 'Grahamstown', 'Queenstown', 'King William\'s Town', 'Bhisho', 'Uitenhage', 'Despatch', 'Jeffreys Bay', 'Stellenbosch', 'Paarl', 'Worcester', 'Somerset West', 'Strand', 'Gordon\'s Bay', 'Hermanus', 'Caledon', 'Bredasdorp', 'Swellendam', 'Riversdale', 'Ladismith', 'Barrydale', 'Montagu', 'Robertson', 'Ashton', 'McGregor', 'Bonnievale', 'Tulbagh', 'Wellington', 'Malmesbury', 'Darling', 'Hopefield', 'Vredenburg', 'Saldanha', 'Langebaan', 'Yzerfontein', 'Moorreesburg', 'Piketberg', 'Citrusdal', 'Clanwilliam', 'Lambert\'s Bay', 'Vredendal', 'Vanrhynsdorp', 'Springbok', 'O\'okiep', 'Nababeep', 'Aggeneys', 'Pofadder', 'Kakamas', 'Keimoes', 'Kenhardt', 'Upington', 'Olifantshoek', 'Postmasburg', 'Griquatown', 'Danielskuil', 'Kuruman', 'Kathu', 'Sishen', 'Hotazel', 'Vryburg', 'Mafikeng', 'Lichtenburg', 'Coligny', 'Delareyville', 'Sannieshof', 'Ottosdal', 'Hartswater', 'Warrenton', 'Jan Kempdorp', 'Douglas', 'Campbell', 'Schmidtsdrift', 'Barkly West', 'Kimberley', 'Ritchie', 'Modder River', 'Vanderbijlpark', 'Sasolburg', 'Vereeniging', 'Meyerton', 'Heidelberg', 'Nigel', 'Springs', 'Brakpan', 'Benoni', 'Boksburg', 'Germiston', 'Alberton', 'Edenvale', 'Kempton Park', 'Bedfordview', 'Sandton', 'Randburg', 'Roodepoort', 'Krugersdorp', 'Carletonville', 'Westonaria', 'Fochville', 'Potchefstroom', 'Ventersdorp', 'Lichtenburg', 'Coligny', 'Delareyville', 'Sannieshof', 'Ottosdal', 'Hartswater', 'Warrenton', 'Jan Kempdorp', 'Douglas', 'Campbell', 'Schmidtsdrift', 'Barkly West'],
    'SS': ['Juba', 'Malakal', 'Wau', 'Yambio', 'Aweil', 'Rumbek', 'Torit', 'Yei', 'Bentiu', 'Bor', 'Gogrial', 'Kapoeta', 'Kuacjok', 'Maridi', 'Nimule', 'Pibor', 'Raja', 'Renk', 'Tonj', 'Wau', 'Yambio', 'Aweil', 'Rumbek', 'Torit', 'Yei', 'Bentiu', 'Bor', 'Gogrial', 'Kapoeta', 'Kuacjok', 'Maridi', 'Nimule', 'Pibor', 'Raja', 'Renk', 'Tonj', 'Wau', 'Yambio', 'Aweil', 'Rumbek', 'Torit', 'Yei', 'Bentiu', 'Bor', 'Gogrial', 'Kapoeta', 'Kuacjok', 'Maridi', 'Nimule', 'Pibor', 'Raja', 'Renk', 'Tonj'],
    'SD': ['Khartoum', 'Omdurman', 'Port Sudan', 'Kassala', 'El Gedaref', 'Nyala', 'El Fasher', 'Geneina', 'Kadugli', 'Ed Damazin', 'El Obeid', 'Atbara', 'Shendi', 'Kosti', 'Sennar', 'El Daein', 'Zalingei', 'Kutum', 'El Geneina', 'Merowe', 'Karima', 'Dongola', 'Wadi Halfa', 'Abu Hamad', 'Berber', 'El Matamma', 'Rufaa', 'Rabak', 'Singa', 'Dinder', 'Galabat', 'Gedaref', 'Kassala', 'Port Sudan', 'Suakin', 'Tokar', 'Aqiq', 'Halaib', 'Khartoum', 'Omdurman', 'Khartoum North', 'Bahri', 'Shambat', 'Khartoum', 'Omdurman', 'Port Sudan', 'Kassala', 'El Gedaref', 'Nyala', 'El Fasher', 'Geneina', 'Kadugli', 'Ed Damazin', 'El Obeid', 'Atbara', 'Shendi', 'Kosti', 'Sennar', 'El Daein', 'Zalingei', 'Kutum', 'El Geneina', 'Merowe', 'Karima', 'Dongola', 'Wadi Halfa', 'Abu Hamad', 'Berber', 'El Matamma', 'Rufaa', 'Rabak', 'Singa', 'Dinder', 'Galabat', 'Gedaref', 'Kassala', 'Port Sudan', 'Suakin', 'Tokar', 'Aqiq', 'Halaib', 'Khartoum', 'Omdurman', 'Khartoum North', 'Bahri', 'Shambat'],
    'TZ': ['Dar es Salaam', 'Mwanza', 'Arusha', 'Dodoma', 'Mbeya', 'Zanzibar City', 'Morogoro', 'Tanga', 'Mtwara', 'Tabora', 'Kigoma', 'Iringa', 'Songea', 'Shinyanga', 'Musoma', 'Bukoba', 'Sumbawanga', 'Singida', 'Lindi', 'Moshi', 'Kilimanjaro', 'Bagamoyo', 'Pemba', 'Unguja', 'Stone Town', 'Kibaha', 'Ifakara', 'Mpanda', 'Kasulu', 'Njombe', 'Babati', 'Geita', 'Kahama', 'Same', 'Korogwe', 'Handeni', 'Mpanda', 'Kasulu', 'Njombe', 'Babati', 'Geita', 'Kahama', 'Same', 'Korogwe', 'Handeni', 'Mpanda', 'Kasulu', 'Njombe', 'Babati', 'Geita', 'Kahama', 'Same', 'Korogwe', 'Handeni'],
    'TG': ['Lomé', 'Sokodé', 'Kara', 'Kpalimé', 'Atakpamé', 'Dapaong', 'Tsévié', 'Aného', 'Bassar', 'Mango', 'Niamtougou', 'Badou', 'Kandé', 'Tchamba', 'Vogan', 'Tabligbo', 'Notsé', 'Kpalimé', 'Atakpamé', 'Dapaong', 'Tsévié', 'Aného', 'Bassar', 'Mango', 'Niamtougou', 'Badou', 'Kandé', 'Tchamba', 'Vogan', 'Tabligbo', 'Notsé', 'Kpalimé', 'Atakpamé', 'Dapaong', 'Tsévié', 'Aného', 'Bassar', 'Mango', 'Niamtougou', 'Badou', 'Kandé', 'Tchamba', 'Vogan', 'Tabligbo', 'Notsé'],
    'TN': ['Tunis', 'Sfax', 'Sousse', 'Kairouan', 'Bizerte', 'Gabès', 'Ariana', 'Gafsa', 'Monastir', 'Ben Arous', 'Kasserine', 'Médenine', 'Nabeul', 'Tataouine', 'Tozeur', 'Béja', 'Jendouba', 'Kébili', 'Le Kef', 'Mahdia', 'Manouba', 'Sidi Bouzid', 'Siliana', 'Zaghouan', 'Hammamet', 'Djerba', 'Skanes', 'Port El Kantaoui', 'Tabarka', 'Douz', 'Matmata', 'Tunis', 'Sfax', 'Sousse', 'Kairouan', 'Bizerte', 'Gabès', 'Ariana', 'Gafsa', 'Monastir', 'Ben Arous', 'Kasserine', 'Médenine', 'Nabeul', 'Tataouine', 'Tozeur', 'Béja', 'Jendouba', 'Kébili', 'Le Kef', 'Mahdia', 'Manouba', 'Sidi Bouzid', 'Siliana', 'Zaghouan', 'Hammamet', 'Djerba', 'Skanes', 'Port El Kantaoui', 'Tabarka', 'Douz', 'Matmata'],
    'UG': ['Kampala', 'Gulu', 'Lira', 'Mbarara', 'Jinja', 'Mbale', 'Mukono', 'Masaka', 'Entebbe', 'Arua', 'Soroti', 'Fort Portal', 'Kabale', 'Mbarara', 'Hoima', 'Lira', 'Gulu', 'Kitgum', 'Tororo', 'Iganga', 'Busia', 'Jinja', 'Kasese', 'Masindi', 'Ntungamo', 'Rukungiri', 'Kamuli', 'Pallisa', 'Kapchorwa', 'Kumi', 'Nebbi', 'Pakwach', 'Kampala', 'Gulu', 'Lira', 'Mbarara', 'Jinja', 'Mbale', 'Mukono', 'Masaka', 'Entebbe', 'Arua', 'Soroti', 'Fort Portal', 'Kabale', 'Mbarara', 'Hoima', 'Lira', 'Gulu', 'Kitgum', 'Tororo', 'Iganga', 'Busia', 'Jinja', 'Kasese', 'Masindi', 'Ntungamo', 'Rukungiri', 'Kamuli', 'Pallisa', 'Kapchorwa', 'Kumi', 'Nebbi', 'Pakwach'],
    'ZM': ['Lusaka', 'Kitwe', 'Ndola', 'Kabwe', 'Chingola', 'Livingstone', 'Kasama', 'Chipata', 'Solwezi', 'Mazabuka', 'Kafue', 'Mufulira', 'Luanshya', 'Mongu', 'Choma', 'Mpika', 'Kapiri Mposhi', 'Nchelenge', 'Mansa', 'Chililabombwe', 'Kalulushi', 'Mpulungu', 'Sesheke', 'Senanga', 'Mwinilunga', 'Lusaka', 'Kitwe', 'Ndola', 'Kabwe', 'Chingola', 'Livingstone', 'Kasama', 'Chipata', 'Solwezi', 'Mazabuka', 'Kafue', 'Mufulira', 'Luanshya', 'Mongu', 'Choma', 'Mpika', 'Kapiri Mposhi', 'Nchelenge', 'Mansa', 'Chililabombwe', 'Kalulushi', 'Mpulungu', 'Sesheke', 'Senanga', 'Mwinilunga'],
    'ZW': ['Harare', 'Bulawayo', 'Chitungwiza', 'Mutare', 'Gweru', 'Epworth', 'Kwekwe', 'Kadoma', 'Masvingo', 'Chinhoyi', 'Marondera', 'Norton', 'Chegutu', 'Bindura', 'Zvishavane', 'Rusape', 'Chiredzi', 'Kariba', 'Victoria Falls', 'Beitbridge', 'Redcliff', 'Rusape', 'Chiredzi', 'Kariba', 'Victoria Falls', 'Beitbridge', 'Redcliff', 'Rusape', 'Chiredzi', 'Kariba', 'Victoria Falls', 'Beitbridge', 'Redcliff'],
    
    // Asia
    'AF': ['Kabul', 'Herat', 'Kandahar', 'Mazar-i-Sharif', 'Jalalabad', 'Kunduz', 'Ghazni', 'Balkh', 'Baghlan', 'Gardez', 'Khost', 'Mehtar Lam', 'Farah', 'Taloqan', 'Pul-e-Khumri', 'Charikar', 'Sheberghan', 'Sar-e-Pul', 'Zaranj', 'Lashkar Gah', 'Qalat', 'Asadabad', 'Fayzabad', 'Maymana', 'Andkhoy', 'Aibak', 'Bamyan', 'Chaghcharan', 'Nili', 'Parun', 'Kabul', 'Herat', 'Kandahar', 'Mazar-i-Sharif', 'Jalalabad', 'Kunduz', 'Ghazni', 'Balkh', 'Baghlan', 'Gardez', 'Khost', 'Mehtar Lam', 'Farah', 'Taloqan', 'Pul-e-Khumri', 'Charikar', 'Sheberghan', 'Sar-e-Pul', 'Zaranj', 'Lashkar Gah', 'Qalat', 'Asadabad', 'Fayzabad', 'Maymana', 'Andkhoy', 'Aibak', 'Bamyan', 'Chaghcharan', 'Nili', 'Parun'],
    'AM': ['Yerevan', 'Gyumri', 'Vanadzor', 'Vagharshapat', 'Hrazdan', 'Abovyan', 'Kapan', 'Armavir', 'Goris', 'Artashat', 'Gavar', 'Sevan', 'Masis', 'Ashtarak', 'Ijevan', 'Dilijan', 'Sisian', 'Alaverdi', 'Stepanavan', 'Martuni', 'Vardenis', 'Talin', 'Aparan', 'Berd', 'Charentsavan', 'Metsamor', 'Nor Hachn', 'Tashir', 'Yeghegnadzor', 'Spitak', 'Yerevan', 'Gyumri', 'Vanadzor', 'Vagharshapat', 'Hrazdan', 'Abovyan', 'Kapan', 'Armavir', 'Goris', 'Artashat', 'Gavar', 'Sevan', 'Masis', 'Ashtarak', 'Ijevan', 'Dilijan', 'Sisian', 'Alaverdi', 'Stepanavan', 'Martuni', 'Vardenis', 'Talin', 'Aparan', 'Berd', 'Charentsavan', 'Metsamor', 'Nor Hachn', 'Tashir', 'Yeghegnadzor', 'Spitak'],
    'AZ': ['Baku', 'Ganja', 'Sumqayit', 'Mingachevir', 'Lankaran', 'Shirvan', 'Nakhchivan', 'Shaki', 'Yevlakh', 'Mingachevir', 'Khirdalan', 'Stepanakert', 'Lankaran', 'Ganja', 'Mingachevir', 'Shirvan', 'Nakhchivan', 'Shaki', 'Yevlakh', 'Mingachevir', 'Khirdalan', 'Stepanakert', 'Lankaran', 'Ganja', 'Mingachevir', 'Shirvan', 'Nakhchivan', 'Shaki', 'Yevlakh', 'Mingachevir', 'Khirdalan', 'Stepanakert', 'Lankaran', 'Ganja', 'Mingachevir', 'Shirvan', 'Nakhchivan', 'Shaki', 'Yevlakh', 'Mingachevir', 'Khirdalan', 'Stepanakert'],
    'BH': ['Manama', 'Riffa', 'Muharraq', 'Hamad Town', 'A\'ali', 'Isa Town', 'Sitra', 'Budaiya', 'Jidhafs', 'Sanad', 'Al Hidd', 'Madinat Hamad', 'Juffair', 'Adliya', 'Seef', 'Amwaj Islands', 'Diplomatic Area', 'Manama', 'Riffa', 'Muharraq', 'Hamad Town', 'A\'ali', 'Isa Town', 'Sitra', 'Budaiya', 'Jidhafs', 'Sanad', 'Al Hidd', 'Madinat Hamad', 'Juffair', 'Adliya', 'Seef', 'Amwaj Islands', 'Diplomatic Area', 'Manama', 'Riffa', 'Muharraq', 'Hamad Town', 'A\'ali', 'Isa Town', 'Sitra', 'Budaiya', 'Jidhafs', 'Sanad', 'Al Hidd', 'Madinat Hamad', 'Juffair', 'Adliya', 'Seef', 'Amwaj Islands', 'Diplomatic Area'],
    'BD': ['Dhaka', 'Chittagong', 'Khulna', 'Rajshahi', 'Sylhet', 'Barisal', 'Rangpur', 'Mymensingh', 'Comilla', 'Jessore', 'Narayanganj', 'Gazipur', 'Bogra', 'Dinajpur', 'Saidpur', 'Cox\'s Bazar', 'Tangail', 'Jamalpur', 'Pabna', 'Kushtia', 'Noakhali', 'Feni', 'Chandpur', 'Lakshmipur', 'Brahmanbaria', 'Habiganj', 'Moulvibazar', 'Sunamganj', 'Netrokona', 'Kishoreganj', 'Manikganj', 'Munshiganj', 'Narsingdi', 'Shariatpur', 'Madaripur', 'Gopalganj', 'Faridpur', 'Rajbari', 'Magura', 'Jhenaidah', 'Meherpur', 'Chuadanga', 'Jashore', 'Satkhira', 'Bagerhat', 'Pirojpur', 'Jhalokati', 'Barguna', 'Patuakhali', 'Bhola', 'Lakshmipur', 'Noakhali', 'Feni', 'Chandpur', 'Comilla', 'Brahmanbaria', 'Habiganj', 'Moulvibazar', 'Sylhet', 'Sunamganj', 'Netrokona', 'Kishoreganj', 'Mymensingh', 'Jamalpur', 'Sherpur', 'Tangail', 'Manikganj', 'Munshiganj', 'Narsingdi', 'Gazipur', 'Kishoreganj', 'Mymensingh', 'Jamalpur', 'Sherpur', 'Tangail', 'Manikganj', 'Munshiganj', 'Narsingdi', 'Gazipur'],
    'BT': ['Thimphu', 'Phuntsholing', 'Punakha', 'Paro', 'Gelephu', 'Wangdue Phodrang', 'Jakar', 'Trashigang', 'Mongar', 'Samdrup Jongkhar', 'Trongsa', 'Dagana', 'Pema Gatshel', 'Samtse', 'Sarpang', 'Zhemgang', 'Lhuntse', 'Trashiyangtse', 'Gasa', 'Haa', 'Thimphu', 'Phuntsholing', 'Punakha', 'Paro', 'Gelephu', 'Wangdue Phodrang', 'Jakar', 'Trashigang', 'Mongar', 'Samdrup Jongkhar', 'Trongsa', 'Dagana', 'Pema Gatshel', 'Samtse', 'Sarpang', 'Zhemgang', 'Lhuntse', 'Trashiyangtse', 'Gasa', 'Haa'],
    'BN': ['Bandar Seri Begawan', 'Kuala Belait', 'Seria', 'Tutong', 'Bangar', 'Kuala Belait', 'Seria', 'Tutong', 'Bangar', 'Kuala Belait', 'Seria', 'Tutong', 'Bangar', 'Kuala Belait', 'Seria', 'Tutong', 'Bangar'],
    'KH': ['Phnom Penh', 'Siem Reap', 'Battambang', 'Sihanoukville', 'Kampong Cham', 'Kampong Chhnang', 'Kampong Speu', 'Kampong Thom', 'Kampot', 'Kandal', 'Koh Kong', 'Kratie', 'Mondulkiri', 'Pailin', 'Preah Vihear', 'Prey Veng', 'Pursat', 'Ratanakiri', 'Stung Treng', 'Svay Rieng', 'Takeo', 'Kep', 'Bavet', 'Poipet', 'Sisophon', 'Kampong Saom', 'Kampong Cham', 'Battambang', 'Siem Reap', 'Sihanoukville', 'Kampong Cham', 'Kampong Chhnang', 'Kampong Speu', 'Kampong Thom', 'Kampot', 'Kandal', 'Koh Kong', 'Kratie', 'Mondulkiri', 'Pailin', 'Preah Vihear', 'Prey Veng', 'Pursat', 'Ratanakiri', 'Stung Treng', 'Svay Rieng', 'Takeo', 'Kep', 'Bavet', 'Poipet', 'Sisophon', 'Kampong Saom'],
    'CN': ['Beijing', 'Shanghai', 'Guangzhou', 'Shenzhen', 'Chengdu', 'Chongqing', 'Tianjin', 'Wuhan', 'Xi\'an', 'Nanjing', 'Hangzhou', 'Shenyang', 'Dongguan', 'Qingdao', 'Zhengzhou', 'Dalian', 'Jinan', 'Kunming', 'Changsha', 'Harbin', 'Foshan', 'Suzhou', 'Shijiazhuang', 'Hefei', 'Xiamen', 'Nanchang', 'Fuzhou', 'Wenzhou', 'Zibo', 'Yantai', 'Changchun', 'Tangshan', 'Zhongshan', 'Taizhou', 'Urumqi', 'Guiyang', 'Shantou', 'Linyi', 'Baotou', 'Handan', 'Weifang', 'Xuzhou', 'Ningbo', 'Nanning', 'Yinchuan', 'Huizhou', 'Luoyang', 'Lanzhou', 'Hohhot', 'Changzhou', 'Jiangmen', 'Zhanjiang', 'Qinhuangdao', 'Liuzhou', 'Zhuhai', 'Xiangyang', 'Yancheng', 'Jilin', 'Anshan', 'Mianyang', 'Baoding', 'Huludao', 'Jiaxing', 'Xining', 'Yichang', 'Jinzhou', 'Shiyan', 'Daqing', 'Yiwu', 'Quanzhou', 'Langfang', 'Zigong', 'Maoming', 'Qinzhou', 'Jining', 'Liaoyang', 'Xinxiang', 'Hengyang', 'Jieyang', 'Chaozhou', 'Zhangzhou', 'Putian', 'Sanming', 'Longyan', 'Nanping', 'Ningde', 'Quzhou', 'Lishui', 'Zhoushan', 'Taizhou', 'Wuhu', 'Bengbu', 'Huainan', 'Ma\'anshan', 'Huaibei', 'Tongling', 'Anqing', 'Huangshan', 'Chuzhou', 'Fuyang', 'Suzhou', 'Bozhou', 'Chizhou', 'Xuancheng', 'Lu\'an', 'Fuyang', 'Suzhou', 'Bozhou', 'Chizhou', 'Xuancheng', 'Lu\'an'],
    'GE': ['Tbilisi', 'Batumi', 'Kutaisi', 'Rustavi', 'Gori', 'Zugdidi', 'Poti', 'Telavi', 'Akhaltsikhe', 'Khashuri', 'Senaki', 'Marneuli', 'Kobuleti', 'Zestafoni', 'Kaspi', 'Ozurgeti', 'Bolnisi', 'Tkibuli', 'Chiatura', 'Tsqaltubo', 'Sagarejo', 'Gardabani', 'Borjomi', 'Tskhinvali', 'Gurjaani', 'Mtskheta', 'Kvareli', 'Akhmeta', 'Dusheti', 'Lagodekhi', 'Tbilisi', 'Batumi', 'Kutaisi', 'Rustavi', 'Gori', 'Zugdidi', 'Poti', 'Telavi', 'Akhaltsikhe', 'Khashuri', 'Senaki', 'Marneuli', 'Kobuleti', 'Zestafoni', 'Kaspi', 'Ozurgeti', 'Bolnisi', 'Tkibuli', 'Chiatura', 'Tsqaltubo', 'Sagarejo', 'Gardabani', 'Borjomi', 'Tskhinvali', 'Gurjaani', 'Mtskheta', 'Kvareli', 'Akhmeta', 'Dusheti', 'Lagodekhi'],
    'IN': ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai', 'Kolkata', 'Ahmedabad', 'Pune', 'Surat', 'Jaipur', 'Lucknow', 'Kanpur', 'Nagpur', 'Indore', 'Thane', 'Bhopal', 'Visakhapatnam', 'Patna', 'Vadodara', 'Ghaziabad', 'Ludhiana', 'Agra', 'Nashik', 'Faridabad', 'Meerut', 'Rajkot', 'Kalyan', 'Vasai-Virar', 'Varanasi', 'Srinagar', 'Amritsar', 'Navi Mumbai', 'Allahabad', 'Ranchi', 'Howrah', 'Jabalpur', 'Gwalior', 'Vijayawada', 'Jodhpur', 'Madurai', 'Raipur', 'Kota', 'Guwahati', 'Chandigarh', 'Solapur', 'Hubli', 'Dharwad', 'Mysore', 'Tiruchirappalli', 'Bareilly', 'Aligarh', 'Tirunelveli', 'Gurgaon', 'Moradabad', 'Jalandhar', 'Bhubaneswar', 'Salem', 'Warangal', 'Guntur', 'Bhiwandi', 'Saharanpur', 'Gorakhpur', 'Bikaner', 'Amravati', 'Noida', 'Jamshedpur', 'Bhilai', 'Cuttack', 'Firozabad', 'Kochi', 'Nellore', 'Bhavnagar', 'Dehradun', 'Durgapur', 'Asansol', 'Rourkela', 'Nanded', 'Kolhapur', 'Ajmer', 'Gulbarga', 'Jamnagar', 'Ujjain', 'Loni', 'Siliguri', 'Jhansi', 'Ulhasnagar', 'Jammu', 'Sangli-Miraj', 'Mangalore', 'Erode', 'Belgaum', 'Ambattur', 'Tirupati', 'Karnal', 'Bihar Sharif', 'Panipat', 'Darbhanga', 'Anantapur', 'Bhatpara', 'Panihati', 'Latur', 'Dhule', 'Tumkur', 'Kozhikode', 'Bilaspur', 'Kurnool', 'Shahjahanpur', 'Bellary', 'Parbhani', 'Agartala', 'Muzaffarpur', 'Bathinda', 'Raichur', 'Ozhukarai', 'Bihar Sharif', 'Panipat', 'Darbhanga', 'Anantapur', 'Bhatpara', 'Panihati', 'Latur', 'Dhule', 'Tumkur', 'Kozhikode', 'Bilaspur', 'Kurnool', 'Shahjahanpur', 'Bellary', 'Parbhani', 'Agartala', 'Muzaffarpur', 'Bathinda', 'Raichur', 'Ozhukarai'],
    'ID': ['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Semarang', 'Makassar', 'Palembang', 'Tangerang', 'Depok', 'Bekasi', 'Bandar Lampung', 'Bogor', 'Pekanbaru', 'Padang', 'Malang', 'Yogyakarta', 'Surakarta', 'Pontianak', 'Manado', 'Balikpapan', 'Denpasar', 'Samarinda', 'Cimahi', 'Jambi', 'Cilegon', 'Mataram', 'Palu', 'Kupang', 'Banjarmasin', 'Tegal', 'Kediri', 'Binjai', 'Pekalongan', 'Sukabumi', 'Cirebon', 'Tasikmalaya', 'Probolinggo', 'Lubuklinggau', 'Cibinong', 'Batu', 'Pasuruan', 'Sidoarjo', 'Lamongan', 'Madiun', 'Blitar', 'Kediri', 'Tulungagung', 'Trenggalek', 'Ponorogo', 'Pacitan', 'Wonogiri', 'Sukoharjo', 'Karanganyar', 'Sragen', 'Boyolali', 'Klaten', 'Magelang', 'Temanggung', 'Wonosobo', 'Purworejo', 'Kebumen', 'Banjarnegara', 'Purbalingga', 'Banyumas', 'Cilacap', 'Brebes', 'Tegal', 'Pemalang', 'Pekalongan', 'Batang', 'Kendal', 'Semarang', 'Demak', 'Grobogan', 'Blora', 'Rembang', 'Pati', 'Kudus', 'Jepara', 'Tuban', 'Bojonegoro', 'Lamongan', 'Gresik', 'Sidoarjo', 'Mojokerto', 'Jombang', 'Nganjuk', 'Madiun', 'Magetan', 'Ngawi', 'Bojonegoro', 'Tuban', 'Lamongan', 'Gresik', 'Sidoarjo', 'Mojokerto', 'Jombang', 'Nganjuk', 'Madiun', 'Magetan', 'Ngawi'],
    'IR': ['Tehran', 'Isfahan', 'Mashhad', 'Tabriz', 'Shiraz', 'Karaj', 'Ahvaz', 'Qom', 'Kermanshah', 'Urmia', 'Zahedan', 'Rasht', 'Kerman', 'Hamadan', 'Yazd', 'Ardabil', 'Bandar Abbas', 'Arak', 'Eslamshahr', 'Zanjan', 'Sanandaj', 'Qazvin', 'Khorramabad', 'Gorgan', 'Sabzevar', 'Khomeyni Shahr', 'Borujerd', 'Amol', 'Neyshabur', 'Babol', 'Khorramshahr', 'Abadan', 'Dezful', 'Kashan', 'Sari', 'Gonbad-e Kavus', 'Ilam', 'Bojnurd', 'Semnan', 'Fasa', 'Kashmar', 'Shahrekord', 'Yasuj', 'Birjand', 'Bandar-e Anzali', 'Saveh', 'Tehran', 'Isfahan', 'Mashhad', 'Tabriz', 'Shiraz', 'Karaj', 'Ahvaz', 'Qom', 'Kermanshah', 'Urmia', 'Zahedan', 'Rasht', 'Kerman', 'Hamadan', 'Yazd', 'Ardabil', 'Bandar Abbas', 'Arak', 'Eslamshahr', 'Zanjan', 'Sanandaj', 'Qazvin', 'Khorramabad', 'Gorgan', 'Sabzevar', 'Khomeyni Shahr', 'Borujerd', 'Amol', 'Neyshabur', 'Babol', 'Khorramshahr', 'Abadan', 'Dezful', 'Kashan', 'Sari', 'Gonbad-e Kavus', 'Ilam', 'Bojnurd', 'Semnan', 'Fasa', 'Kashmar', 'Shahrekord', 'Yasuj', 'Birjand', 'Bandar-e Anzali', 'Saveh'],
    'IQ': ['Baghdad', 'Basra', 'Mosul', 'Kirkuk', 'Najaf', 'Erbil', 'Karbala', 'Nasiriyah', 'Amarah', 'Baqubah', 'Ramadi', 'Samarra', 'Fallujah', 'Tikrit', 'Dohuk', 'Kut', 'Hillah', 'Diwaniyah', 'Zakho', 'Sulaymaniyah', 'Diyarbakir', 'Halabja', 'Ranya', 'Qal\'at Sukkar', 'Hit', 'Haditha', 'Tal Afar', 'Sinjar', 'Qayyarah', 'Baiji', 'Hawija', 'Tuz Khurmatu', 'Khanaqin', 'Mandali', 'Badrah', 'Kut', 'Amarah', 'Nasiriyah', 'Shatra', 'Suq al-Shuyukh', 'Afak', 'Rumaitha', 'Samawah', 'Baghdad', 'Basra', 'Mosul', 'Kirkuk', 'Najaf', 'Erbil', 'Karbala', 'Nasiriyah', 'Amarah', 'Baqubah', 'Ramadi', 'Samarra', 'Fallujah', 'Tikrit', 'Dohuk', 'Kut', 'Hillah', 'Diwaniyah', 'Zakho', 'Sulaymaniyah', 'Diyarbakir', 'Halabja', 'Ranya', 'Qal\'at Sukkar', 'Hit', 'Haditha', 'Tal Afar', 'Sinjar', 'Qayyarah', 'Baiji', 'Hawija', 'Tuz Khurmatu', 'Khanaqin', 'Mandali', 'Badrah', 'Kut', 'Amarah', 'Nasiriyah', 'Shatra', 'Suq al-Shuyukh', 'Afak', 'Rumaitha', 'Samawah'],
    'IL': ['Tel Aviv', 'Jerusalem', 'Haifa', 'Beersheba', 'Rishon LeZion', 'Petah Tikva', 'Ashdod', 'Netanya', 'Holon', 'Bnei Brak', 'Rehovot', 'Bat Yam', 'Ashkelon', 'Herzliya', 'Kfar Saba', 'Hadera', 'Ramat Gan', 'Modiin', 'Nazareth', 'Lod', 'Ramla', 'Ra\'anana', 'Givatayim', 'Nahariya', 'Eilat', 'Akko', 'Tiberias', 'Safed', 'Kiryat Shmona', 'Afula', 'Dimona', 'Kiryat Gat', 'Kiryat Malakhi', 'Yavne', 'Or Yehuda', 'Gedera', 'Kfar Yona', 'Rosh HaAyin', 'Nes Ziona', 'Yehud', 'Tel Aviv', 'Jerusalem', 'Haifa', 'Beersheba', 'Rishon LeZion', 'Petah Tikva', 'Ashdod', 'Netanya', 'Holon', 'Bnei Brak', 'Rehovot', 'Bat Yam', 'Ashkelon', 'Herzliya', 'Kfar Saba', 'Hadera', 'Ramat Gan', 'Modiin', 'Nazareth', 'Lod', 'Ramla', 'Ra\'anana', 'Givatayim', 'Nahariya', 'Eilat', 'Akko', 'Tiberias', 'Safed', 'Kiryat Shmona', 'Afula', 'Dimona', 'Kiryat Gat', 'Kiryat Malakhi', 'Yavne', 'Or Yehuda', 'Gedera', 'Kfar Yona', 'Rosh HaAyin', 'Nes Ziona', 'Yehud'],
    'JP': ['Tokyo', 'Yokohama', 'Osaka', 'Nagoya', 'Sapporo', 'Fukuoka', 'Kobe', 'Kawasaki', 'Hiroshima', 'Sendai', 'Kitakyushu', 'Chiba', 'Sakai', 'Niigata', 'Hamamatsu', 'Kumamoto', 'Sagamihara', 'Shizuoka', 'Okayama', 'Kagoshima', 'Hachioji', 'Utsunomiya', 'Matsuyama', 'Kanazawa', 'Nagano', 'Toyama', 'Gifu', 'Fukushima', 'Takamatsu', 'Asahikawa', 'Iwaki', 'Takasaki', 'Koriyama', 'Toyohashi', 'Nagasaki', 'Toyama', 'Gifu', 'Fukushima', 'Takamatsu', 'Asahikawa', 'Iwaki', 'Takasaki', 'Koriyama', 'Toyohashi', 'Nagasaki', 'Hakodate', 'Akita', 'Aomori', 'Morioka', 'Yamagata', 'Fukui', 'Tottori', 'Matsue', 'Yamaguchi', 'Tokushima', 'Kochi', 'Miyazaki', 'Oita', 'Saga', 'Naha', 'Kawagoe', 'Himeji', 'Kurashiki', 'Fukuyama', 'Tokushima', 'Kochi', 'Miyazaki', 'Oita', 'Saga', 'Naha', 'Kawagoe', 'Himeji', 'Kurashiki', 'Fukuyama'],
    'JO': ['Amman', 'Zarqa', 'Irbid', 'Aqaba', 'Jerash', 'Madaba', 'Mafraq', 'Salt', 'Karak', 'Tafilah', 'Ma\'an', 'Ajloun', 'Ramtha', 'Fuheis', 'Sahab', 'Russeifa', 'Wadi as-Sir', 'Ayn al-Basha', 'Sweileh', 'Jarash', 'Mafraq', 'Karak', 'Tafilah', 'Ma\'an', 'Ajloun', 'Ramtha', 'Fuheis', 'Sahab', 'Russeifa', 'Wadi as-Sir', 'Ayn al-Basha', 'Sweileh', 'Jarash', 'Mafraq', 'Karak', 'Tafilah', 'Ma\'an', 'Ajloun', 'Ramtha', 'Fuheis', 'Sahab', 'Russeifa', 'Wadi as-Sir', 'Ayn al-Basha', 'Sweileh', 'Jarash'],
    'KZ': ['Almaty', 'Nur-Sultan', 'Shymkent', 'Karaganda', 'Aktobe', 'Taraz', 'Pavlodar', 'Ust-Kamenogorsk', 'Semey', 'Oral', 'Kostanay', 'Petropavl', 'Atyrau', 'Temirtau', 'Turkestan', 'Kyzylorda', 'Aktau', 'Ekibastuz', 'Rudny', 'Taldykorgan', 'Kokshetau', 'Zhezkazgan', 'Kentau', 'Balkhash', 'Saran', 'Shakhtinsk', 'Semei', 'Stepnogorsk', 'Ridder', 'Zaysan', 'Almaty', 'Nur-Sultan', 'Shymkent', 'Karaganda', 'Aktobe', 'Taraz', 'Pavlodar', 'Ust-Kamenogorsk', 'Semey', 'Oral', 'Kostanay', 'Petropavl', 'Atyrau', 'Temirtau', 'Turkestan', 'Kyzylorda', 'Aktau', 'Ekibastuz', 'Rudny', 'Taldykorgan', 'Kokshetau', 'Zhezkazgan', 'Kentau', 'Balkhash', 'Saran', 'Shakhtinsk', 'Semei', 'Stepnogorsk', 'Ridder', 'Zaysan'],
    'KW': ['Kuwait City', 'Al Ahmadi', 'Hawalli', 'Al Jahra', 'Al Farwaniyah', 'Salmiya', 'Jahra', 'Fahaheel', 'Abu Halifa', 'Mahboula', 'Mangaf', 'Sabah Al-Salem', 'Rumaithiya', 'Salwa', 'Bayan', 'Dasma', 'Surra', 'Yarmouk', 'Shuwaikh', 'Sharq', 'Dasman', 'Kuwait City', 'Al Ahmadi', 'Hawalli', 'Al Jahra', 'Al Farwaniyah', 'Salmiya', 'Jahra', 'Fahaheel', 'Abu Halifa', 'Mahboula', 'Mangaf', 'Sabah Al-Salem', 'Rumaithiya', 'Salwa', 'Bayan', 'Dasma', 'Surra', 'Yarmouk', 'Shuwaikh', 'Sharq', 'Dasman'],
    'KG': ['Bishkek', 'Osh', 'Jalal-Abad', 'Karakol', 'Tokmok', 'Kara-Balta', 'Naryn', 'Talas', 'Balykchy', 'Kant', 'Kara-Suu', 'Cholpon-Ata', 'Karakol', 'Bishkek', 'Osh', 'Jalal-Abad', 'Karakol', 'Tokmok', 'Kara-Balta', 'Naryn', 'Talas', 'Balykchy', 'Kant', 'Kara-Suu', 'Cholpon-Ata', 'Karakol', 'Bishkek', 'Osh', 'Jalal-Abad', 'Karakol', 'Tokmok', 'Kara-Balta', 'Naryn', 'Talas', 'Balykchy', 'Kant', 'Kara-Suu', 'Cholpon-Ata', 'Karakol'],
    'LA': ['Vientiane', 'Pakse', 'Savannakhet', 'Luang Prabang', 'Thakhek', 'Phonsavan', 'Xam Neua', 'Phonhong', 'Muang Xay', 'Luang Namtha', 'Muang Sing', 'Boun Neua', 'Houayxay', 'Pakbeng', 'Nong Khiaw', 'Muang Ngoi', 'Muang Khua', 'Phongsaly', 'Sam Neua', 'Xam Neua', 'Phonhong', 'Muang Xay', 'Luang Namtha', 'Muang Sing', 'Boun Neua', 'Houayxay', 'Pakbeng', 'Nong Khiaw', 'Muang Ngoi', 'Muang Khua', 'Phongsaly', 'Sam Neua', 'Xam Neua', 'Phonhong', 'Muang Xay', 'Luang Namtha', 'Muang Sing', 'Boun Neua', 'Houayxay', 'Pakbeng', 'Nong Khiaw', 'Muang Ngoi', 'Muang Khua', 'Phongsaly', 'Sam Neua'],
    'LB': ['Beirut', 'Tripoli', 'Sidon', 'Tyre', 'Baalbek', 'Zahle', 'Jounieh', 'Byblos', 'Batroun', 'Nabatieh', 'Jezzine', 'Halba', 'Marjayoun', 'Zgharta', 'Amioun', 'Bcharre', 'Ehden', 'Douma', 'Baalbek', 'Hermel', 'Rashaya', 'Machghara', 'Jezzine', 'Marjayoun', 'Nabatieh', 'Tyre', 'Sidon', 'Beirut', 'Tripoli', 'Sidon', 'Tyre', 'Baalbek', 'Zahle', 'Jounieh', 'Byblos', 'Batroun', 'Nabatieh', 'Jezzine', 'Halba', 'Marjayoun', 'Zgharta', 'Amioun', 'Bcharre', 'Ehden', 'Douma', 'Baalbek', 'Hermel', 'Rashaya', 'Machghara', 'Jezzine', 'Marjayoun', 'Nabatieh', 'Tyre', 'Sidon'],
    'MY': ['Kuala Lumpur', 'George Town', 'Ipoh', 'Johor Bahru', 'Petaling Jaya', 'Shah Alam', 'Klang', 'Kota Kinabalu', 'Kuching', 'Kota Bharu', 'Alor Setar', 'Miri', 'Seremban', 'Subang Jaya', 'Iskandar Puteri', 'Malacca City', 'Kuantan', 'Tawau', 'Sandakan', 'Kuala Terengganu', 'Kangar', 'Putrajaya', 'Labuan', 'Kuala Lumpur', 'George Town', 'Ipoh', 'Johor Bahru', 'Petaling Jaya', 'Shah Alam', 'Klang', 'Kota Kinabalu', 'Kuching', 'Kota Bharu', 'Alor Setar', 'Miri', 'Seremban', 'Subang Jaya', 'Iskandar Puteri', 'Malacca City', 'Kuantan', 'Tawau', 'Sandakan', 'Kuala Terengganu', 'Kangar', 'Putrajaya', 'Labuan'],
    'MV': ['Malé', 'Addu City', 'Fuvahmulah', 'Kulhudhuffushi', 'Thinadhoo', 'Hithadhoo', 'Eydhafushi', 'Naifaru', 'Mahibadhoo', 'Viligili', 'Hulhumale', 'Hulhumale', 'Hulhumale'],
    'MM': ['Yangon', 'Mandalay', 'Naypyidaw', 'Mawlamyine', 'Bago', 'Pathein', 'Monywa', 'Sittwe', 'Meiktila', 'Mergui', 'Taunggyi', 'Myeik', 'Magway', 'Pakokku', 'Pyay', 'Hinthada', 'Lashio', 'Dawei', 'Kalay', 'Mawlamyine', 'Bago', 'Pathein', 'Monywa', 'Sittwe', 'Meiktila', 'Mergui', 'Taunggyi', 'Myeik', 'Magway', 'Pakokku', 'Pyay', 'Hinthada', 'Lashio', 'Dawei', 'Kalay', 'Mawlamyine', 'Bago', 'Pathein', 'Monywa', 'Sittwe', 'Meiktila', 'Mergui', 'Taunggyi', 'Myeik', 'Magway', 'Pakokku', 'Pyay', 'Hinthada', 'Lashio', 'Dawei', 'Kalay'],
    'NP': ['Kathmandu', 'Pokhara', 'Lalitpur', 'Bharatpur', 'Biratnagar'],
    'KP': ['Pyongyang', 'Hamhung', 'Chongjin', 'Nampo', 'Sinuiju'],
    'OM': ['Muscat', 'Seeb', 'Salalah', 'Bawshar', 'Sohar'],
    'PK': ['Karachi', 'Lahore', 'Islamabad', 'Faisalabad', 'Rawalpindi', 'Multan', 'Gujranwala', 'Peshawar', 'Quetta', 'Sialkot', 'Bahawalpur', 'Sargodha', 'Sukkur', 'Larkana', 'Sheikhupura', 'Rahim Yar Khan', 'Jhang', 'Dera Ghazi Khan', 'Gujrat', 'Kasur', 'Mardan', 'Mingora', 'Nawabshah', 'Chiniot', 'Kotri', 'Kāmoke', 'Hafizabad', 'Kohat', 'Jacobabad', 'Shikarpur', 'Muzaffargarh', 'Khanewal', 'Gojra', 'Mandi Bahauddin', 'Abbottabad', 'Bahawalnagar', 'Pakpattan', 'Khuzdar', 'Chishtian', 'Daska', 'Shahkot', 'Mianwali', 'Bhakkar', 'Jhelum', 'Kharian', 'Kamalia', 'Vehari', 'Nowshera', 'Charsadda', 'Swabi', 'Mardan', 'Charsadda', 'Nowshera', 'Swabi', 'Mardan', 'Charsadda', 'Nowshera', 'Swabi'],
    'PS': ['Gaza', 'Hebron', 'Nablus', 'Ramallah', 'Jericho'],
    'PH': ['Manila', 'Cebu', 'Davao', 'Quezon City', 'Caloocan', 'Makati', 'Pasig', 'Taguig', 'Las Piñas', 'Valenzuela', 'Parañaque', 'Muntinlupa', 'Marikina', 'Mandaluyong', 'San Juan', 'Malabon', 'Navotas', 'Pasay', 'Bacolod', 'Iloilo City', 'Zamboanga City', 'Cagayan de Oro', 'Antipolo', 'Bacoor', 'Dasmariñas', 'General Santos', 'Calamba', 'San Pedro', 'Santa Rosa', 'Binan', 'Taytay', 'Cainta', 'Rodriguez', 'San Mateo', 'Angono', 'Teresa', 'Baras', 'Tanay', 'Pililla', 'Jala-Jala', 'Cardona', 'Morong', 'Binangonan', 'Cainta', 'Taytay', 'Angono', 'Teresa', 'Baras', 'Tanay', 'Pililla', 'Jala-Jala', 'Cardona', 'Morong', 'Binangonan', 'Cainta', 'Taytay', 'Angono', 'Teresa', 'Baras', 'Tanay', 'Pililla', 'Jala-Jala', 'Cardona', 'Morong', 'Binangonan'],
    'QA': ['Doha', 'Al Rayyan', 'Al Wakrah', 'Al Khor', 'Dukhan'],
    'SA': ['Riyadh', 'Jeddah', 'Mecca', 'Medina', 'Dammam'],
    'SG': ['Singapore'],
    'LK': ['Colombo', 'Kandy', 'Galle', 'Jaffna', 'Negombo'],
    'KR': ['Seoul', 'Busan', 'Incheon', 'Daegu', 'Daejeon'],
    'SY': ['Damascus', 'Aleppo', 'Homs', 'Latakia', 'Hama', 'Tartus', 'Deir ez-Zor', 'Al-Hasakah', 'Raqqa', 'Idlib', 'Daraa', 'As-Suwayda', 'Qamishli', 'Manbij', 'Al-Bab', 'Afrin', 'Kobani', 'Tell Abyad', 'Al-Mayadin', 'Abu Kamal', 'Al-Qusayr', 'Yabroud', 'Zabadani', 'Ma\'loula', 'Safita', 'Masyaf', 'Baniyas', 'Jableh', 'Lattakia', 'Jisr al-Shughur', 'Ariha', 'Kafr Nabl', 'Maarrat al-Nu\'man', 'Khan Shaykhun', 'Saraqib', 'Al-Dana', 'Harim', 'Salqin', 'Darkush', 'Jindires', 'Atarib', 'Anadan', 'Kafr Hamra', 'Nubl', 'Zahra', 'Kafr Zita', 'Halfaya', 'Mhardeh', 'Kafr Buhum', 'Salamiyah', 'Masyaf', 'Baniyas', 'Jableh', 'Lattakia', 'Jisr al-Shughur', 'Ariha', 'Kafr Nabl', 'Maarrat al-Nu\'man', 'Khan Shaykhun', 'Saraqib', 'Al-Dana', 'Harim', 'Salqin', 'Darkush', 'Jindires', 'Atarib', 'Anadan', 'Kafr Hamra', 'Nubl', 'Zahra', 'Kafr Zita', 'Halfaya', 'Mhardeh', 'Kafr Buhum', 'Salamiyah'],
    'TW': ['Taipei', 'Kaohsiung', 'Taichung', 'Tainan', 'Hsinchu'],
    'TJ': ['Dushanbe', 'Khujand', 'Kulob', 'Qurghonteppa', 'Istaravshan'],
    'TH': ['Bangkok', 'Chiang Mai', 'Phuket', 'Pattaya', 'Rayong'],
    'TL': ['Dili', 'Baucau', 'Maliana', 'Suai', 'Liquiçá'],
    'TR': ['Istanbul', 'Ankara', 'Izmir', 'Bursa', 'Antalya'],
    'TM': ['Ashgabat', 'Türkmenabat', 'Daşoguz', 'Mary', 'Balkanabat'],
    'AE': ['Dubai', 'Abu Dhabi', 'Sharjah', 'Ajman', 'Ras Al Khaimah'],
    'UZ': ['Tashkent', 'Samarkand', 'Namangan', 'Andijan', 'Bukhara'],
    'VN': ['Ho Chi Minh City', 'Hanoi', 'Da Nang', 'Can Tho', 'Hai Phong'],
    'YE': ['Sana\'a', 'Aden', 'Taiz', 'Hodeidah', 'Ibb'],
    
    // Europe
    'AL': ['Tirana', 'Durrës', 'Vlorë', 'Shkodër', 'Fier'],
    'AD': ['Andorra la Vella', 'Escaldes-Engordany', 'Encamp', 'Sant Julià de Lòria', 'La Massana'],
    'AT': ['Vienna', 'Graz', 'Linz', 'Salzburg', 'Innsbruck'],
    'BY': ['Minsk', 'Gomel', 'Mogilev', 'Vitebsk', 'Grodno'],
    'BE': ['Brussels', 'Antwerp', 'Ghent', 'Charleroi', 'Liège'],
    'BA': ['Sarajevo', 'Banja Luka', 'Tuzla', 'Zenica', 'Mostar'],
    'BG': ['Sofia', 'Plovdiv', 'Varna', 'Burgas', 'Ruse'],
    'HR': ['Zagreb', 'Split', 'Rijeka', 'Osijek', 'Zadar'],
    'CY': ['Nicosia', 'Limassol', 'Larnaca', 'Paphos', 'Famagusta'],
    'CZ': ['Prague', 'Brno', 'Ostrava', 'Plzen', 'Liberec'],
    'DK': ['Copenhagen', 'Aarhus', 'Odense', 'Aalborg', 'Esbjerg'],
    'EE': ['Tallinn', 'Tartu', 'Narva', 'Pärnu', 'Kohtla-Järve'],
    'FI': ['Helsinki', 'Espoo', 'Tampere', 'Vantaa', 'Turku'],
    'FR': ['Paris', 'Marseille', 'Lyon', 'Toulouse', 'Nice', 'Nantes', 'Strasbourg', 'Montpellier', 'Bordeaux', 'Lille', 'Rennes', 'Reims', 'Le Havre', 'Saint-Étienne', 'Toulon', 'Grenoble', 'Dijon', 'Angers', 'Nîmes', 'Villeurbanne', 'Saint-Denis', 'Le Mans', 'Aix-en-Provence', 'Clermont-Ferrand', 'Brest', 'Limoges', 'Tours', 'Amiens', 'Perpignan', 'Metz', 'Besançon', 'Boulogne-Billancourt', 'Orléans', 'Mulhouse', 'Caen', 'Rouen', 'Nancy', 'Argenteuil', 'Montreuil', 'Saint-Paul', 'Roubaix', 'Tourcoing', 'Nanterre', 'Avignon', 'Créteil', 'Dunkirk', 'Poitiers', 'Asnières-sur-Seine', 'Courbevoie', 'Versailles', 'Vitry-sur-Seine', 'Colombes', 'Aulnay-sous-Bois', 'La Rochelle', 'Rueil-Malmaison', 'Champigny-sur-Marne', 'Antibes', 'Saint-Maur-des-Fossés', 'Cannes', 'Calais', 'Béziers', 'Mérignac', 'Drancy', 'Massy', 'Bourges', 'Issy-les-Moulineaux', 'Noisy-le-Grand', 'Évry', 'Pessac', 'Troyes', 'Clichy', 'Antony', 'La Seyne-sur-Mer', 'Villeneuve-d\'Ascq', 'Hyères', 'Sète', 'Pau', 'Lorient', 'Montauban', 'Châteauroux', 'Bayonne', 'Brive-la-Gaillarde', 'Châlons-en-Champagne', 'Charleville-Mézières', 'Châteauroux', 'Châlons-en-Champagne', 'Charleville-Mézières'],
    'DE': ['Berlin', 'Munich', 'Frankfurt', 'Cologne', 'Hamburg', 'Stuttgart', 'Düsseldorf', 'Dortmund', 'Essen', 'Leipzig', 'Bremen', 'Dresden', 'Hannover', 'Nuremberg', 'Duisburg', 'Bochum', 'Wuppertal', 'Bielefeld', 'Bonn', 'Münster', 'Karlsruhe', 'Mannheim', 'Augsburg', 'Wiesbaden', 'Gelsenkirchen', 'Mönchengladbach', 'Braunschweig', 'Chemnitz', 'Kiel', 'Aachen', 'Halle', 'Magdeburg', 'Freiburg', 'Krefeld', 'Lübeck', 'Oberhausen', 'Erfurt', 'Mainz', 'Rostock', 'Kassel', 'Hagen', 'Hamm', 'Saarbrücken', 'Mülheim', 'Potsdam', 'Ludwigshafen', 'Oldenburg', 'Leverkusen', 'Osnabrück', 'Solingen', 'Heidelberg', 'Herne', 'Neuss', 'Darmstadt', 'Paderborn', 'Regensburg', 'Ingolstadt', 'Würzburg', 'Fürth', 'Wolfsburg', 'Offenbach', 'Ulm', 'Heilbronn', 'Pforzheim', 'Göttingen', 'Bottrop', 'Trier', 'Recklinghausen', 'Reutlingen', 'Bremerhaven', 'Koblenz', 'Bergisch Gladbach', 'Jena', 'Remscheid', 'Erlangen', 'Moers', 'Siegen', 'Hildesheim', 'Salzgitter', 'Cottbus', 'Kaiserslautern', 'Gütersloh', 'Schwerin', 'Witten', 'Iserlohn', 'Zwickau', 'Düren', 'Esslingen', 'Ratingen', 'Lünen', 'Hanau', 'Marl', 'Lüdenscheid', 'Velbert', 'Minden', 'Dessau', 'Villingen-Schwenningen', 'Rheine', 'Konstanz', 'Worms', 'Ludwigsburg', 'Neumünster', 'Wilhelmshaven', 'Flensburg', 'Bayreuth', 'Baden-Baden', 'Detmold', 'Landshut', 'Aschaffenburg', 'Bamberg', 'Fulda', 'Kempten', 'Weimar', 'Speyer', 'Schwäbisch Gmünd', 'Lörrach', 'Cuxhaven', 'Rosenheim', 'Frankfurt (Oder)', 'Stralsund', 'Friedrichshafen', 'Offenburg', 'Gießen', 'Hameln', 'Stolberg', 'Euskirchen', 'Sindelfingen', 'Herten', 'Bergheim', 'Garbsen', 'Wesel', 'Sankt Augustin', 'Hürth', 'Unna', 'Eschweiler', 'Langenhagen', 'Grevenbroich', 'Dormagen', 'Castrop-Rauxel', 'Lüneburg', 'Marl', 'Lüdenscheid', 'Velbert', 'Minden', 'Dessau', 'Villingen-Schwenningen', 'Rheine', 'Konstanz', 'Worms', 'Ludwigsburg', 'Neumünster', 'Wilhelmshaven', 'Flensburg', 'Bayreuth', 'Baden-Baden', 'Detmold', 'Landshut', 'Aschaffenburg', 'Bamberg', 'Fulda', 'Kempten', 'Weimar', 'Speyer', 'Schwäbisch Gmünd', 'Lörrach', 'Cuxhaven', 'Rosenheim', 'Frankfurt (Oder)', 'Stralsund', 'Friedrichshafen', 'Offenburg', 'Gießen', 'Hameln', 'Stolberg', 'Euskirchen', 'Sindelfingen', 'Herten', 'Bergheim', 'Garbsen', 'Wesel', 'Sankt Augustin', 'Hürth', 'Unna', 'Eschweiler', 'Langenhagen', 'Grevenbroich', 'Dormagen', 'Castrop-Rauxel', 'Lüneburg'],
    'GR': ['Athens', 'Thessaloniki', 'Patras', 'Heraklion', 'Larissa'],
    'HU': ['Budapest', 'Debrecen', 'Szeged', 'Miskolc', 'Pecs'],
    'IS': ['Reykjavik', 'Kópavogur', 'Hafnarfjörður', 'Akureyri', 'Reykjanesbær'],
    'IE': ['Dublin', 'Cork', 'Limerick', 'Galway', 'Waterford'],
    'IT': ['Rome', 'Milan', 'Naples', 'Turin', 'Venice', 'Palermo', 'Genoa', 'Bologna', 'Florence', 'Bari', 'Catania', 'Verona', 'Venice', 'Messina', 'Padua', 'Trieste', 'Brescia', 'Parma', 'Taranto', 'Prato', 'Modena', 'Reggio Calabria', 'Reggio Emilia', 'Perugia', 'Livorno', 'Ravenna', 'Cagliari', 'Foggia', 'Rimini', 'Salerno', 'Ferrara', 'Sassari', 'Latina', 'Giugliano in Campania', 'Monza', 'Syracuse', 'Bergamo', 'Pescara', 'Trento', 'Forlì', 'Vicenza', 'Terni', 'Bolzano', 'Novara', 'Piacenza', 'Ancona', 'Andria', 'Arezzo', 'Udine', 'Cesena', 'Lecce', 'Pesaro', 'La Spezia', 'Como', 'Pisa', 'Barletta', 'Alessandria', 'Pistoia', 'Guidonia Montecelio', 'Catanzaro', 'Brindisi', 'Torre del Greco', 'Marsala', 'Grosseto', 'Pozzuoli', 'Casoria', 'Caserta', 'Gela', 'Cinisello Balsamo', 'Ragusa', 'Asti', 'Lamezia Terme', 'Cosenza', 'Varese', 'Cremona', 'Carpi', 'Imola', 'Massa', 'Pavia', 'Vigevano', 'Legnano', 'Caltanissetta', 'Potenza', 'Caltanissetta', 'Potenza', 'Caltanissetta', 'Potenza'],
    'LV': ['Riga', 'Daugavpils', 'Liepāja', 'Jelgava', 'Jūrmala'],
    'LI': ['Vaduz', 'Schaan', 'Triesen', 'Balzers', 'Eschen'],
    'LT': ['Vilnius', 'Kaunas', 'Klaipėda', 'Šiauliai', 'Panevėžys'],
    'LU': ['Luxembourg', 'Esch-sur-Alzette', 'Differdange', 'Dudelange', 'Ettelbruck'],
    'MT': ['Valletta', 'Birkirkara', 'Mosta', 'Qormi', 'Żabbar'],
    'MD': ['Chișinău', 'Tiraspol', 'Bălți', 'Bender', 'Rîbnița'],
    'MC': ['Monaco'],
    'ME': ['Podgorica', 'Nikšić', 'Pljevlja', 'Bijelo Polje', 'Cetinje'],
    'NL': ['Amsterdam', 'Rotterdam', 'The Hague', 'Utrecht', 'Eindhoven'],
    'MK': ['Skopje', 'Bitola', 'Kumanovo', 'Prilep', 'Tetovo'],
    'NO': ['Oslo', 'Bergen', 'Trondheim', 'Stavanger', 'Kristiansand'],
    'PL': ['Warsaw', 'Krakow', 'Wroclaw', 'Poznan', 'Gdansk'],
    'PT': ['Lisbon', 'Porto', 'Covilha', 'Braga', 'Funchal'],
    'RO': ['Bucharest', 'Cluj-Napoca', 'Timisoara', 'Iasi', 'Constanta'],
    'RU': ['Moscow', 'Saint Petersburg', 'Novosibirsk', 'Yekaterinburg', 'Kazan', 'Nizhny Novgorod', 'Chelyabinsk', 'Omsk', 'Samara', 'Rostov-on-Don', 'Ufa', 'Krasnoyarsk', 'Voronezh', 'Perm', 'Volgograd', 'Krasnodar', 'Saratov', 'Tyumen', 'Tolyatti', 'Izhevsk', 'Barnaul', 'Ulyanovsk', 'Irkutsk', 'Khabarovsk', 'Yaroslavl', 'Vladivostok', 'Makhachkala', 'Tomsk', 'Orenburg', 'Kemerovo', 'Novokuznetsk', 'Ryazan', 'Naberezhnye Chelny', 'Astrakhan', 'Penza', 'Lipetsk', 'Kirov', 'Cheboksary', 'Kaliningrad', 'Tula', 'Kursk', 'Stavropol', 'Ulan-Ude', 'Sochi', 'Tver', 'Magnitogorsk', 'Ivanovo', 'Bryansk', 'Surgut', 'Belgorod', 'Nizhny Tagil', 'Arkhangelsk', 'Kaluga', 'Smolensk', 'Volzhsky', 'Cherepovets', 'Vladikavkaz', 'Chita', 'Saransk', 'Kurgan', 'Vladimir', 'Kostroma', 'Yakutsk', 'Petrozavodsk', 'Syktyvkar', 'Nalchik', 'Blagoveshchensk', 'Veliky Novgorod', 'Pskov', 'Murmansk', 'Magadan', 'Yuzhno-Sakhalinsk', 'Anadyr', 'Petropavlovsk-Kamchatsky', 'Norilsk', 'Nizhnevartovsk', 'Novy Urengoy', 'Noyabrsk', 'Nefteyugansk', 'Khanty-Mansiysk', 'Surgut', 'Nizhnevartovsk', 'Novy Urengoy', 'Noyabrsk', 'Nefteyugansk', 'Khanty-Mansiysk'],
    'SM': ['San Marino', 'Borgo Maggiore', 'Serravalle', 'Domagnano', 'Fiorentino'],
    'RS': ['Belgrade', 'Novi Sad', 'Niš', 'Kragujevac', 'Subotica'],
    'SK': ['Bratislava', 'Košice', 'Prešov', 'Žilina', 'Banská Bystrica'],
    'SI': ['Ljubljana', 'Maribor', 'Celje', 'Kranj', 'Velenje'],
    'ES': ['Madrid', 'Barcelona', 'Valencia', 'Seville', 'Bilbao', 'Zaragoza', 'Málaga', 'Murcia', 'Palma', 'Las Palmas', 'Valladolid', 'Córdoba', 'Vigo', 'Alicante', 'Gijón', 'Hospitalet de Llobregat', 'Granada', 'Vitoria-Gasteiz', 'A Coruña', 'Elche', 'Santa Cruz de Tenerife', 'Oviedo', 'Badalona', 'Cartagena', 'Terrassa', 'Jerez de la Frontera', 'Sabadell', 'Móstoles', 'Santa Coloma de Gramenet', 'Pamplona', 'Almería', 'Fuenlabrada', 'Leganés', 'Burgos', 'Santander', 'Castellón de la Plana', 'Alcorcón', 'Getafe', 'Salamanca', 'Huelva', 'Marbella', 'León', 'Tarragona', 'Cádiz', 'Lleida', 'Mataró', 'Dos Hermanas', 'Santa Lucía de Tirajana', 'Jaén', 'Ourense', 'Reus', 'Torrelavega', 'Algeciras', 'Mérida', 'Cáceres', 'Lorca', 'Coslada', 'Talavera de la Reina', 'El Puerto de Santa María', 'Ceuta', 'Melilla', 'Gandía', 'Sitges', 'San Sebastián', 'Marbella', 'Benidorm', 'Torremolinos', 'Fuengirola', 'Estepona', 'Nerja', 'Ronda', 'Granada', 'Córdoba', 'Seville', 'Jerez de la Frontera', 'Cádiz', 'Algeciras', 'Málaga', 'Marbella', 'Torremolinos', 'Fuengirola', 'Estepona', 'Nerja', 'Ronda'],
    'SE': ['Stockholm', 'Gothenburg', 'Malmö', 'Uppsala', 'Västerås'],
    'CH': ['Zurich', 'Geneva', 'Basel', 'Bern', 'Lausanne'],
    'GB': ['London', 'Manchester', 'Birmingham', 'Leeds', 'Glasgow', 'Liverpool', 'Edinburgh', 'Bristol', 'Cardiff', 'Belfast', 'Newcastle upon Tyne', 'Sheffield', 'Leicester', 'Coventry', 'Bradford', 'Nottingham', 'Kingston upon Hull', 'Plymouth', 'Stoke-on-Trent', 'Wolverhampton', 'Derby', 'Southampton', 'Portsmouth', 'Reading', 'Northampton', 'Luton', 'Bolton', 'Bournemouth', 'Norwich', 'Swindon', 'Southend-on-Sea', 'Peterborough', 'Middlesbrough', 'Sunderland', 'Brighton', 'West Bromwich', 'Ipswich', 'Warrington', 'Slough', 'Oxford', 'Cambridge', 'Doncaster', 'York', 'Exeter', 'Gloucester', 'Bath', 'Canterbury', 'Durham', 'Lincoln', 'Hereford', 'Lancaster', 'Carlisle', 'Ripon', 'Wells', 'Ely', 'Truro', 'Bangor', 'St. David\'s', 'Aberdeen', 'Dundee', 'Inverness', 'Perth', 'Stirling', 'Dumfries', 'Ayr', 'Kilmarnock', 'Greenock', 'Paisley', 'Motherwell', 'Livingston', 'Hamilton', 'Cumbernauld', 'East Kilbride', 'Airdrie', 'Falkirk', 'Kilmarnock', 'Greenock', 'Paisley', 'Motherwell', 'Livingston', 'Hamilton', 'Cumbernauld', 'East Kilbride', 'Airdrie', 'Falkirk'],
    'UA': ['Kyiv', 'Kharkiv', 'Odesa', 'Dnipro', 'Donetsk'],
    'VA': ['Vatican City'],
    
    // North America
    'AG': ['St. John\'s', 'All Saints', 'Liberta', 'Potter\'s Village', 'Bolans'],
    'BS': ['Nassau', 'Freeport', 'West End', 'Coopers Town', 'Marsh Harbour'],
    'BB': ['Bridgetown', 'Speightstown', 'Oistins', 'Holetown', 'Crane'],
    'BZ': ['Belize City', 'San Ignacio', 'Orange Walk', 'Dangriga', 'Corozal'],
    'CA': ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa', 'Edmonton', 'Winnipeg', 'Quebec City', 'Hamilton', 'Kitchener', 'London', 'Victoria', 'Halifax', 'Oshawa', 'Windsor', 'Saskatoon', 'Regina', 'Sherbrooke', 'St. John\'s', 'Barrie', 'Kelowna', 'Abbotsford', 'Sudbury', 'Kingston', 'Saguenay', 'Trois-Rivières', 'Guelph', 'Cambridge', 'Thunder Bay', 'Saint John', 'Moncton', 'Nanaimo', 'Kamloops', 'Chilliwack', 'Fredericton', 'Red Deer', 'Lethbridge', 'Saint-Jérôme', 'Sherbrooke', 'Trois-Rivières', 'Drummondville', 'Granby', 'Saint-Hyacinthe', 'Joliette', 'Shawinigan', 'Victoriaville', 'Rivière-du-Loup', 'Rimouski', 'Matane', 'Gaspé', 'Percé', 'Carleton-sur-Mer', 'New Richmond', 'Bonaventure', 'Chandler', 'Maria', 'Causapscal', 'Amqui', 'Sayabec', 'Lac-Mégantic', 'Thetford Mines', 'Asbestos', 'Val-d\'Or', 'Rouyn-Noranda', 'Amos', 'La Sarre', 'Ville-Marie', 'Témiscamingue', 'Notre-Dame-du-Nord', 'Angliers', 'Lorrainville', 'Villebois', 'Barraute', 'Senneterre', 'Malartic', 'Cadillac', 'Duparquet', 'Rapide-Danseur', 'Rivière-Héva', 'Rochebaucourt', 'Trécesson', 'Authier', 'Clerval', 'Gallichan', 'La Corne', 'La Morandière', 'La Motte', 'La Reine', 'Laforce', 'Landrienne', 'Launay', 'Lac-Simon', 'Macamic', 'Malartic', 'Moffet', 'Normétal', 'Palmarolle', 'Poularies', 'Preissac', 'Rapide-Danseur', 'Rivière-Héva', 'Rochebaucourt', 'Roquemaure', 'Saint-Dominique-du-Rosaire', 'Saint-Félix-de-Dalquier', 'Saint-Lambert', 'Sainte-Germaine-Boulé', 'Sainte-Hélène-de-Mancebourg', 'Sainte-Véronique', 'Senneterre', 'Taschereau', 'Trécesson', 'Val-d\'Or', 'Ville-Marie', 'Villebois', 'Wright'],
    'CR': ['San José', 'Cartago', 'Alajuela', 'Heredia', 'Liberia'],
    'CU': ['Havana', 'Santiago de Cuba', 'Camagüey', 'Holguín', 'Santa Clara'],
    'DM': ['Roseau', 'Portsmouth', 'Marigot', 'Berekua', 'Mahaut'],
    'DO': ['Santo Domingo', 'Santiago', 'La Romana', 'San Pedro de Macorís', 'San Cristóbal'],
    'SV': ['San Salvador', 'Santa Ana', 'San Miguel', 'Soyapango', 'Mejicanos'],
    'GD': ['St. George\'s', 'Gouyave', 'Grenville', 'Victoria', 'Sauteurs'],
    'GT': ['Guatemala City', 'Mixco', 'Villa Nueva', 'Quetzaltenango', 'Escuintla'],
    'HT': ['Port-au-Prince', 'Carrefour', 'Delmas', 'Pétion-Ville', 'Port-de-Paix'],
    'HN': ['Tegucigalpa', 'San Pedro Sula', 'Choloma', 'La Ceiba', 'El Progreso'],
    'JM': ['Kingston', 'Spanish Town', 'Portmore', 'Montego Bay', 'Mandeville'],
    'MX': ['Mexico City', 'Guadalajara', 'Monterrey', 'Cancun', 'Playa del Carmen'],
    'NI': ['Managua', 'León', 'Masaya', 'Chinandega', 'Matagalpa'],
    'PA': ['Panama City', 'San Miguelito', 'Tocumen', 'David', 'Colón'],
    'KN': ['Basseterre', 'Charlestown', 'Sandy Point Town', 'Dieppe Bay Town', 'Old Road Town'],
    'LC': ['Castries', 'Gros Islet', 'Vieux Fort', 'Soufrière', 'Dennery'],
    'VC': ['Kingstown', 'Georgetown', 'Byera Village', 'Biabou', 'Layou'],
    'TT': ['Port of Spain', 'San Fernando', 'Chaguanas', 'Arima', 'Couva'],
    'US': ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville', 'Fort Worth', 'Columbus', 'Charlotte', 'San Francisco', 'Indianapolis', 'Seattle', 'Denver', 'Washington', 'Boston', 'El Paso', 'Nashville', 'Detroit', 'Oklahoma City', 'Portland', 'Las Vegas', 'Memphis', 'Louisville', 'Baltimore', 'Milwaukee', 'Albuquerque', 'Tucson', 'Fresno', 'Sacramento', 'Kansas City', 'Mesa', 'Atlanta', 'Omaha', 'Colorado Springs', 'Raleigh', 'Virginia Beach', 'Miami', 'Oakland', 'Minneapolis', 'Tulsa', 'Cleveland', 'Wichita', 'Arlington', 'Tampa', 'New Orleans', 'Honolulu', 'Anaheim', 'Santa Ana', 'St. Louis', 'Riverside', 'Corpus Christi', 'Lexington', 'Henderson', 'Stockton', 'Saint Paul', 'Cincinnati', 'St. Petersburg', 'Pittsburgh', 'Greensboro', 'Lincoln', 'Buffalo', 'Plano', 'Newark', 'Toledo', 'Fort Wayne', 'St. Petersburg', 'Laredo', 'Jersey City', 'Chandler', 'Madison', 'Durham', 'Lubbock', 'Winston-Salem', 'Garland', 'Glendale', 'Baton Rouge', 'Hialeah', 'Norfolk', 'Reno', 'Chesapeake', 'Gilbert', 'Birmingham', 'Rochester', 'Scottsdale', 'Richmond', 'Spokane', 'Des Moines', 'Montgomery', 'Modesto', 'Fremont', 'Shreveport', 'Tacoma', 'Oxnard', 'Aurora', 'Fontana', 'Akron', 'Moreno Valley', 'Yonkers', 'Huntington Beach', 'Little Rock', 'Amarillo', 'Glendale', 'Mobile', 'Grand Rapids', 'Salt Lake City', 'Tallahassee', 'Huntsville', 'Grand Prairie', 'Knoxville', 'Worcester', 'Newport News', 'Brownsville', 'Overland Park', 'Santa Clarita', 'Providence', 'Garden Grove', 'Chattanooga', 'Oceanside', 'Jackson', 'Fort Lauderdale', 'Santa Rosa', 'Rancho Cucamonga', 'Port St. Lucie', 'Tempe', 'Ontario', 'Vancouver', 'Sioux Falls', 'Peoria', 'Springfield', 'Pembroke Pines', 'Elk Grove', 'Salem', 'Corona', 'Eugene', 'McKinney', 'Fort Collins', 'Lancaster', 'Cary', 'Palmdale', 'Hayward', 'Salinas', 'Frisco', 'Springfield', 'Pasadena', 'Macon', 'Alexandria', 'Pomona', 'Lakewood', 'Sunnyvale', 'Escondido', 'Hollywood', 'Kansas City', 'Joliet', 'Torrance', 'Bridgeport', 'Paterson', 'Naperville', 'Syracuse', 'McAllen', 'Pasadena', 'Mesquite', 'Dayton', 'Savannah', 'Fullerton', 'Orange', 'Miramar', 'Thornton', 'Roseville', 'Denton', 'Waco', 'Surprise', 'Carrollton', 'West Valley City', 'Warren', 'Hampton', 'Gainesville', 'Visalia', 'Coral Springs', 'Stamford', 'Cedar Rapids', 'New Haven', 'Concord', 'Kent', 'Santa Clara', 'Elizabeth', 'Round Rock', 'Thousand Oaks', 'Lafayette', 'Athens', 'Topeka', 'Simi Valley', 'Fargo', 'Norman', 'Columbia', 'Abilene', 'Wilmington', 'Hartford', 'Victorville', 'Pearland', 'Vallejo', 'Ann Arbor', 'Berkeley', 'Allentown', 'Richardson', 'Odessa', 'Arvada', 'St. George', 'Cambridge', 'Sugar Land', 'Texas City', 'Iowa City', 'Chico', 'Boulder', 'Provo', 'Fayetteville', 'Green Bay', 'Wichita Falls', 'Racine', 'Davenport', 'Erie', 'South Bend', 'Evansville', 'Tuscaloosa', 'Spartanburg', 'Lakeland', 'Boulder', 'Provo', 'Fayetteville', 'Green Bay', 'Wichita Falls', 'Racine', 'Davenport', 'Erie', 'South Bend', 'Evansville', 'Tuscaloosa', 'Spartanburg', 'Lakeland'],
    
    // South America
    'AR': ['Buenos Aires', 'Córdoba', 'Rosario', 'Mendoza', 'La Plata'],
    'BO': ['La Paz', 'Santa Cruz', 'Cochabamba', 'Sucre', 'Oruro'],
    'BR': ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Salvador', 'Fortaleza', 'Belo Horizonte', 'Manaus', 'Curitiba', 'Recife', 'Porto Alegre', 'Belém', 'Goiânia', 'Guarulhos', 'Campinas', 'São Luís', 'São Gonçalo', 'Maceió', 'Duque de Caxias', 'Natal', 'Teresina', 'Campo Grande', 'Nova Iguaçu', 'São Bernardo do Campo', 'João Pessoa', 'Santo André', 'Osasco', 'Jaboatão dos Guararapes', 'São José dos Campos', 'Ribeirão Preto', 'Uberlândia', 'Contagem', 'Aracaju', 'Feira de Santana', 'Cuiabá', 'Joinville', 'Juiz de Fora', 'Londrina', 'Aparecida de Goiânia', 'Niterói', 'Ananindeua', 'Porto Velho', 'Campos dos Goytacazes', 'Mauá', 'Caxias do Sul', 'Betim', 'Olinda', 'Carapicuíba', 'Anápolis', 'Vila Velha', 'Serra', 'Diadema', 'Cariacica', 'Bauru', 'Campina Grande', 'Montes Claros', 'Jundiaí', 'Piracicaba', 'Caruaru', 'Rio Branco', 'Vitória', 'Caucaia', 'Blumenau', 'Franca', 'Ponta Grossa', 'Petrolina', 'Paulista', 'Ribeirão das Neves', 'Uberaba', 'Volta Redonda', 'Novo Hamburgo', 'Maringá', 'Barueri', 'Várzea Grande', 'Foz do Iguaçu', 'São José de Ribamar', 'Macapá', 'Suzano', 'Magé', 'Santa Maria', 'São João de Meriti', 'Mogi das Cruzes', 'Governador Valadares', 'Santarém', 'Barra Mansa', 'Taubaté', 'Imperatriz', 'Viamão', 'Arapiraca', 'Petrópolis', 'Cabo Frio', 'Itaquaquecetuba', 'Araçatuba', 'Praia Grande', 'Cascavel', 'São Vicente', 'Rio Claro', 'Marília', 'Cotia', 'Americana', 'Juazeiro do Norte', 'Mossoró', 'Dourados', 'Sorocaba', 'Caxias', 'Chapecó', 'Itabuna', 'Criciúma', 'Limeira', 'Jequié', 'Rio Verde', 'Alvorada', 'Sete Lagoas', 'Maracanaú', 'Divinópolis', 'Arapongas', 'Colombo', 'São Caetano do Sul', 'Itu', 'Cabo de Santo Agostinho', 'Passo Fundo', 'Luziânia', 'Palmas', 'Parnamirim', 'Poços de Caldas', 'Angra dos Reis', 'Foz do Iguaçu', 'São José de Ribamar', 'Macapá', 'Suzano', 'Magé', 'Santa Maria', 'São João de Meriti', 'Mogi das Cruzes', 'Governador Valadares', 'Santarém', 'Barra Mansa', 'Taubaté', 'Imperatriz', 'Viamão', 'Arapiraca', 'Petrópolis', 'Cabo Frio', 'Itaquaquecetuba', 'Araçatuba', 'Praia Grande', 'Cascavel', 'São Vicente', 'Rio Claro', 'Marília', 'Cotia', 'Americana', 'Juazeiro do Norte', 'Mossoró', 'Dourados', 'Sorocaba', 'Caxias', 'Chapecó', 'Itabuna', 'Criciúma', 'Limeira', 'Jequié', 'Rio Verde', 'Alvorada', 'Sete Lagoas', 'Maracanaú', 'Divinópolis', 'Arapongas', 'Colombo', 'São Caetano do Sul', 'Itu', 'Cabo de Santo Agostinho', 'Passo Fundo', 'Luziânia', 'Palmas', 'Parnamirim', 'Poços de Caldas', 'Angra dos Reis'],
    'CL': ['Santiago', 'Valparaíso', 'Concepción', 'La Serena', 'Temuco'],
    'CO': ['Bogotá', 'Medellín', 'Cali', 'Barranquilla', 'Cartagena'],
    'EC': ['Quito', 'Guayaquil', 'Cuenca', 'Santo Domingo', 'Machala'],
    'GY': ['Georgetown', 'Linden', 'New Amsterdam', 'Anna Regina', 'Bartica'],
    'PY': ['Asunción', 'Ciudad del Este', 'San Lorenzo', 'Luque', 'Capiatá'],
    'PE': ['Lima', 'Arequipa', 'Cusco', 'Trujillo', 'Iquitos'],
    'SR': ['Paramaribo', 'Lelydorp', 'Nieuw Nickerie', 'Moengo', 'Meerzorg'],
    'UY': ['Montevideo', 'Salto', 'Ciudad de la Costa', 'Paysandú', 'Las Piedras'],
    'VE': ['Caracas', 'Maracaibo', 'Valencia', 'Barquisimeto', 'Maracay'],
    
    // Oceania
    'AU': ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide'],
    'FJ': ['Suva', 'Lautoka', 'Nadi', 'Labasa', 'Ba'],
    'KI': ['Tarawa', 'Betio', 'Bikenibeu', 'Teaoraereke', 'Bairiki'],
    'MH': ['Majuro', 'Ebeye', 'Jaluit', 'Wotje', 'Kwajalein'],
    'FM': ['Palikir', 'Weno', 'Colonia', 'Kolonia', 'Tofol'],
    'NR': ['Yaren', 'Arijejen', 'Anabar', 'Anetan', 'Baiti'],
    'NZ': ['Auckland', 'Wellington', 'Christchurch', 'Hamilton', 'Tauranga'],
    'PW': ['Ngerulmud', 'Koror', 'Melekeok', 'Airai', 'Kloulklubed'],
    'PG': ['Port Moresby', 'Lae', 'Arawa', 'Mount Hagen', 'Popondetta'],
    'WS': ['Apia', 'Vaitele', 'Faleula', 'Siusega', 'Malie'],
    'SB': ['Honiara', 'Auki', 'Gizo', 'Kirakira', 'Buala'],
    'TO': ['Nuku\'alofa', 'Neiafu', 'Haveluloto', 'Vaini', 'Pangai'],
    'TV': ['Funafuti', 'Vaiaku', 'Fongafale', 'Asau', 'Savave'],
    'VU': ['Port Vila', 'Luganville', 'Norsup', 'Isangel', 'Lakatoro'],
  }
  
  // CRITICAL: Log the exact lookup being performed
  console.log(`[getCitiesByCountry] Looking up cities for code: "${normalizedCode}" (original: "${countryCode}")`)
  
  // CRITICAL: Use explicit key check - do NOT use hasOwnProperty as it might have issues
  // Instead, check if the key exists in the object using 'in' operator
  if (!(normalizedCode in citiesByCountry)) {
    console.error(`[getCitiesByCountry] ERROR: No cities found for country code: "${normalizedCode}"`)
    const availableCodes = Object.keys(citiesByCountry).slice(0, 20)
    console.error(`[getCitiesByCountry] Available country codes (first 20):`, availableCodes)
    return []
  }
  
  // Get cities - create a fresh array immediately to prevent any reference issues
  const rawCities = citiesByCountry[normalizedCode]
  
  if (!rawCities || !Array.isArray(rawCities) || rawCities.length === 0) {
    console.warn(`[getCitiesByCountry] Invalid cities data for country code: ${normalizedCode}`)
    return []
  }
  
  // STEP 1: Remove duplicates within the city list itself
  const seenCities = new Set<string>()
  let cities = rawCities.filter(city => {
    const normalizedCity = city.trim()
    if (seenCities.has(normalizedCity)) {
      return false // Duplicate, skip it
    }
    seenCities.add(normalizedCity)
    return true
  })
  
  console.log(`[getCitiesByCountry] Found ${rawCities.length} cities, ${cities.length} after removing duplicates for ${normalizedCode}. First city: "${cities[0]}"`)
  
  // STEP 2: Build comprehensive maps of ALL cities by country (for validation)
  const allCitiesByCountry: Record<string, Set<string>> = {}
  for (const [code, cityList] of Object.entries(citiesByCountry)) {
    if (Array.isArray(cityList)) {
      // Remove duplicates and normalize
      const uniqueCities = new Set(cityList.map(c => c.trim()))
      allCitiesByCountry[code] = uniqueCities
    }
  }
  
  // STEP 3: Get the CORRECT cities for this country (what should be there)
  const correctCitiesSet = allCitiesByCountry[normalizedCode] || new Set()
  
  // STEP 4: Filter out ANY city that appears in OTHER countries but NOT in this country's correct list
  const beforeFilter = cities.length
  const filteredCities: string[] = []
  const removedCities: string[] = []
  
  for (const city of cities) {
    const normalizedCity = city.trim()
    
    // Check if this city is in the correct list for this country
    if (correctCitiesSet.has(normalizedCity)) {
      // This city belongs to this country - keep it
      filteredCities.push(city)
    } else {
      // This city is NOT in the correct list - check if it belongs to another country
      let belongsToOtherCountry = false
      for (const [otherCode, otherCitiesSet] of Object.entries(allCitiesByCountry)) {
        if (otherCode !== normalizedCode && otherCitiesSet.has(normalizedCity)) {
          belongsToOtherCountry = true
          removedCities.push(`${city} (from ${otherCode})`)
          break
        }
      }
      
      if (!belongsToOtherCountry) {
        // City doesn't appear in any country's list - might be a typo or new city, keep it
        filteredCities.push(city)
      }
    }
  }
  
  cities = filteredCities
  
  if (removedCities.length > 0) {
    console.error(`[VALIDATION ERROR] Removed ${removedCities.length} cities from other countries in ${normalizedCode}:`, removedCities.slice(0, 10))
  }
  
  // STEP 5: Additional validation - check if first cities match patterns from other countries
  if (cities.length > 0) {
    const first5 = cities.slice(0, 5)
    
    for (const [otherCode, otherCitiesSet] of Object.entries(allCitiesByCountry)) {
      if (otherCode !== normalizedCode) {
        // Get first 5 cities from that country
        const otherCitiesArray = Array.from(otherCitiesSet).slice(0, 5)
        
        // Check for exact positional matches
        let exactMatches = 0
        for (let i = 0; i < Math.min(5, first5.length, otherCitiesArray.length); i++) {
          if (first5[i].trim() === otherCitiesArray[i]) {
            exactMatches++
          }
        }
        
        if (exactMatches >= 3) {
          console.error(`[CRITICAL ERROR] First 5 cities match ${otherCode} pattern! Matches: ${exactMatches}/5`)
          console.error(`[CRITICAL ERROR] Requested: ${normalizedCode}, Detected: ${otherCode}`)
          console.error(`[CRITICAL ERROR] First 5:`, first5)
          console.error(`[CRITICAL ERROR] ${otherCode} first 5:`, otherCitiesArray)
          return []
        }
      }
    }
  }
  
  // STEP 6: Final validation
  if (cities.length === 0) {
    console.warn(`[getCitiesByCountry] No valid cities remaining after filtering for ${normalizedCode}`)
    return []
  }
  
  // Remove any remaining duplicates (safety check)
  const finalCities: string[] = []
  const finalSeen = new Set<string>()
  for (const city of cities) {
    const normalizedCity = city.trim()
    if (!finalSeen.has(normalizedCity)) {
      finalSeen.add(normalizedCity)
      finalCities.push(city)
    }
  }
  
  console.log(`[getCitiesByCountry] ✓ Returning ${finalCities.length} unique, validated cities for ${normalizedCode}. First 3:`, finalCities.slice(0, 3))
  return finalCities
}
