"use client"

import * as React from 'react'
import { authService } from '@/lib/api'
import { cacheService } from '@/lib/cache-service'

export interface UserRole {
  id: number
  name: string
  description?: string
}

export interface User {
  id: number
  email: string
  username?: string
  full_name?: string
  first_name?: string
  last_name?: string
  avatar_url?: string
  bio?: string
  
  // Demographics
  gender?: 'male' | 'female' | 'other' | 'prefer_not_to_say'
  date_of_birth?: string
  phone_number?: string
  
  // Location
  continent?: string
  region?: string
  country?: string
  city?: string
  
  // Verification & Status
  is_active: boolean
  is_verified: boolean
  is_admin: boolean
  identity_verified?: boolean
  verification_date?: string
  status?: 'active' | 'suspended' | 'banned' | 'pending_verification'
  last_login?: string
  
  // Referral
  personal_referral_code?: string
  sponsor_id?: number
  
  // RBAC
  role_id?: number
  role?: UserRole
}

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

  // Fonction pour charger les permissions
  const loadPermissions = async () => {
    try {
      const token = localStorage.getItem('access_token')
      if (!token) return
      
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/rbac/me/permissions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      
      if (response.ok) {
        const perms = await response.json()
        setPermissions(perms)
      }
    } catch (error) {
      console.error('Erreur lors du chargement des permissions:', error)
    }
  }

  // Vérifier l'authentification au chargement
  React.useEffect(() => {
    const checkAuth = async () => {
      try {
        if (authService.isAuthenticated()) {
          const userData = await authService.getCurrentUser()
          setUser({
            ...userData,
            is_admin: (userData as any).is_admin || false
          })
          // Charger les permissions après avoir récupéré l'utilisateur
          await loadPermissions()
        }
      } catch (error) {
        console.error('Erreur lors de la vérification de l\'authentification:', error)
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
      is_admin: userData.is_admin || false
    })
    
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
        setUser(userData)
        await loadPermissions()
      } catch (error) {
        console.error('Erreur lors du rafraîchissement de l\'utilisateur:', error)
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
