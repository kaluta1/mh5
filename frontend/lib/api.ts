import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { cacheService } from './cache-service'
import { logger } from './logger'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://mh5-hbjp.onrender.com'

// Créer une instance axios avec la configuration de base
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 0, // No timeout
  headers: {
    'Content-Type': 'application/json',
  },
})

// Instance séparée pour les requêtes d'authentification avec timeout plus long
// (Render.com backends can be slow to wake up from sleep)
const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 0, // No timeout
  headers: {
    'Content-Type': 'application/json',
  },
})

// Helper pour ajouter les headers communs
const addCommonHeaders = (config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // Ajouter la langue depuis localStorage si disponible
  const savedLanguage = localStorage.getItem('myhigh5-language')
  if (savedLanguage && ['en', 'fr', 'es', 'de'].includes(savedLanguage)) {
    config.headers['Accept-Language'] = savedLanguage
  }
  return config
}

// Intercepteur pour ajouter le token d'authentification et la langue
api.interceptors.request.use(
  (config) => addCommonHeaders(config),
  (error) => {
    return Promise.reject(error)
  }
)

// Intercepteur pour authApi (même configuration mais timeout plus court)
authApi.interceptors.request.use(
  (config) => addCommonHeaders(config),
  (error) => {
    return Promise.reject(error)
  }
)

// Intercepteur pour gérer les réponses et erreurs avec retry logic
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as InternalAxiosRequestConfig & { _retry?: boolean; _retryCount?: number }

    // Retry logic pour les erreurs de timeout ou réseau (mais pas pour les requêtes d'auth)
    const isAuthRequest = config?.url?.includes('/auth/')

    if (
      config &&
      !config._retry &&
      !isAuthRequest && // Don't retry auth requests - they have their own timeout
      (error.code === 'ECONNABORTED' ||
        error.message?.includes('timeout') ||
        error.message?.includes('Network Error') ||
        !error.response)
    ) {
      const retryCount = config._retryCount || 0
      const maxRetries = 1 // Reduced to 1 retry for faster failure

      if (retryCount < maxRetries) {
        config._retry = true
        config._retryCount = retryCount + 1

        // Shorter backoff: 500ms
        const delay = 500
        logger.warn(`Request timeout/error, retrying (${retryCount + 1}/${maxRetries}) after ${delay}ms...`)

        await new Promise(resolve => setTimeout(resolve, delay))

        return api(config)
      }
    }

    // Gestion des erreurs 401 (non autorisé)
    if (error.response?.status === 401) {
      // Ne pas rediriger si c'est une tentative de connexion (erreur normale)
      const isLoginAttempt = config?.url?.includes('/auth/login')
      const isRegisterAttempt = config?.url?.includes('/auth/register')

      // Si ce n'est pas une tentative de connexion/inscription, c'est un token expiré
      if (!isLoginAttempt && !isRegisterAttempt) {
        // Token expiré, supprimer le token et le cache
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        cacheService.clear()
        // Utiliser router.push au lieu de window.location.href pour éviter le rechargement
        // Note: On ne peut pas utiliser useRouter ici, donc on laisse le composant gérer la redirection
        // window.location.href = '/login'
      }
    }

    return Promise.reject(error)
  }
)

// Types pour l'authentification
export interface LoginRequest {
  email_or_username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: {
    id: number
    email: string
    username: string
    full_name?: string
    avatar_url?: string
    is_active: boolean
    is_verified: boolean
  }
}

export interface RegisterRequest {
  email: string
  username: string
  password: string
  full_name?: string
  country?: string
  city?: string
  region?: string
  continent?: string
  sponsor_code?: string  // Code de parrainage optionnel
}

export interface PasswordResetRequest {
  email: string
}

export interface PasswordResetConfirm {
  token: string
  new_password: string
}

// Services d'authentification
export const authService = {
  // Vérifier si l'utilisateur est authentifié
  isAuthenticated(): boolean {
    if (typeof window === 'undefined') return false
    const token = localStorage.getItem('access_token')
    return !!token
  },

  // Obtenir les informations de l'utilisateur actuel
  async getCurrentUser(): Promise<LoginResponse['user']> {
    const response = await api.get('/api/v1/auth/me')
    return response.data
  },

  // Connexion (utilise authApi avec timeout plus court)
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    // Convertir en URLSearchParams pour OAuth2PasswordRequestForm (application/x-www-form-urlencoded)
    const params = new URLSearchParams()
    params.append('username', credentials.email_or_username)
    params.append('password', credentials.password)

    const response = await authApi.post('/api/v1/auth/login', params.toString(), {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    })
    const data = response.data

    // Sauvegarder les tokens
    if (data.access_token) {
      localStorage.setItem('access_token', data.access_token)
    }
    if (data.refresh_token) {
      localStorage.setItem('refresh_token', data.refresh_token)
    }

    return data
  },

  // Inscription
  async register(userData: RegisterRequest): Promise<LoginResponse> {
    const { sponsor_code, ...userDataWithoutSponsor } = userData

    // Construire l'URL avec le code de parrainage en query param si présent
    const url = sponsor_code
      ? `/api/v1/auth/register?sponsor_code=${encodeURIComponent(sponsor_code)}`
      : '/api/v1/auth/register'

    const response = await api.post(url, userDataWithoutSponsor)
    return response.data
  },

  // Déconnexion
  async logout(): Promise<void> {
    try {
      await api.post('/api/v1/auth/logout')
    } catch (error) {
      logger.error('Erreur lors de la déconnexion', error)
    } finally {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      // Supprimer tout le cache lors de la déconnexion
      cacheService.clear()
    }
  },

  // Demande de réinitialisation de mot de passe
  async requestPasswordReset(email: string): Promise<void> {
    await api.post('/api/v1/auth/password-reset-request', { email })
  },

  // Confirmation de réinitialisation de mot de passe
  async confirmPasswordReset(data: PasswordResetConfirm): Promise<void> {
    await api.post('/api/v1/auth/password-reset-confirm', data)
  },

  // Vérifier l'email avec un token
  async verifyEmail(token: string): Promise<{ message: string; email: string }> {
    const response = await api.post(`/api/v1/auth/verify-email?token=${encodeURIComponent(token)}`)
    return response.data
  },

  // Obtenir le token d'accès
  getAccessToken(): string | null {
    return localStorage.getItem('access_token')
  }
}

// Service générique pour les autres appels API (cache géré côté backend avec Redis)
export const apiService = {
  // GET request (cache géré côté backend)
  async get<T>(endpoint: string, params?: Record<string, unknown>, useCache?: boolean): Promise<T> {
    // Le cache est maintenant géré côté backend avec Redis
    const response = await api.get(endpoint, { params })
    return response.data
  },

  // POST request
  async post<T>(endpoint: string, data?: unknown, invalidateCache?: string, config?: Record<string, unknown>): Promise<T> {
    const response = await api.post(endpoint, data, config)
    return response.data
  },

  // PUT request
  async put<T>(endpoint: string, data?: unknown, invalidateCache?: string): Promise<T> {
    const response = await api.put(endpoint, data)
    return response.data
  },

  // DELETE request
  async delete<T>(endpoint: string, invalidateCache?: string): Promise<T> {
    const response = await api.delete(endpoint)
    return response.data
  }
}

export default api
