import api from '@/lib/api'

export interface Continent {
  id: number
  name: string
  code?: string
}

export interface Region {
  id: number
  name: string
  continent_id: number
}

export interface Country {
  id: number
  name: string
  code: string
  region_id: number
}

export interface City {
  id: number
  name: string
  country_id: number
}

class GeographyService {
  /**
   * Récupère tous les continents
   */
  async getContinents(): Promise<Continent[]> {
    try {
      const response = await api.get('/api/v1/geography/continents')
      return response.data
    } catch (error) {
      console.error('Error fetching continents:', error)
      throw error
    }
  }

  /**
   * Récupère les régions d'un continent
   */
  async getRegionsByContinent(continentId: number): Promise<Region[]> {
    try {
      const response = await api.get(`/api/v1/geography/continents/${continentId}/regions`)
      return response.data
    } catch (error) {
      console.error('Error fetching regions:', error)
      throw error
    }
  }

  /**
   * Récupère les pays d'une région
   */
  async getCountriesByRegion(regionId: number): Promise<Country[]> {
    try {
      const response = await api.get(`/api/v1/geography/regions/${regionId}/countries`)
      return response.data
    } catch (error) {
      console.error('Error fetching countries:', error)
      throw error
    }
  }

  /**
   * Récupère les villes d'un pays
   */
  async getCitiesByCountry(countryId: number): Promise<City[]> {
    try {
      const response = await api.get(`/api/v1/geography/countries/${countryId}/cities`)
      return response.data
    } catch (error) {
      console.error('Error fetching cities:', error)
      throw error
    }
  }

  /**
   * Crée un nouveau continent
   */
  async createContinent(name: string, code?: string): Promise<Continent> {
    try {
      const response = await api.post('/api/v1/geography/continents', {
        name,
        code
      })
      return response.data
    } catch (error) {
      console.error('Error creating continent:', error)
      throw error
    }
  }

  /**
   * Crée une nouvelle région
   */
  async createRegion(name: string, continentId: number): Promise<Region> {
    try {
      const response = await api.post('/api/v1/geography/regions', {
        name,
        continent_id: continentId
      })
      return response.data
    } catch (error) {
      console.error('Error creating region:', error)
      throw error
    }
  }

  /**
   * Crée un nouveau pays
   */
  async createCountry(name: string, code: string, regionId: number): Promise<Country> {
    try {
      const response = await api.post('/api/v1/geography/countries', {
        name,
        code,
        region_id: regionId
      })
      return response.data
    } catch (error) {
      console.error('Error creating country:', error)
      throw error
    }
  }

  /**
   * Crée une nouvelle ville
   */
  async createCity(name: string, countryId: number): Promise<City> {
    try {
      const response = await api.post('/api/v1/geography/cities', {
        name,
        country_id: countryId
      })
      return response.data
    } catch (error) {
      console.error('Error creating city:', error)
      throw error
    }
  }
}

export const geographyService = new GeographyService()
