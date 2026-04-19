import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { cacheService } from './cache-service'
import { logger } from './logger'
import { API_URL } from './config'
import { LANGUAGE_PREFERENCE_KEY } from './language-cookie'
import { languages } from './translations'

// Must match lib/config.ts (localhost in dev when NEXT_PUBLIC_API_URL is unset — not always myhigh5.com).
const API_BASE_URL = API_URL.replace(/\/+$/, '')

// Instance axios pour les appels API (optimized for speed)
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // Increased to 30s to handle slow backend responses (Render cold starts)
  headers: {
    'Content-Type': 'application/json',
  },
  // Performance optimizations
  maxRedirects: 3,
  validateStatus: (status) => status < 500, // Don't throw on 4xx errors
})

// Instance séparée pour les requêtes d'authentification avec timeout fini
// (évite loading infini si le backend ne répond pas; Render cold start ~30–60s)
const AUTH_TIMEOUT_MS = 60000 // 60 secondes
const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: AUTH_TIMEOUT_MS,
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
  const savedLanguage = localStorage.getItem(LANGUAGE_PREFERENCE_KEY)
  const supported = Object.keys(languages)
  if (savedLanguage && supported.includes(savedLanguage)) {
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

    // Retry logic pour les erreurs de timeout, réseau, ou backend unavailable (404/500)
    const isAuthRequest = config?.url?.includes('/auth/')
    const isBackendUnavailable = error.response?.status === 404 || error.response?.status === 500 || error.response?.status === 503
    const retryCount = config?._retryCount || 0
    const maxRetries = isBackendUnavailable ? 2 : 1 // More retries for backend unavailable

    if (
      config &&
      !config._retry &&
      !isAuthRequest && // Don't retry auth requests - they have their own timeout
      (error.code === 'ECONNABORTED' ||
        error.message?.includes('timeout') ||
        error.message?.includes('Network Error') ||
        !error.response ||
        isBackendUnavailable) // Retry on backend unavailable errors
    ) {
      if (retryCount < maxRetries) {
        config._retry = true
        config._retryCount = retryCount + 1

        // Longer backoff for backend unavailable (backend might be redeploying)
        const delay = isBackendUnavailable ? 2000 : 500
        logger.warn(`Request ${isBackendUnavailable ? 'backend unavailable' : 'timeout/error'}, retrying (${retryCount + 1}/${maxRetries}) after ${delay}ms...`)

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

    // For 404/500 errors, log but let components handle gracefully
    // This prevents API errors from triggering the not-found page
    if (isBackendUnavailable && retryCount >= maxRetries) {
      // Log but don't prevent the error from propagating
      // Components should handle this gracefully
      logger.error(`Backend unavailable after ${maxRetries} retries: ${config?.url}`)
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

let _currentUserPromise: Promise<LoginResponse['user']> | null = null;
let _currentUserCacheTime = 0;

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
    const now = Date.now();
    if (_currentUserPromise && now - _currentUserCacheTime < 2000) {
      return _currentUserPromise;
    }

    _currentUserCacheTime = now;
    _currentUserPromise = (async () => {
      try {
        // Shorter timeout so a dead local backend does not block the UI for 30s
        const response = await api.get('/api/v1/auth/me', { timeout: 15000 })
        // validateStatus accepts4xx; treat auth failures as errors so we do not setUser(error JSON)
        if (response.status === 401 || response.status === 403) {
          const err = new Error('Unauthorized') as AxiosError
          ;(err as any).response = response
          throw err
        }
        const data = response.data
        if (!data || typeof data !== 'object' || typeof (data as any).id !== 'number') {
          const err = new Error('Invalid user response') as AxiosError
          ;(err as any).response = response
          throw err
        }
        return data as LoginResponse['user']
      } catch (e) {
        _currentUserPromise = null
        _currentUserCacheTime = 0
        throw e
      }
    })();

    return _currentUserPromise;
  },

  // Connexion (timeout 60s, 1 retry si timeout ou 503 pour cold start Render)
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const params = new URLSearchParams()
    params.append('username', credentials.email_or_username)
    params.append('password', credentials.password)

    const doLogin = () =>
      authApi.post('/api/v1/auth/login', params.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })

    let response
    try {
      response = await doLogin()
    } catch (err) {
      const axiosErr = err as AxiosError
      const isTimeout =
        axiosErr.code === 'ECONNABORTED' ||
        (err as Error).message?.includes('timeout')
      const is503 = axiosErr.response?.status === 503
      if (isTimeout) {
        logger.warn('Login timeout, retrying once...')
        await new Promise((r) => setTimeout(r, 2000))
        response = await doLogin()
      } else if (is503) {
        logger.warn('Backend 503 (service starting), retrying once in 5s...')
        await new Promise((r) => setTimeout(r, 5000))
        response = await doLogin()
      } else {
        throw err
      }
    }

    const data = response.data
    if (data.access_token) localStorage.setItem('access_token', data.access_token)
    if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token)
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

    // Vérifier que l'inscription a réussi (validateStatus accepte les 4xx)
    if (response.status >= 400) {
      const error: any = new Error(
        response.data?.detail || response.data?.message || "Erreur lors de l'inscription"
      )
      error.response = response
      throw error
    }

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
