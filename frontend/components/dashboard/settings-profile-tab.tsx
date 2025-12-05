'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { UploadButton } from '@/components/ui/upload-button'
import { User, FileText, Image as ImageIcon } from 'lucide-react'

interface SettingsProfileTabProps {
  user: any
}

export function SettingsProfileTab({ user }: SettingsProfileTabProps) {
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [avatarUrl, setAvatarUrl] = useState('')
  const [bio, setBio] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  // Charger les données de l'utilisateur au montage
  useEffect(() => {
    if (user) {
      setFirstName(user.first_name || '')
      setLastName(user.last_name || '')
      setAvatarUrl(user.avatar_url || '')
      setBio(user.bio || '')
    }
  }, [user])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

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

    try {
      setIsLoading(true)

      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      if (!token) {
        addToast(t('profile_setup.session_expired') || 'Session expirée', 'error')
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
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || t('profile_setup.update_error') || 'Erreur lors de la mise à jour')
      }

      addToast(t('profile_setup.success') || 'Profil mis à jour avec succès!', 'success')
    } catch (err: any) {
      console.error('Erreur:', err)
      addToast(err.message || 'Erreur lors de la mise à jour du profil', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Avatar Upload - En haut */}
      <div>
        <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center justify-center gap-2">
          <ImageIcon className="w-4 h-4" />
          {t('profile_setup.avatar') || 'Avatar'} *
        </label>
        <div className="flex justify-center mb-8">
          {avatarUrl ? (
            <div className="flex flex-col items-center gap-4">
              <img src={avatarUrl} alt="Avatar" className="w-32 h-32 rounded-full object-cover border-4 border-myfav-primary" />
              <button
                type="button"
                onClick={() => setAvatarUrl('')}
                className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-sm"
              >
                {t('settings.remove') || 'Supprimer'}
              </button>
            </div>
          ) : (
            <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 bg-white/50 dark:bg-gray-700/50 w-full max-w-xs">
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
      </div>

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
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
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
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
          />
        </div>
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
          className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary resize-none"
        />
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {bio.length}/500 {t('profile_setup.characters') || 'caractères'}
        </p>
      </div>

      {/* Submit Button */}
      <div className="flex justify-end gap-3 pt-6 border-t border-gray-700">
        <Button
          type="submit"
          disabled={isLoading || !firstName.trim() || !lastName.trim() || !avatarUrl || !bio.trim()}
          className="bg-myfav-primary hover:bg-myfav-primary-dark text-white font-bold"
        >
          {isLoading ? t('common.submitting') || 'Soumission...' : t('settings.save') || 'Enregistrer'}
        </Button>
      </div>
    </form>
  )
}
