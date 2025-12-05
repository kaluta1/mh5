'use client'

import { useState, useRef, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import api from '@/lib/api'

interface AuthorPopoverProps {
  userId?: number
  name: string
  avatar: string
  country?: string
  city?: string
  rank?: number
  votes: number
  children: React.ReactNode
}

export function AuthorPopover({ userId, name, avatar, country, city, rank, votes, children }: AuthorPopoverProps) {
  const { t } = useLanguage()
  const [authorDetails, setAuthorDetails] = useState<any>(null)
  const [loadingAuthorDetails, setLoadingAuthorDetails] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const [position, setPosition] = useState<'top' | 'bottom'>('top')
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  // Charger les détails de l'auteur
  const loadAuthorDetails = async () => {
    if (!userId || loadingAuthorDetails || authorDetails) return
    
    try {
      setLoadingAuthorDetails(true)
      const response = await api.get(`/api/v1/users/${userId}`)
      setAuthorDetails(response.data)
    } catch (error) {
      console.error('Error loading author details:', error)
    } finally {
      setLoadingAuthorDetails(false)
    }
  }

  // Calculer l'âge à partir de la date de naissance
  const calculateAge = (dateOfBirth: string | null | undefined): number | null => {
    if (!dateOfBirth) return null
    const birthDate = new Date(dateOfBirth)
    const today = new Date()
    let age = today.getFullYear() - birthDate.getFullYear()
    const monthDiff = today.getMonth() - birthDate.getMonth()
    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
      age--
    }
    return age
  }

  const handleMouseEnter = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    setIsOpen(true)
    loadAuthorDetails()
    
    // Calculer la position du popover en fonction de l'espace disponible
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      const spaceAbove = rect.top
      const spaceBelow = window.innerHeight - rect.bottom
      const popoverHeight = 320 // Hauteur approximative du popover
      
      // Si pas assez d'espace en haut, afficher en bas
      if (spaceAbove < popoverHeight + 20 && spaceBelow > spaceAbove) {
        setPosition('bottom')
      } else {
        setPosition('top')
      }
    }
  }

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setIsOpen(false)
    }, 200) // Petit délai pour permettre de passer de l'élément au popover
  }

  // Nettoyer le timeout au démontage
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  return (
    <div 
      ref={containerRef}
      className="relative inline-block"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {children}
      
      {/* Popover */}
      {isOpen && (
        <div
          ref={popoverRef}
          className={`absolute left-0 w-80 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-4 z-50 ${
            position === 'top' ? 'bottom-full mb-2' : 'top-full mt-2'
          }`}
          onMouseEnter={() => {
            if (timeoutRef.current) {
              clearTimeout(timeoutRef.current)
            }
          }}
          onMouseLeave={handleMouseLeave}
        >
          {loadingAuthorDetails ? (
            <div className="flex items-center justify-center py-4">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-myfav-primary"></div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                {avatar && (avatar.startsWith('http') || avatar.startsWith('/')) ? (
                  <div className="w-16 h-16 rounded-full overflow-hidden bg-gray-200 dark:bg-gray-700 flex-shrink-0">
                    <img src={avatar} alt={name} className="w-full h-full object-cover" />
                  </div>
                ) : (
                  <div className="w-16 h-16 rounded-full bg-gradient-to-br from-myfav-primary to-myfav-primary-dark flex items-center justify-center text-2xl flex-shrink-0">
                    {avatar || '👤'}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-900 dark:text-white text-base">{name}</p>
                  {authorDetails?.username && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">@{authorDetails.username}</p>
                  )}
                </div>
              </div>
              
              {/* Informations détaillées */}
              <div className="space-y-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                {authorDetails?.gender && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-600 dark:text-gray-400 w-20">{t('dashboard.contests.gender') || 'Sexe'}:</span>
                    <span className="text-sm text-gray-900 dark:text-white">
                      {authorDetails.gender === 'male' ? (t('dashboard.contests.male') || 'Homme') : 
                       authorDetails.gender === 'female' ? (t('dashboard.contests.female') || 'Femme') : 
                       authorDetails.gender}
                    </span>
                  </div>
                )}
                {authorDetails?.date_of_birth && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-600 dark:text-gray-400 w-20">{t('dashboard.contests.age') || 'Âge'}:</span>
                    <span className="text-sm text-gray-900 dark:text-white">
                      {calculateAge(authorDetails.date_of_birth)} {t('dashboard.contests.years') || 'ans'}
                    </span>
                  </div>
                )}
                {authorDetails?.country && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-600 dark:text-gray-400 w-20">{t('dashboard.contests.country') || 'Pays'}:</span>
                    <span className="text-sm text-gray-900 dark:text-white">{authorDetails.country}</span>
                  </div>
                )}
                {authorDetails?.city && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-600 dark:text-gray-400 w-20">{t('dashboard.contests.city') || 'Ville'}:</span>
                    <span className="text-sm text-gray-900 dark:text-white">{authorDetails.city}</span>
                  </div>
                )}
                {authorDetails?.bio && (
                  <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">{t('dashboard.contests.bio') || 'Biographie'}:</p>
                    <p className="text-sm text-gray-900 dark:text-white">{authorDetails.bio}</p>
                  </div>
                )}
              </div>

              {/* Stats du contestant */}
              <div className="pt-2 border-t border-gray-200 dark:border-gray-700 grid grid-cols-2 gap-2">
                {rank && (
                  <div>
                    <p className="text-xs text-gray-600 dark:text-gray-400">{t('dashboard.contests.rank') || 'Classement'}</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">#{rank}</p>
                  </div>
                )}
                <div>
                  <p className="text-xs text-gray-600 dark:text-gray-400">{t('dashboard.contests.votes') || 'Votes'}</p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{votes}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

