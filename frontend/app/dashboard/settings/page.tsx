'use client'

import { useState, useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { SettingsSkeleton } from '@/components/ui/skeleton'
import { SettingsProfileTab } from '@/components/dashboard/settings-profile-tab'
import { SettingsLocationTab } from '@/components/dashboard/settings-location-tab'
import { SettingsDemographicsTab } from '@/components/dashboard/settings-demographics-tab'
import { 
  User, 
  MapPin, 
  Users, 
  Shield, 
  CheckCircle2, 
  AlertCircle,
  Mail,
  Calendar,
  Clock,
  Share2,
  Camera
} from 'lucide-react'

type Tab = 'profile' | 'location' | 'demographics'

// Calcul du pourcentage de complétion du profil
function calculateProfileCompletion(user: any): { percentage: number; missing: string[] } {
  if (!user) return { percentage: 0, missing: [] }
  
  const fields = [
    { key: 'first_name', label: 'Prénom' },
    { key: 'last_name', label: 'Nom' },
    { key: 'avatar_url', label: 'Photo de profil' },
    { key: 'bio', label: 'Biographie' },
    { key: 'gender', label: 'Genre' },
    { key: 'date_of_birth', label: 'Date de naissance' },
    { key: 'country', label: 'Pays' },
    { key: 'city', label: 'Ville' },
  ]
  
  const missing: string[] = []
  let completed = 0
  
  fields.forEach(field => {
    if (user[field.key]) {
      completed++
    } else {
      missing.push(field.label)
    }
  })
  
  return {
    percentage: Math.round((completed / fields.length) * 100),
    missing
  }
}

// Calcul de l'âge
function calculateAge(dateOfBirth: string): number | null {
  if (!dateOfBirth) return null
  const today = new Date()
  const birthDate = new Date(dateOfBirth)
  let age = today.getFullYear() - birthDate.getFullYear()
  const m = today.getMonth() - birthDate.getMonth()
  if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
    age--
  }
  return age
}

// Formatage de la date
function formatDate(dateString: string | null): string {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  })
}

// Formatage du genre
function formatGender(gender: string | null, t: any): string {
  if (!gender) return '-'
  const genderMap: Record<string, string> = {
    'male': t('profile_setup.male') || 'Homme',
    'female': t('profile_setup.female') || 'Femme',
    'other': t('profile_setup.other') || 'Autre',
    'prefer_not_to_say': t('profile_setup.prefer_not_to_say') || 'Non spécifié'
  }
  return genderMap[gender] || gender
}

