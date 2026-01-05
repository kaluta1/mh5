/**
 * Service de cache pour les requêtes API
 * Utilise localStorage pour persister le cache entre les sessions
 */

interface CacheEntry<T> {
  data: T
  timestamp: number
  ttl: number // Time to live en millisecondes
}

class CacheService {
  private cache: Map<string, CacheEntry<any>> = new Map()
  private readonly DEFAULT_TTL = 10 * 60 * 1000 // 5 minutes par défaut
  private readonly STORAGE_KEY = 'api_cache'
  private enabled: boolean = true // Cache activé

  constructor() {
    this.loadFromStorage()
    // Nettoyer le cache expiré au démarrage
    this.cleanExpired()
  }

  /**
   * Active ou désactive le cache
   */
  setEnabled(enabled: boolean): void {
    this.enabled = enabled
    if (!enabled) {
      // Si désactivé, vider le cache
      this.clear()
    }
  }

  /**
   * Vérifie si le cache est activé
   */
  isEnabled(): boolean {
    return this.enabled
  }

  /**
   * Charge le cache depuis localStorage
   */
  private loadFromStorage(): void {
    if (typeof window === 'undefined') return

    try {
      const stored = localStorage.getItem(this.STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        const now = Date.now()
        
        // Ne charger que les entrées non expirées
        for (const [key, entry] of Object.entries(parsed)) {
          const cacheEntry = entry as CacheEntry<any>
          if (now - cacheEntry.timestamp < cacheEntry.ttl) {
            this.cache.set(key, cacheEntry)
          }
        }
      }
    } catch (error) {
      console.warn('Erreur lors du chargement du cache:', error)
    }
  }

  /**
   * Sauvegarde le cache dans localStorage
   */
  private saveToStorage(): void {
    if (typeof window === 'undefined') return

    try {
      const cacheObj: Record<string, CacheEntry<any>> = {}
      this.cache.forEach((value, key) => {
        cacheObj[key] = value
      })
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(cacheObj))
    } catch (error) {
      console.warn('Erreur lors de la sauvegarde du cache:', error)
      // Si localStorage est plein, nettoyer les anciennes entrées
      this.cleanExpired()
    }
  }

  /**
   * Génère une clé de cache à partir de l'endpoint et des paramètres
   */
  private generateKey(endpoint: string, params?: any): string {
    const paramsStr = params ? JSON.stringify(params) : ''
    return `${endpoint}${paramsStr ? `?${paramsStr}` : ''}`
  }

  /**
   * Récupère une valeur du cache
   */
  get<T>(endpoint: string, params?: any): T | null {
    if (!this.enabled) {
      return null
    }

    const key = this.generateKey(endpoint, params)
    const entry = this.cache.get(key)

    if (!entry) {
      return null
    }

    // Vérifier si l'entrée est expirée
    const now = Date.now()
    if (now - entry.timestamp >= entry.ttl) {
      this.cache.delete(key)
      this.saveToStorage()
      return null
    }

    return entry.data as T
  }

  /**
   * Met une valeur en cache
   */
  set<T>(endpoint: string, data: T, params?: any, ttl?: number): void {
    if (!this.enabled) {
      return
    }

    const key = this.generateKey(endpoint, params)
    const entry: CacheEntry<T> = {
      data,
      timestamp: Date.now(),
      ttl: ttl || this.DEFAULT_TTL
    }

    this.cache.set(key, entry)
    this.saveToStorage()
  }

  /**
   * Invalide le cache pour un endpoint spécifique ou un pattern
   */
  invalidate(endpoint?: string, pattern?: string): void {
    if (!this.enabled) {
      return
    }

    if (endpoint) {
      // Invalider toutes les clés qui commencent par cet endpoint
      const keysToDelete: string[] = []
      this.cache.forEach((_, key) => {
        if (key.startsWith(endpoint)) {
          keysToDelete.push(key)
        }
      })
      keysToDelete.forEach(key => this.cache.delete(key))
    } else if (pattern) {
      // Invalider toutes les clés qui correspondent au pattern
      const regex = new RegExp(pattern)
      const keysToDelete: string[] = []
      this.cache.forEach((_, key) => {
        if (regex.test(key)) {
          keysToDelete.push(key)
        }
      })
      keysToDelete.forEach(key => this.cache.delete(key))
    } else {
      // Invalider tout le cache
      this.cache.clear()
    }

    this.saveToStorage()
  }

  /**
   * Nettoie les entrées expirées du cache
   */
  cleanExpired(): void {
    const now = Date.now()
    const keysToDelete: string[] = []

    this.cache.forEach((entry, key) => {
      if (now - entry.timestamp >= entry.ttl) {
        keysToDelete.push(key)
      }
    })

    keysToDelete.forEach(key => this.cache.delete(key))
    
    if (keysToDelete.length > 0) {
      this.saveToStorage()
    }
  }

  /**
   * Vide complètement le cache
   */
  clear(): void {
    this.cache.clear()
    if (typeof window !== 'undefined') {
      localStorage.removeItem(this.STORAGE_KEY)
    }
  }

  /**
   * Retourne la taille du cache
   */
  size(): number {
    return this.cache.size
  }
}

export const cacheService = new CacheService()

// Nettoyer le cache expiré toutes les 5 minutes
if (typeof window !== 'undefined') {
  setInterval(() => {
    cacheService.cleanExpired()
  }, 10 * 60 * 1000)
}

