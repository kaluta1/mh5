"use client"

import * as React from 'react'
import { AxiosError } from 'axios'
import { authService } from '@/lib/api'
import { cacheService } from '@/lib/cache-service'
import { logger } from '@/lib/logger'
import type { User, UserRole } from '@/types/user'

// Re-export types for backward compatibility
export type { User, UserRole }

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  permissions: string[]
  login: (credentials: { email_or_username: string; password: string }) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  hasPermission: (permission: string) => boolean
  hasAnyPermission: (...permissions: string[]) => boolean
  hasAllPermissions: (...permissions: string[]) => boolean
  isAdmin: boolean
  isModerator: boolean
}

const AuthContext = React.createContext<AuthContextType | undefined>(undefined)

export function useAuth() {
  const context = React.useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null)
  const [permissions, setPermissions] = React.useState<string[]>([])
  const [isLoading, setIsLoading] = React.useState(true)

  const isAuthenticated = !!user && authService.isAuthenticated()

  // Helper pour vérifier les rôles
  const isAdmin = user?.role?.name === 'admin' || user?.is_admin || false
  const isModerator = user?.role?.name === 'moderator' || isAdmin

  // Fonction pour charger les permissions (avec timeout)
  const loadPermissions = async () => {
    try {
      const token = localStorage.getItem('access_token')
      if (!token) return

      // Use window-level cache for React Strict Mode duplicate mounts
      const now = Date.now()
      if (typeof window !== 'undefined') {
        const win = window as any
        if (win._permissionsPromise && now - (win._permissionsCacheTime || 0) < 2000) {
          const perms = await win._permissionsPromise
          setPermissions(Array.isArray(perms) ? perms : [])
          return
        }
      }

      const baseUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '')

      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000)

      const fetchPromise = fetch(`${baseUrl}/api/v1/rbac/me/permissions`, {
        headers: { 'Authorization': `Bearer ${token}` },
        signal: controller.signal
      }).then(async (response) => {
        clearTimeout(timeoutId)
        if (response.ok) {
          return await response.json()
        } else if (response.status === 404 || response.status === 403) {
          return []
        }
        throw new Error('Failed to fetch permissions')
      })

      if (typeof window !== 'undefined') {
        const win = window as any
        win._permissionsPromise = fetchPromise
        win._permissionsCacheTime = now
      }

      const perms = await fetchPromise
      setPermissions(Array.isArray(perms) ? perms : [])

    } catch (error) {
      // Silently fail - permissions are not critical for initial load
      if (error instanceof Error && error.name !== 'AbortError') {
        logger.debug('Permissions load skipped (endpoint may not exist)', error)
      }
    }
  }

  // Vérifier l'authentification au chargement (optimized for speed)
  React.useEffect(() => {
    const checkAuth = async (retryCount = 0) => {
      try {
        // Check cache first for instant display
        const cachedUser = cacheService.get('user')
        if (cachedUser && typeof cachedUser === 'object') {
          setUser(cachedUser as User)
          setIsLoading(false) // Show page immediately with cached user
          // Load fresh data in background
          if (authService.isAuthenticated()) {
            authService.getCurrentUser()
              .then(userData => {
                setUser({
                  ...userData,
                  is_admin: (userData as any).is_admin || false,
                  is_active: userData.is_active ?? true,
                  is_verified: userData.is_verified ?? false
                } as User)
                cacheService.set('user', userData, 300000) // Cache for 5 minutes
                loadPermissions().catch(() => { })
              })
              .catch(() => { }) // Silent fail - use cached data
          }
          return
        }

        if (authService.isAuthenticated()) {
          const userData = await authService.getCurrentUser()
          setUser({
            ...userData,
            is_admin: (userData as any).is_admin || false,
            is_active: userData.is_active ?? true,
            is_verified: userData.is_verified ?? false
          } as User)
          cacheService.set('user', userData, 300000) // Cache for 5 minutes
          loadPermissions().catch(() => { })
        } else {
          setIsLoading(false)
        }
      } catch (error) {
        const axiosErr = error as AxiosError
        const status = axiosErr.response?.status
        const isNetworkOrServerError = !axiosErr.response || (status && status >= 500)
        const isRetryable = isNetworkOrServerError || axiosErr.code === 'ECONNABORTED' || axiosErr.message === 'Network Error'

        if (status === 401) {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          logger.debug('Session expirée ou token invalide')
        } else if (isRetryable && retryCount < 1) {
          logger.warn('Backend indisponible, nouvel essai dans 3s...')
          await new Promise((r) => setTimeout(r, 3000))
          return checkAuth(retryCount + 1)
        } else if (isRetryable) {
          logger.warn('Backend temporairement indisponible')
        } else {
          logger.error('Erreur lors de la vérification de l\'authentification', error)
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
        }
      } finally {
        setIsLoading(false)
      }
    }

    checkAuth()
  }, [])

  const login = async (credentials: { email_or_username: string; password: string }) => {
    // Login et récupérer les tokens
    await authService.login(credentials)

    // Récupérer les données utilisateur après connexion
    const userData = await authService.getCurrentUser()
    setUser({
      ...userData,
      is_admin: (userData as any).is_admin || false,
      is_active: userData.is_active ?? true,
      is_verified: userData.is_verified ?? false
    } as User)

    // Charger les permissions
    await loadPermissions()
  }

  const logout = async () => {
    await authService.logout()
    setUser(null)
    setPermissions([])
    // Invalider tout le cache lors de la déconnexion
    cacheService.clear()
  }

  const refreshUser = async () => {
    if (authService.isAuthenticated()) {
      try {
        const userData = await authService.getCurrentUser()
        setUser({
          ...userData,
          is_admin: (userData as any).is_admin || false,
          is_active: userData.is_active ?? true,
          is_verified: userData.is_verified ?? false
        } as User)
        await loadPermissions()
      } catch (error) {
        const status = (error as AxiosError).response?.status
        if (status === 401) {
          await logout()
        } else {
          logger.warn('Rafraîchissement utilisateur impossible (backend indisponible?)', error)
        }
      }
    }
  }

  // Fonctions de vérification des permissions
  const hasPermission = (permission: string): boolean => {
    if (permissions.includes('all')) return true // Admin avec toutes les permissions
    return permissions.includes(permission)
  }

  const hasAnyPermission = (...perms: string[]): boolean => {
    if (permissions.includes('all')) return true
    return perms.some(p => permissions.includes(p))
  }

  const hasAllPermissions = (...perms: string[]): boolean => {
    if (permissions.includes('all')) return true
    return perms.every(p => permissions.includes(p))
  }

  const value: AuthContextType = React.useMemo(() => ({
    user,
    isLoading,
    isAuthenticated,
    permissions,
    login,
    logout,
    refreshUser,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    isAdmin,
    isModerator
  }), [user, isLoading, isAuthenticated, permissions, isAdmin, isModerator])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}