export default function SettingsPage() {
  const router = useRouter()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [currentTab, setCurrentTab] = useState<Tab>('profile')
  const [pageLoading, setPageLoading] = useState(true)

  const profileCompletion = useMemo(() => calculateProfileCompletion(user), [user])
  const userAge = useMemo(() => user?.date_of_birth ? calculateAge(user.date_of_birth) : null, [user?.date_of_birth])

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login')
    } else if (!isLoading) {
      setPageLoading(false)
    }
  }, [isAuthenticated, isLoading, router])

  if (pageLoading) {
    return <SettingsSkeleton />
  }

  const tabs: { id: Tab; label: string; icon: React.ReactNode; description: string }[] = [
    {
      id: 'profile',
      label: t('settings.profile') || 'Profil',
      icon: <User className="w-5 h-5" />,
      description: 'Photo, nom et bio'
    },
    {
      id: 'location',
      label: t('settings.location') || 'Localisation',
      icon: <MapPin className="w-5 h-5" />,
      description: 'Pays et ville'
    },
    {
      id: 'demographics',
      label: t('settings.demographics') || 'Identité',
      icon: <Users className="w-5 h-5" />,
      description: 'Genre et âge'
    },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        
        {/* Profile Header Card */}
        <div className="bg-gradient-to-r from-gray-800/80 to-gray-800/40 backdrop-blur-sm rounded-2xl border border-gray-700/50 p-6 mb-6 shadow-xl">
          <div className="flex flex-col md:flex-row gap-6">
            
            {/* Avatar Section */}
            <div className="flex-shrink-0">
              <div className="relative group">
                {user?.avatar_url ? (
                  <img 
                    src={user.avatar_url} 
                    alt="Avatar" 
                    className="w-28 h-28 rounded-2xl object-cover border-4 border-myfav-primary/30 shadow-lg"
                  />
                ) : (
                  <div className="w-28 h-28 rounded-2xl bg-gradient-to-br from-myfav-primary/20 to-myfav-primary/5 border-4 border-dashed border-gray-600 flex items-center justify-center">
                    <Camera className="w-10 h-10 text-gray-500" />
                  </div>
                )}
                {/* Verification Badge */}
                {user?.identity_verified && (
                  <div className="absolute -bottom-2 -right-2 bg-green-500 rounded-full p-1.5 border-2 border-gray-800">
                    <CheckCircle2 className="w-4 h-4 text-white" />
                  </div>
                )}
              </div>
            </div>

            {/* User Info */}
            <div className="flex-grow">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                <div>
                  <h1 className="text-2xl md:text-3xl font-bold text-white mb-1">
                    {user?.first_name && user?.last_name 
                      ? `${user.first_name} ${user.last_name}` 
                      : user?.username || user?.email?.split('@')[0] || 'Utilisateur'}
                  </h1>
                  {user?.username && (
                    <p className="text-myfav-primary font-medium">@{user.username}</p>
                  )}
                  {user?.bio && (
                    <p className="text-gray-400 mt-2 text-sm line-clamp-2 max-w-lg">{user.bio}</p>
                  )}
                </div>

                {/* Status Badges */}
                <div className="flex flex-wrap gap-2">
                  {user?.is_admin && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                      <Shield className="w-3.5 h-3.5" />
                      Admin
                    </span>
                  )}
                  {user?.identity_verified ? (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-green-500/20 text-green-300 border border-green-500/30">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Vérifié
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      <AlertCircle className="w-3.5 h-3.5" />
                      Non vérifié
                    </span>
                  )}
                </div>
              </div>

              {/* Quick Info Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
                <div className="flex items-center gap-2 text-sm">
                  <Mail className="w-4 h-4 text-gray-500" />
                  <span className="text-gray-400 truncate">{user?.email || '-'}</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <MapPin className="w-4 h-4 text-gray-500" />
                  <span className="text-gray-400">
                    {user?.city && user?.country ? `${user.city}, ${user.country}` : '-'}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Calendar className="w-4 h-4 text-gray-500" />
                  <span className="text-gray-400">
                    {userAge ? `${userAge} ans` : '-'}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Clock className="w-4 h-4 text-gray-500" />
                  <span className="text-gray-400">
                    {user?.last_login ? formatDate(user.last_login) : '-'}
                  </span>
                </div>
              </div>
            </div>

            {/* Profile Completion */}
            <div className="flex-shrink-0 md:w-48">
              <div className="bg-gray-700/50 rounded-xl p-4 border border-gray-600/50">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-400">Profil complété</span>
                  <span className={`text-lg font-bold ${
                    profileCompletion.percentage === 100 ? 'text-green-400' : 
                    profileCompletion.percentage >= 70 ? 'text-yellow-400' : 'text-red-400'
                  }`}>
                    {profileCompletion.percentage}%
                  </span>
                </div>
                <div className="h-2 bg-gray-600 rounded-full overflow-hidden">
                  <div 
                    className={`h-full rounded-full transition-all duration-500 ${
                      profileCompletion.percentage === 100 ? 'bg-green-500' : 
                      profileCompletion.percentage >= 70 ? 'bg-yellow-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${profileCompletion.percentage}%` }}
                  />
                </div>
                {profileCompletion.missing.length > 0 && (
                  <p className="text-xs text-gray-500 mt-2">
                    Manque: {profileCompletion.missing.slice(0, 2).join(', ')}
                    {profileCompletion.missing.length > 2 && ` +${profileCompletion.missing.length - 2}`}
                  </p>
                )}
              </div>

              {/* Referral Code */}
              {user?.personal_referral_code && (
                <div className="mt-3 bg-myfav-primary/10 rounded-xl p-3 border border-myfav-primary/30">
                  <div className="flex items-center gap-2 mb-1">
                    <Share2 className="w-4 h-4 text-myfav-primary" />
                    <span className="text-xs text-gray-400">Code parrainage</span>
                  </div>
                  <p className="text-myfav-primary font-mono font-bold text-sm">
                    {user.personal_referral_code}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          
          {/* Sidebar Navigation */}
          <div className="lg:col-span-1">
            <div className="bg-gray-800/50 backdrop-blur-sm rounded-xl border border-gray-700/50 p-2 sticky top-4">
              <nav className="space-y-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setCurrentTab(tab.id)}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all ${
                      currentTab === tab.id
                        ? 'bg-myfav-primary text-white shadow-lg shadow-myfav-primary/25'
                        : 'text-gray-400 hover:bg-gray-700/50 hover:text-white'
                    }`}
                  >
                    <div className={`p-2 rounded-lg ${
                      currentTab === tab.id ? 'bg-white/20' : 'bg-gray-700'
                    }`}>
                      {tab.icon}
                    </div>
                    <div>
                      <p className="font-medium">{tab.label}</p>
                      <p className={`text-xs ${
                        currentTab === tab.id ? 'text-white/70' : 'text-gray-500'
                      }`}>
                        {tab.description}
                      </p>
                    </div>
                  </button>
                ))}
              </nav>
            </div>
          </div>

          {/* Tab Content */}
          <div className="lg:col-span-3">
            <div className="bg-gray-800/50 backdrop-blur-sm rounded-xl border border-gray-700/50 p-6 shadow-xl">
              {/* Tab Header */}
              <div className="mb-6 pb-4 border-b border-gray-700">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  {tabs.find(t => t.id === currentTab)?.icon}
                  {tabs.find(t => t.id === currentTab)?.label}
                </h2>
                <p className="text-gray-400 text-sm mt-1">
                  {currentTab === 'profile' && (t('settings.profile_description') || 'Modifiez votre photo, nom et biographie')}
                  {currentTab === 'location' && (t('settings.location_description') || 'Définissez votre localisation géographique')}
                  {currentTab === 'demographics' && (t('settings.demographics_description') || 'Renseignez vos informations personnelles')}
                </p>
              </div>

              {/* Tab Content */}
              {currentTab === 'profile' && <SettingsProfileTab user={user} />}
              {currentTab === 'location' && <SettingsLocationTab user={user} />}
              {currentTab === 'demographics' && <SettingsDemographicsTab user={user} />}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
