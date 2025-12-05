"use client"

import * as React from 'react'
import { authService } from '@/lib/api'

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
}

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (credentials: { email_or_username: string; password: string }) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
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
  const [isLoading, setIsLoading] = React.useState(true)

  const isAuthenticated = !!user && authService.isAuthenticated()

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
  }

  const logout = async () => {
    await authService.logout()
    setUser(null)
  }

  const refreshUser = async () => {
    if (authService.isAuthenticated()) {
      try {
        const userData = await authService.getCurrentUser()
        setUser(userData)
      } catch (error) {
        console.error('Erreur lors du rafraîchissement de l\'utilisateur:', error)
        await logout()
      }
    }
  }

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated,
    login,
    logout,
    refreshUser
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}
