const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface LocationData {
  id: number
  name: string
}

class LocationService {
  private token: string | null = null

  setToken(token: string) {
    this.token = token
  }

  private getHeaders() {
    return {
      'Content-Type': 'application/json',
      ...(this.token && { 'Authorization': `Bearer ${this.token}` }),
    }
  }

  // Continents
  async getContinents(): Promise<LocationData[]> {
    const response = await fetch(`${API_BASE}/api/v1/geography/continents`, {
      headers: this.getHeaders(),
    })
    if (!response.ok) throw new Error('Failed to fetch continents')
    return response.json()
  }

  async createOrGetContinent(name: string): Promise<LocationData> {
    const response = await fetch(`${API_BASE}/api/v1/geography/continents`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ name }),
    })
    if (!response.ok) throw new Error('Failed to create continent')
    return response.json()
  }

  // Regions
  async getRegionsByContinent(continentId: number): Promise<LocationData[]> {
    const response = await fetch(`${API_BASE}/api/v1/geography/continents/${continentId}/regions`, {
      headers: this.getHeaders(),
    })
    if (!response.ok) throw new Error('Failed to fetch regions')
    return response.json()
  }

  async createOrGetRegion(name: string, continentId: number): Promise<LocationData> {
    const response = await fetch(`${API_BASE}/api/v1/geography/regions`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ name, continent_id: continentId }),
    })
    if (!response.ok) throw new Error('Failed to create region')
    return response.json()
  }

  // Countries
  async getCountriesByRegion(regionId: number): Promise<LocationData[]> {
    const response = await fetch(`${API_BASE}/api/v1/geography/regions/${regionId}/countries`, {
      headers: this.getHeaders(),
    })
    if (!response.ok) throw new Error('Failed to fetch countries')
    return response.json()
  }

  async createOrGetCountry(name: string, regionId: number): Promise<LocationData> {
    const response = await fetch(`${API_BASE}/api/v1/geography/countries`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ name, region_id: regionId }),
    })
    if (!response.ok) throw new Error('Failed to create country')
    return response.json()
  }

  // Cities
  async getCitiesByCountry(countryId: number): Promise<LocationData[]> {
    const response = await fetch(`${API_BASE}/api/v1/geography/countries/${countryId}/cities`, {
      headers: this.getHeaders(),
    })
    if (!response.ok) throw new Error('Failed to fetch cities')
    return response.json()
  }

  async createOrGetCity(name: string, countryId: number): Promise<LocationData> {
    const response = await fetch(`${API_BASE}/api/v1/geography/cities`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ name, country_id: countryId }),
    })
    if (!response.ok) throw new Error('Failed to create city')
    return response.json()
  }
}

export const locationService = new LocationService()
