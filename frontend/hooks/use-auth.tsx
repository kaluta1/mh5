"use client"

import * as React from 'react'
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
      
      // Use AbortController for timeout
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000) // 5 second timeout
      
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/rbac/me/permissions`, {
        headers: { 'Authorization': `Bearer ${token}` },
        signal: controller.signal
      })
      
      clearTimeout(timeoutId)
      
      if (response.ok) {
        const perms = await response.json()
        setPermissions(perms)
      }
    } catch (error) {
      // Silently fail - permissions are not critical for initial load
      if (error instanceof Error && error.name !== 'AbortError') {
        logger.error('Erreur lors du chargement des permissions', error)
      }
    }
  }

  // Vérifier l'authentification au chargement (optimized)
  React.useEffect(() => {
    const checkAuth = async () => {
      try {
        if (authService.isAuthenticated()) {
          // Load user first (critical)
          const userData = await authService.getCurrentUser()
          setUser({
            ...userData,
            is_admin: (userData as any).is_admin || false,
            is_active: userData.is_active ?? true,
            is_verified: userData.is_verified ?? false
          } as User)
          
          // Load permissions in background (non-blocking)
          loadPermissions().catch(() => {
            // Silently fail - permissions can load later
          })
        } else {
          setIsLoading(false)
        }
      } catch (error) {
        logger.error('Erreur lors de la vérification de l\'authentification', error)
        // Token invalide, nettoyer le localStorage
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
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
        logger.error('Erreur lors du rafraîchissement de l\'utilisateur', error)
        await logout()
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

  const value: AuthContextType = {
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
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}
