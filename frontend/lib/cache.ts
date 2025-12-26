/**
 * Système de cache pour les APIs avec expiration de 24h
 * Recharge seulement quand il y a une nouvelle entrée
 */

interface CacheEntry<T> {
  data: T
  timestamp: number
  version?: string // Version du cache pour détecter les nouvelles entrées
}

const CACHE_DURATION = 24 * 60 * 60 * 1000 // 24 heures en millisecondes
const CACHE_PREFIX = 'api_cache_'

class ApiCache {
  /**
   * Génère une clé de cache à partir d'une URL et de paramètres
   */
  private getCacheKey(url: string, params?: any): string {
    const paramsStr = params ? JSON.stringify(params) : ''
    return `${CACHE_PREFIX}${url}_${paramsStr}`
  }

  /**
   * Vérifie si une entrée de cache est valide (non expirée)
   */
  private isValid(entry: CacheEntry<any> | null): boolean {
    if (!entry) return false
    const now = Date.now()
    return (now - entry.timestamp) < CACHE_DURATION
  }

  /**
   * Récupère une entrée du cache
   */
  get<T>(url: string, params?: any): T | null {
    if (typeof window === 'undefined') return null
    
    try {
      const key = this.getCacheKey(url, params)
      const cached = localStorage.getItem(key)
      
      if (!cached) return null
      
      const entry: CacheEntry<T> = JSON.parse(cached)
      
      if (this.isValid(entry)) {
        return entry.data
      } else {
        // Cache expiré, le supprimer
        localStorage.removeItem(key)
        return null
      }
    } catch (error) {
      console.error('Error reading from cache:', error)
      return null
    }
  }

  /**
   * Stocke une entrée dans le cache
   */
  set<T>(url: string, data: T, params?: any, version?: string): void {
    if (typeof window === 'undefined') return
    
    try {
      const key = this.getCacheKey(url, params)
      const entry: CacheEntry<T> = {
        data,
        timestamp: Date.now(),
        version
      }
      localStorage.setItem(key, JSON.stringify(entry))
    } catch (error) {
      console.error('Error writing to cache:', error)
      // Si le localStorage est plein, nettoyer les anciennes entrées
      this.cleanExpired()
    }
  }

  /**
   * Vérifie si une nouvelle version est disponible
   * Compare la version du cache avec la version actuelle
   */
  hasNewVersion(url: string, params: any, currentVersion: string): boolean {
    const key = this.getCacheKey(url, params)
    const cached = localStorage.getItem(key)
    
    if (!cached) return true // Pas de cache, donc nouvelle version
    
    try {
      const entry: CacheEntry<any> = JSON.parse(cached)
      return entry.version !== currentVersion
    } catch {
      return true
    }
  }

  /**
   * Invalide le cache pour une URL spécifique
   */
  invalidate(url: string, params?: any): void {
    if (typeof window === 'undefined') return
    
    if (params !== undefined) {
      // Invalider une variante spécifique
      const key = this.getCacheKey(url, params)
      localStorage.removeItem(key)
    } else {
      // Invalider toutes les variantes de cet endpoint
      const keys = Object.keys(localStorage)
      const urlPrefix = `${CACHE_PREFIX}${url}_`
      keys.forEach(key => {
        if (key.startsWith(urlPrefix)) {
          localStorage.removeItem(key)
        }
      })
    }
  }

  /**
   * Invalide tout le cache
   */
  clear(): void {
    if (typeof window === 'undefined') return
    
    const keys = Object.keys(localStorage)
    keys.forEach(key => {
      if (key.startsWith(CACHE_PREFIX)) {
        localStorage.removeItem(key)
      }
    })
  }

  /**
   * Nettoie les entrées expirées
   */
  cleanExpired(): void {
    if (typeof window === 'undefined') return
    
    const keys = Object.keys(localStorage)
    keys.forEach(key => {
      if (key.startsWith(CACHE_PREFIX)) {
        try {
          const cached = localStorage.getItem(key)
          if (cached) {
            const entry: CacheEntry<any> = JSON.parse(cached)
            if (!this.isValid(entry)) {
              localStorage.removeItem(key)
            }
          }
        } catch {
          localStorage.removeItem(key)
        }
      }
    })
  }

  /**
   * Récupère la version actuelle du cache pour une URL
   */
  getVersion(url: string, params?: any): string | null {
    const key = this.getCacheKey(url, params)
    const cached = localStorage.getItem(key)
    
    if (!cached) return null
    
    try {
      const entry: CacheEntry<any> = JSON.parse(cached)
      return entry.version || null
    } catch {
      return null
    }
  }
}

export const apiCache = new ApiCache()

// Nettoyer les entrées expirées au démarrage
if (typeof window !== 'undefined') {
  apiCache.cleanExpired()
}

