'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Eye, EyeOff, Loader2, ArrowLeft, Heart, Mail, Lock, User, Phone, Gift, CheckCircle } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { LanguageSelector } from '@/components/ui/language-selector'
import { LocationSelectorSimple } from '@/components/auth/location-selector-simple'
import { authService } from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'

export default function RegisterPage() {
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    confirmPassword: '',
    country: '',
    city: '',
    region: '',
    continent: ''
  })
  
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [isSuccess, setIsSuccess] = useState(false)
  const [referralCode, setReferralCode] = useState<string | null>(null)

  // Vérifier si un code de parrainage est présent dans l'URL ou localStorage
  useEffect(() => {
    const refCode = searchParams.get('ref') || searchParams.get('referral')
    if (refCode) {
      setReferralCode(refCode)
      // Stocker le code de parrainage dans localStorage
      localStorage.setItem('referral_code', refCode)
    } else {
      // Vérifier si un code est déjà stocké
      const storedCode = localStorage.getItem('referral_code')
      if (storedCode) {
        setReferralCode(storedCode)
      }
    }
  }, [searchParams])

  // Rediriger si déjà connecté
  useEffect(() => {
    const accessToken = localStorage.getItem('access_token')
    if (accessToken) {
      router.push('/dashboard')
      return
    }
  }, [router])

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    if (error) setError('')
  }

  // Callbacks pour la localisation - mémorisés pour éviter la boucle infinie
  const handleCountryChange = useCallback((country: string) => {
    console.log('handleCountryChange appelé avec:', country)
    setFormData(prev => {
      const newData = { ...prev, country }
      console.log('FormData après handleCountryChange:', newData)
      return newData
    })
  }, [])

  const handleCityChange = useCallback((city: string) => {
    console.log('handleCityChange appelé avec:', city)
    setFormData(prev => {
      const newData = { ...prev, city }
      console.log('FormData après handleCityChange:', newData)
      return newData
    })
  }, [])

  const handleRegionChange = useCallback((region: string) => {
    console.log('handleRegionChange appelé avec:', region)
    setFormData(prev => {
      const newData = { ...prev, region }
      console.log('FormData après handleRegionChange:', newData)
      return newData
    })
  }, [])

  const handleContinentChange = useCallback((continent: string) => {
    console.log('handleContinentChange appelé avec:', continent)
    setFormData(prev => {
      const newData = { ...prev, continent }
      console.log('FormData après handleContinentChange:', newData)
      return newData
    })
  }, [])

  const validateForm = () => {
    console.log('Validation formData:', formData)
    
    if (!formData.email || !formData.username || !formData.password || !formData.confirmPassword) {
      setError(t('auth.register.errors.required_fields'))
      return false
    }

    if (!formData.country || !formData.city) {
      console.log('Pays manquant:', !formData.country, 'Ville manquante:', !formData.city)
      setError('Veuillez sélectionner votre pays et votre ville')
      return false
    }

    if (formData.password !== formData.confirmPassword) {
      setError(t('auth.register.errors.password_mismatch'))
      return false
    }

    if (formData.password.length < 6) {
      setError(t('auth.register.errors.password_min_length'))
      return false
    }

    if (!acceptTerms) {
      setError(t('auth.register.errors.terms_required'))
      return false
    }

    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateForm()) return

    setIsLoading(true)
    setError('')

    try {
      const userData = {
        email: formData.email,
        username: formData.username,
        password: formData.password,
        country: formData.country,
        city: formData.city,
        region: formData.region,
        continent: formData.continent,
        sponsor_code: referralCode || undefined  // Passer le code de parrainage
      }

      const response = await authService.register(userData)
      
      // Stocker les tokens si fournis
      if (response.access_token) {
        localStorage.setItem('access_token', response.access_token)
      }
      if (response.refresh_token) {
        localStorage.setItem('refresh_token', response.refresh_token)
      }

      // Supprimer le code de parrainage du localStorage après utilisation
      if (referralCode) {
        localStorage.removeItem('referral_code')
      }

      // Afficher le message de succès
      setIsSuccess(true)
      
    } catch (err: any) {
      console.error('Registration error:', err)
      setError(err.response?.data?.detail || t('auth.registerError'))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-gray-900 dark:via-blue-900/20 dark:to-purple-900/20 relative overflow-hidden">
      {/* Background decorative elements */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-blue-400/10 rounded-full blur-3xl"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-purple-400/10 rounded-full blur-3xl"></div>
      </div>

      {/* Header avec contrôles */}
      <div className="relative z-10 flex justify-between items-center p-6">
        <Link 
          href="/"
          className="inline-flex items-center text-sm font-medium text-gray-700 hover:text-myfav-primary dark:text-gray-200 dark:hover:text-myfav-blue-400 transition-colors"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {t('navigation.home')}
        </Link>
        
        <div className="flex items-center space-x-3">
          <LanguageSelector />
          <ThemeToggle />
        </div>
      </div>

      {/* Main content */}
      <div className="relative z-10 flex items-center justify-center min-h-[calc(100vh-120px)] p-2">
        <div className="w-full max-w-lg">
          {/* Logo et titre */}
          <div className="text-center mb-2">
            <h1 className="text-4xl font-bold dsm-title mb-3">
              {t('auth.register.title')}
            </h1>
            <p className="text-lg text-gray-700 dark:text-gray-200 max-w-md mx-auto">
              {t('auth.register.subtitle')}
            </p>
          </div>

          {/* Bannière code de parrainage */}
          {referralCode && (
            <div className="mb-4 p-4 bg-gradient-to-r from-myfav-primary/10 to-purple-500/10 dark:from-myfav-primary/20 dark:to-purple-500/20 rounded-xl border border-myfav-primary/20 dark:border-myfav-primary/30">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-myfav-primary/20 flex items-center justify-center">
                  <Gift className="w-5 h-5 text-myfav-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {t('auth.referral_bonus') || 'Vous avez été parrainé !'}
                  </p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">
                    {t('auth.referral_code') || 'Code'}: <span className="font-mono font-bold text-myfav-primary">{referralCode}</span>
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Formulaire ou Succès */}
          <div className="bg-white/80 dark:bg-gray-800/90 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/20 dark:border-gray-700/50 p-8">
            {isSuccess ? (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="mb-6">
                  <div className="w-20 h-20 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                    <CheckCircle className="w-12 h-12 text-green-500" />
                  </div>
                </div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                  {t('auth.register.success_title') || 'Inscription réussie !'}
                </h2>
                <p className="text-center text-gray-700 dark:text-gray-200 mb-6">
                  {t('auth.register.success_message') || 'Bienvenue ! Votre compte a été créé avec succès.'}
                </p>
                <Button
                  onClick={() => router.push('/login')}
                  className="w-full h-12 text-lg font-semibold bg-gradient-to-r from-myfav-primary to-purple-600 hover:from-myfav-primary-dark hover:to-purple-700 text-white rounded-xl shadow-lg hover:shadow-xl transition-all duration-300"
                >
                  <Heart className="mr-2 h-5 w-5" />
                  {t('auth.register.continue_button') || 'Se connecter'}
                </Button>
              </div>
            ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <div className="p-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
                  {error}
                </div>
              )}

              <div className="space-y-6">
                {/* Email */}
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    {t('auth.email')} *
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <Input
                      type="email"
                      placeholder={t('auth.register.email_placeholder')}
                      value={formData.email}
                      onChange={(e) => handleInputChange('email', e.target.value)}
                      className="pl-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-myfav-primary focus:ring-myfav-primary dsm-input"
                      required
                    />
                  </div>
                </div>

                {/* Username */}
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    {t('auth.username')} *
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <Input
                      type="text"
                      placeholder={t('auth.register.username_placeholder')}
                      value={formData.username}
                      onChange={(e) => handleInputChange('username', e.target.value)}
                      className="pl-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-myfav-primary focus:ring-myfav-primary dsm-input"
                        required
                    />
                  </div>
                </div>

                {/* Password */}
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    {t('auth.password')} *
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      placeholder={t('auth.register.password_placeholder')}
                      value={formData.password}
                      onChange={(e) => handleInputChange('password', e.target.value)}
                      className="pl-10 pr-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-myfav-primary focus:ring-myfav-primary dsm-input"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                    >
                      {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                    </button>
                  </div>
                </div>

                {/* Confirm Password */}
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    {t('auth.register.confirm_password_placeholder')} *
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <Input
                      type={showConfirmPassword ? 'text' : 'password'}
                      placeholder={t('auth.register.confirm_password_placeholder')}
                      value={formData.confirmPassword}
                      onChange={(e) => handleInputChange('confirmPassword', e.target.value)}
                      className="pl-10 pr-10 h-12 rounded-xl border-gray-200 dark:border-gray-600 focus:border-myfav-primary focus:ring-myfav-primary dsm-input"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                    >
                      {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Country & City Selection */}
              <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <LocationSelectorSimple
                  selectedCountry={formData.country}
                  selectedCity={formData.city}
                  onCountryChange={handleCountryChange}
                  onCityChange={handleCityChange}
                  onRegionChange={handleRegionChange}
                  onContinentChange={handleContinentChange}
                />
              </div>

              {/* Terms */}
              <div className="flex items-start space-x-3 p-4 bg-myfav-blue-50 dark:bg-myfav-blue-900/20 rounded-xl">
                <Checkbox
                  id="terms"
                  checked={acceptTerms}
                  onCheckedChange={setAcceptTerms}
                  className="mt-0.5"
                />
                <label
                  htmlFor="terms"
                  className="text-sm text-gray-700 dark:text-gray-200 cursor-pointer leading-relaxed"
                >
                  {t('auth.register.terms_accept')}
                </label>
              </div>

              {/* Submit Button */}
              <Button
                type="submit"
                className="w-full h-12 bg-myfav-primary hover:bg-myfav-primary-dark text-white font-semibold rounded-xl shadow-lg hover:shadow-xl transition-all duration-200"
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    {t('auth.register.loading')}
                  </>
                ) : (
                  <>
                    <Heart className="mr-2 h-5 w-5" />
                    {t('auth.register.submit')}
                  </>
                )}
              </Button>

              {/* Login Link */}
              <div className="text-center pt-4">
                <span className="text-sm text-gray-700 dark:text-gray-200">
                  {t('auth.register.have_account')}{' '}
                </span>
                <Link
                  href="/login"
                  className="text-sm font-semibold text-myfav-primary hover:text-myfav-primary-dark dark:text-myfav-blue-400 dark:hover:text-myfav-blue-300 transition-colors"
                >
                  {t('auth.register.login_link')}
                </Link>
              </div>
            </form>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
