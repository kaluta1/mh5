'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { SettingsSkeleton } from '@/components/ui/skeleton'
import { SettingsProfileTab } from '@/components/dashboard/settings-profile-tab'
import { SettingsLocationTab } from '@/components/dashboard/settings-location-tab'
import { SettingsDemographicsTab } from '@/components/dashboard/settings-demographics-tab'
import { User, MapPin, Users } from 'lucide-react'

type Tab = 'profile' | 'location' | 'demographics'

export default function SettingsPage() {
  const router = useRouter()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [currentTab, setCurrentTab] = useState<Tab>('profile')
  const [pageLoading, setPageLoading] = useState(true)

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

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    {
      id: 'profile',
      label: t('settings.profile') || 'Profil',
      icon: <User className="w-5 h-5" />,
    },
    {
      id: 'location',
      label: t('settings.location') || 'Localisation',
      icon: <MapPin className="w-5 h-5" />,
    },
    {
      id: 'demographics',
      label: t('settings.demographics') || 'Informations Personnelles',
      icon: <Users className="w-5 h-5" />,
    },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 to-gray-800 p-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">
            {t('settings.title') || 'Paramètres'}
          </h1>
          <p className="text-gray-400">
            {t('settings.description') || 'Gérez vos informations personnelles et vos préférences'}
          </p>
        </div>

        {/* Tabs Navigation */}
        <div className="flex gap-2 mb-8 border-b border-gray-700">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setCurrentTab(tab.id)}
              className={`flex items-center gap-2 px-6 py-4 font-medium transition-all border-b-2 ${
                currentTab === tab.id
                  ? 'border-myfav-primary text-myfav-primary'
                  : 'border-transparent text-gray-400 hover:text-white'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 shadow-xl">
          {currentTab === 'profile' && <SettingsProfileTab user={user} />}
          {currentTab === 'location' && <SettingsLocationTab user={user} />}
          {currentTab === 'demographics' && <SettingsDemographicsTab user={user} />}
        </div>
      </div>
    </div>
  )
}
