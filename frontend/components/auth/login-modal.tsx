"use client"

import * as React from "react"
import { AxiosError } from "axios"
import { logger } from "@/lib/logger"
import type { User } from "@/types/user"
import { useState, useEffect } from "react"
import { useRouter, usePathname } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Eye, EyeOff, Loader2, Mail, Lock } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"
import { useAuth } from "@/hooks/use-auth"
import { SuccessPage } from "./success-page"

interface LoginModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSwitchToRegister?: () => void
  onLoginSuccess?: (user: User) => void
  onRegisterClick?: () => void
}

export function LoginModal({ open, onOpenChange, onSwitchToRegister, onLoginSuccess, onRegisterClick }: LoginModalProps) {
  const { t } = useLanguage()
  const router = useRouter()
  const pathname = usePathname()
  const { login, isAuthenticated } = useAuth()
  const [formData, setFormData] = useState({
    emailOrUsername: "",
    password: ""
  })
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sauvegarder l'URL actuelle quand le modal s'ouvre
  useEffect(() => {
    if (open && pathname && pathname !== '/login' && pathname !== '/') {
      localStorage.setItem('returnUrl', pathname)
    }
  }, [open, pathname])

  const validateForm = () => {
    if (!formData.emailOrUsername.trim() || !formData.password.trim()) {
      setError(t('auth.login.errors.required_fields') || t('auth.login.errors.invalid_credentials'))
      return false
    }
    setError(null)
    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    if (!validateForm()) return false
    
    if (isLoading) return false
    
    setIsLoading(true)
    setError(null)

    try {
      // Utiliser la fonction login du hook useAuth pour mettre à jour le contexte
      await login({
        email_or_username: formData.emailOrUsername.trim(),
        password: formData.password,
      })

      // Afficher la page de succès
      setIsSuccess(true)
      setFormData({ emailOrUsername: "", password: "" })
      setError(null)
      
      // Fermer le modal et rediriger vers l'URL sauvegardée ou par défaut
      setTimeout(() => {
        onOpenChange(false)
        
        // Vérifier s'il y a une URL de retour sauvegardée
        const returnUrl = localStorage.getItem('returnUrl')
        if (returnUrl && returnUrl !== '/login' && returnUrl !== '/') {
          localStorage.removeItem('returnUrl')
          router.push(returnUrl)
        } else {
          router.push('/dashboard/contests')
        }
      }, 1500)
    } catch (err: unknown) {
      logger.error('Login error', err)
      
      // Fonction pour mapper les erreurs backend aux traductions
      const mapErrorToTranslation = (message: string): string => {
        const lowerMessage = message.toLowerCase()
        
        // Détecter les erreurs d'identifiants invalides dans différentes langues
        if (lowerMessage.includes('incorrect') || 
            lowerMessage.includes('invalid') || 
            lowerMessage.includes('invalide') ||
            lowerMessage.includes('inválido') ||
            lowerMessage.includes('ungültig') ||
            lowerMessage.includes('email') && (lowerMessage.includes('password') || lowerMessage.includes('mot de passe') || lowerMessage.includes('contraseña') || lowerMessage.includes('passwort')) ||
            lowerMessage.includes('username') && (lowerMessage.includes('password') || lowerMessage.includes('mot de passe') || lowerMessage.includes('contraseña') || lowerMessage.includes('passwort')) ||
            lowerMessage.includes('nom d\'utilisateur') && (lowerMessage.includes('mot de passe')) ||
            lowerMessage.includes('nombre de usuario') && (lowerMessage.includes('contraseña')) ||
            lowerMessage.includes('benutzername') && (lowerMessage.includes('passwort'))) {
          return t('auth.login.errors.invalid_credentials')
        }
        
        return message
      }
      
      let errorMessage = t('auth.login.errors.invalid_credentials')
      
      // Gérer les erreurs de timeout spécifiquement
      const axiosError = err as AxiosError
      if (axiosError.code === 'ECONNABORTED' || 
          axiosError.message?.includes('timeout') || 
          (err instanceof Error && err.message?.includes('timeout'))) {
        errorMessage = t('auth.login.errors.timeout')
      } else if (axiosError.response?.data) {
        const errorData = axiosError.response.data as { detail?: string | { msg: string }[] | string; message?: string } | string
        if (typeof errorData === 'string') {
          errorMessage = mapErrorToTranslation(errorData)
        } else if (errorData && typeof errorData === 'object' && 'detail' in errorData) {
          if (typeof errorData.detail === 'string') {
            errorMessage = mapErrorToTranslation(errorData.detail)
          } else if (Array.isArray(errorData.detail)) {
            const messages = errorData.detail.map(e => (typeof e === 'object' && 'msg' in e ? e.msg : String(e))).join(', ')
            errorMessage = mapErrorToTranslation(messages)
          } else {
            errorMessage = t('auth.login.errors.invalid_credentials')
          }
        } else if (errorData && typeof errorData === 'object' && 'message' in errorData && errorData.message) {
          errorMessage = mapErrorToTranslation(errorData.message)
        }
      } else if (axiosError.message) {
        errorMessage = mapErrorToTranslation(axiosError.message)
      } else if (!axiosError.response && axiosError.request) {
        // Pas de réponse du serveur (réseau ou serveur down)
        errorMessage = t('auth.login.errors.network_error')
      }
      
      // Afficher l'erreur en haut du formulaire
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
    
    return false
  }

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    // Effacer l'erreur quand l'utilisateur commence à taper
    if (error) {
      setError(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md dsm-bg-light">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-center dsm-title">
            {t('auth.login.title')}
          </DialogTitle>
          <DialogDescription className="text-center dsm-text-gray">
            {t('auth.login.subtitle')}
          </DialogDescription>
        </DialogHeader>

        {isSuccess ? (
          <SuccessPage />
        ) : (
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
          {error && (
            <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="emailOrUsername" className="text-gray-700 dark:text-gray-200">
              {t('auth.email')}
            </Label>
            <div className="relative">
              <Mail className="absolute left-3 top-3 h-4 w-4 text-gray-400 dark:text-gray-500" />
              <Input
                id="emailOrUsername"
                type="text"
                placeholder={t('auth.login.email_placeholder')}
                value={formData.emailOrUsername}
                onChange={(e) => handleInputChange("emailOrUsername", e.target.value)}
                className="pl-10 dsm-input"
                required
                disabled={isLoading}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="password" className="text-gray-700 dark:text-gray-200">
              {t('auth.password')}
            </Label>
            <div className="relative">
              <Lock className="absolute left-3 top-3 h-4 w-4 text-gray-400 dark:text-gray-500" />
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder={t('auth.login.password_placeholder')}
                value={formData.password}
                onChange={(e) => handleInputChange("password", e.target.value)}
                className="pl-10 pr-10 dsm-input"
                required
                disabled={isLoading}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent text-gray-500 dark:text-gray-400"
                onClick={() => setShowPassword(!showPassword)}
                disabled={isLoading}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>

          <div className="flex items-center justify-between text-sm">
            <Button
              type="button"
              variant="link"
              className="p-0 h-auto font-normal text-myhigh5-primary hover:text-myhigh5-primary-dark dark:text-myhigh5-blue-400"
              onClick={() => {
                onOpenChange(false)
                router.push('/forgot-password')
              }}
            >
              {t('auth.login.forgot_password')}
            </Button>
          </div>

          <Button 
            type="button" 
            className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white font-semibold" 
            disabled={isLoading}
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              handleSubmit(e as any)
            }}
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('auth.login.loading')}
              </>
            ) : (
              t('auth.login.submit')
            )}
          </Button>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <Separator className="w-full" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-2 text-muted-foreground">
                {t('common.or') || 'Or'}
              </span>
            </div>
          </div>

          <div className="text-center">
            <span className="text-sm text-gray-700 dark:text-gray-200">
              {t('auth.login.no_account')}{' '}
            </span>
            <button
              type="button"
              onClick={() => {
                onOpenChange(false)
                if (onSwitchToRegister) {
                  onSwitchToRegister()
                }
              }}
              className="text-sm font-medium text-myhigh5-primary hover:text-myhigh5-primary-dark dark:text-myhigh5-blue-400 dark:hover:text-myhigh5-blue-300"
            >
              {t('auth.login.register_link')}
            </button>
          </div>
        </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
