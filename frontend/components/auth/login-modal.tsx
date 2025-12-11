"use client"

import * as React from "react"
import { useState } from "react"
import { useRouter } from "next/navigation"
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
  onLoginSuccess?: (user: any) => void
  onRegisterClick?: () => void
}

export function LoginModal({ open, onOpenChange, onSwitchToRegister, onLoginSuccess, onRegisterClick }: LoginModalProps) {
  const { t } = useLanguage()
  const router = useRouter()
  const { login, isAuthenticated } = useAuth()
  const [formData, setFormData] = useState({
    emailOrUsername: "",
    password: ""
  })
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const [isSuccess, setIsSuccess] = useState(false)

  const validateForm = () => {
    if (!formData.emailOrUsername || !formData.password) {
      setError(t('auth.login.errors.required_fields'))
      return false
    }
    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateForm()) return
    
    setIsLoading(true)
    setError("")

    try {
      // Utiliser la fonction login du hook useAuth pour mettre à jour le contexte
      await login({
        email_or_username: formData.emailOrUsername,
        password: formData.password,
      })

      // Afficher la page de succès
      setIsSuccess(true)
      setFormData({ emailOrUsername: "", password: "" })
      
      // Fermer le modal et rediriger vers les contests
      setTimeout(() => {
        onOpenChange(false)
        router.push('/dashboard/contests')
      }, 1500)
    } catch (err: any) {
      console.error('Login error:', err)
      let errorMessage = t('auth.login.errors.invalid_credentials')
      
      if (err.response?.data) {
        const errorData = err.response.data
        if (typeof errorData === 'string') {
          errorMessage = errorData
        } else if (errorData.detail) {
          if (typeof errorData.detail === 'string') {
            errorMessage = errorData.detail
          } else if (Array.isArray(errorData.detail)) {
            errorMessage = errorData.detail.map(e => e.msg || e).join(', ')
          } else {
            errorMessage = t('auth.login.errors.invalid_credentials')
          }
        } else if (errorData.message) {
          errorMessage = errorData.message
        }
      } else if (err.message) {
        errorMessage = err.message
      }
      
      setError(errorMessage)
      setIsLoading(false)
    }
  }

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    if (error) setError("")
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
          <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
              {typeof error === 'string' ? error : t('common.error')}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="emailOrUsername" className="text-gray-700 dark:text-gray-200">
              {t('auth.email')} {t('common.or')} {t('auth.username')} *
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
              className="p-0 h-auto font-normal text-myfav-primary hover:text-myfav-primary-dark dark:text-myfav-blue-400"
              onClick={() => {
                // TODO: Implémenter mot de passe oublié
                console.log("Mot de passe oublié")
              }}
            >
              {t('auth.login.forgot_password')}
            </Button>
          </div>

          <Button type="submit" className="w-full bg-myfav-primary hover:bg-myfav-primary-dark text-white font-semibold" disabled={isLoading}>
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
              className="text-sm font-medium text-myfav-primary hover:text-myfav-primary-dark dark:text-myfav-blue-400 dark:hover:text-myfav-blue-300"
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
