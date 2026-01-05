'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { LocationSelectorWithCreate } from '@/components/dashboard/location-selector-with-create'
import { UploadButton } from '@/components/ui/upload-button'
import { Calendar, User, Image as ImageIcon, FileText } from 'lucide-react'

export default function ProfileSetupPage() {
  const router = useRouter()
  const { user, isAuthenticated } = useAuth()
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [firstName, setFirstName] = useState<string>('')
  const [lastName, setLastName] = useState<string>('')
  const [avatarUrl, setAvatarUrl] = useState<string>('')
  const [bio, setBio] = useState<string>('')
  const [dateOfBirth, setDateOfBirth] = useState<string>('')
  const [gender, setGender] = useState<string>('')
  
  const [continentId, setContinentId] = useState<number | null>(null)
  const [regionId, setRegionId] = useState<number | null>(null)
  const [countryId, setCountryId] = useState<number | null>(null)
  const [cityId, setCityId] = useState<number | null>(null)
  
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
    }
  }, [isAuthenticated, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validation
    if (!firstName.trim()) {
      addToast(t('profile_setup.first_name_required') || 'Le prénom est requis', 'error')
      return
    }

    if (!lastName.trim()) {
      addToast(t('profile_setup.last_name_required') || 'Le nom est requis', 'error')
      return
    }

    if (!avatarUrl) {
      addToast(t('profile_setup.avatar_required') || 'L\'avatar est requis', 'error')
      return
    }

    if (!bio.trim()) {
      addToast(t('profile_setup.bio_required') || 'La bio est requise', 'error')
      return
    }

    if (!dateOfBirth) {
      addToast(t('profile_setup.dob_required') || 'La date de naissance est requise', 'error')
      return
    }

    if (!gender) {
      addToast(t('profile_setup.gender_required') || 'Le genre est requis', 'error')
      return
    }

    if (!cityId) {
      addToast(t('profile_setup.city_required') || 'La ville est requise', 'error')
      return
    }

    try {
      setIsLoading(true)

      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      if (!token) {
        addToast(t('profile_setup.session_expired') || 'Session expirée', 'error')
        router.push('/login')
        return
      }

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/v1/users/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          avatar_url: avatarUrl,
          bio: bio,
          date_of_birth: dateOfBirth,
          gender: gender,
          city_id: cityId,
          country_id: countryId,
          region_id: regionId,
          continent_id: continentId,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || t('profile_setup.update_error') || 'Erreur lors de la mise à jour du profil')
      }

      addToast(t('profile_setup.success') || 'Profil configuré avec succès!', 'success')
      
      // Rediriger vers le contest ou le dashboard
      const contestId = typeof window !== 'undefined' ? sessionStorage.getItem('contestId') : null
      if (contestId) {
        sessionStorage.removeItem('contestId')
        router.push(`/dashboard/contests/${contestId}/apply`)
      } else {
        router.push('/dashboard')
      }
    } catch (err: any) {
      console.error('Erreur:', err)
      addToast(err.message || 'Erreur lors de la configuration du profil', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 to-gray-800 p-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            {t('common.profile_setup') || 'Configuration du Profil'}
          </h1>
          <p className="text-gray-400">
            {t('common.profile_setup_description') || 'Complétez votre profil pour pouvoir participer aux concours'}
          </p>
        </div>

        {/* Form Card */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 shadow-xl">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* First Name & Last Name */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                  {t('profile_setup.first_name') || 'Prénom'} *
                </label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder={t('profile_setup.first_name_placeholder') || 'Votre prénom'}
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                  {t('profile_setup.last_name') || 'Nom'} *
                </label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder={t('profile_setup.last_name_placeholder') || 'Votre nom'}
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
                />
              </div>
            </div>

            {/* Avatar Upload */}
            <div>
              <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <ImageIcon className="w-4 h-4" />
                {t('profile_setup.avatar') || 'Avatar'} *
              </label>
              {avatarUrl ? (
                <div className="flex items-center gap-4">
                  <img src={avatarUrl} alt="Avatar" className="w-20 h-20 rounded-lg object-cover" />
                  <button
                    type="button"
                    onClick={() => setAvatarUrl('')}
                    className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-sm"
                  >
                    Supprimer
                  </button>
                </div>
              ) : (
                <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 bg-white/50 dark:bg-gray-700/50">
                  <UploadButton
                    endpoint="profileAvatar"
                    onClientUploadComplete={(res) => {
                      if (res && res.length > 0) {
                        setAvatarUrl(res[0].url)
                      }
                    }}
                    onUploadError={(error: Error) => {
                      addToast(`${t('profile_setup.upload_error') || 'Erreur d\'upload'}: ${error.message}`, 'error')
                    }}
                  />
                </div>
              )}
            </div>

            {/* Bio */}
            <div>
              <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <FileText className="w-4 h-4" />
                {t('profile_setup.bio') || 'Bio'} *
              </label>
              <textarea
                value={bio}
                onChange={(e) => setBio(e.target.value.slice(0, 500))}
                placeholder={t('profile_setup.bio_placeholder') || 'Parlez un peu de vous...'}
                maxLength={500}
                rows={4}
                disabled={isLoading}
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary resize-none"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {bio.length}/500 {t('profile_setup.characters') || 'caractères'}
              </p>
            </div>

            {/* Location Section */}
            <div>
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <User className="w-5 h-5" />
                {t('profile_setup.location') || 'Localisation'} *
              </h2>
              <LocationSelectorWithCreate
                onContinentSelected={(id) => setContinentId(id)}
                onRegionSelected={(id) => setRegionId(id)}
                onCountrySelected={(id) => setCountryId(id)}
                onCitySelected={(id) => setCityId(id)}
                isLoading={isLoading}
              />
            </div>

            {/* Gender Section */}
            <div>
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <User className="w-5 h-5" />
                {t('profile_setup.gender') || 'Genre'}
              </h2>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { value: 'male', label: t('profile_setup.male') || 'Homme' },
                  { value: 'female', label: t('profile_setup.female') || 'Femme' },
                  { value: 'other', label: t('profile_setup.other') || 'Autre' },
                  { value: 'prefer_not_to_say', label: t('profile_setup.prefer_not_to_say') || 'Préfère ne pas dire' },
                ].map((option) => (
                  <label
                    key={option.value}
                    className={`flex items-center gap-3 p-3 rounded-lg border-2 cursor-pointer transition ${
                      gender === option.value
                        ? 'border-myhigh5-primary bg-myhigh5-primary/10'
                        : 'border-gray-600 bg-gray-700/50 hover:border-gray-500'
                    }`}
                  >
                    <input
                      type="radio"
                      name="gender"
                      value={option.value}
                      checked={gender === option.value}
                      onChange={(e) => setGender(e.target.value)}
                      disabled={isLoading}
                      className="w-4 h-4"
                    />
                    <span className="text-white font-medium">{option.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Date of Birth Section */}
            <div>
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Calendar className="w-5 h-5" />
                {t('profile_setup.date_of_birth') || 'Date de Naissance'}
              </h2>
              <input
                type="date"
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
                disabled={isLoading}
                className="w-full px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myhigh5-primary"
              />
            </div>

            {/* Submit Buttons */}
            <div className="flex gap-3 pt-6">
              <Button
                type="button"
                onClick={() => router.back()}
                variant="outline"
                disabled={isLoading}
                className="flex-1"
              >
                {t('common.cancel') || 'Annuler'}
              </Button>
              <Button
                type="submit"
                disabled={isLoading || !cityId || !gender || !dateOfBirth}
                className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white font-bold"
              >
                {isLoading ? t('common.submitting') || 'Soumission...' : t('profile_setup.continue') || 'Continuer'}
              </Button>
            </div>
          </form>
        </div>

        {/* Info Box */}
        <div className="mt-8 bg-blue-900/20 border border-blue-800 rounded-lg p-4">
          <p className="text-blue-200 text-sm">
            ℹ️ {t('profile_setup.info') || 'Ces informations sont requises pour participer aux concours. Vous pourrez les modifier ultérieurement dans vos paramètres de profil.'}
          </p>
        </div>
      </div>
    </div>
  )
}
