'use client'

import Image from 'next/image'
import { Heart, Users, Clock, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { Badge } from '@/components/ui/badge'
import { useState, useEffect } from 'react'

interface ContestCardProps {
  id: string
  title: string
  coverImage: string
  startDate: Date
  status: 'city' | 'country' | 'regional' | 'continental' | 'global'
  received: number
  contestants: number
  likes: number
  comments: number
  isOpen: boolean
  isFavorite: boolean
  isFeatured?: boolean
  genderRestriction?: 'male' | 'female' | null
  participationStartDate?: Date
  participationEndDate?: Date
  votingStartDate?: Date
  userGender?: 'male' | 'female' | 'other' | 'prefer_not_to_say' | null
  onViewContestants: () => void
  onToggleFavorite: () => void
  onParticipate?: () => void
  onOpenDetails?: () => void
}

export function ContestCard({
  id,
  title,
  coverImage,
  startDate,
  status,
  received,
  contestants,
  likes,
  comments,
  isOpen,
  isFavorite,
  isFeatured = false,
  genderRestriction,
  participationStartDate,
  participationEndDate,
  votingStartDate,
  userGender,
  onViewContestants,
  onToggleFavorite,
  onParticipate,
  onOpenDetails
}: ContestCardProps) {
  const { t } = useLanguage()
  const [currentTime, setCurrentTime] = useState(new Date())
  const [imageError, setImageError] = useState(false)

  // Mettre à jour l'heure chaque seconde pour le décompte en temps réel
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date())
    }, 1000)

    return () => clearInterval(interval)
  }, [])


  const getStatusColor = (status: string) => {
    switch (status) {
      case 'city':
        return 'bg-cyan-500/90 text-white'
      case 'country':
        return 'bg-blue-500/90 text-white'
      case 'regional':
        return 'bg-green-500/90 text-white'
      case 'continental':
        return 'bg-purple-500/90 text-white'
      case 'global':
        return 'bg-amber-500/90 text-white'
      default:
        return 'bg-gray-500/90 text-white'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'city':
        return t('dashboard.contests.city') || 'Ville'
      case 'country':
        return t('dashboard.contests.country')
      case 'regional':
        return t('dashboard.contests.regional')
      case 'continental':
        return t('dashboard.contests.continental')
      case 'global':
        return t('dashboard.contests.global') || 'Global'
      default:
        return status
    }
  }

  const isParticipationOngoing = () => {
    if (!participationStartDate || !participationEndDate) return false
    const now = currentTime
    const start = new Date(participationStartDate)
    const end = new Date(participationEndDate)
    const votingStart = votingStartDate ? new Date(votingStartDate) : null
    
    if (now < start || now > end) return false
    if (votingStart && now >= votingStart) return false
    return true
  }
  
  const canParticipate = () => {
    // Vérifier que le concours est ouvert et que la participation est en cours
    if (!isOpen || !isParticipationOngoing()) {
      return false
    }
    
    // Vérifier les restrictions de genre
    if (genderRestriction) {
      // Si l'utilisateur n'a pas de genre défini, il ne peut pas participer
      if (!userGender) {
        return false
      }
      
      // Vérifier que le genre de l'utilisateur correspond à la restriction
      if (genderRestriction === 'male' && userGender !== 'male') {
        return false
      }
      
      if (genderRestriction === 'female' && userGender !== 'female') {
        return false
      }
    }
    
    return true
  }

  const getCountdownText = () => {
    const now = currentTime
    
    if (votingStartDate) {
      const votingStart = new Date(votingStartDate)
      if (now >= votingStart) return ''
    }
    
    let endDate: Date | null = null
    
    if (participationEndDate) {
      endDate = new Date(participationEndDate)
    }
    
    if (votingStartDate) {
      const votingStart = new Date(votingStartDate)
      if (!endDate || votingStart < endDate) {
        endDate = votingStart
      }
    }
    
    if (!endDate || now > endDate) return ''
    
    const diffMs = endDate.getTime() - now.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    const diffHours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))
    const diffSeconds = Math.floor((diffMs % (1000 * 60)) / 1000)
    
    if (diffDays > 0) {
      return `${diffDays}j ${diffHours}h`
    } else if (diffHours > 0) {
      return `${diffHours}h ${diffMinutes}m`
    } else if (diffMinutes > 0) {
      return `${diffMinutes}m ${diffSeconds}s`
    } else if (diffSeconds > 0) {
      return `${diffSeconds}s`
    } else {
      return '0s'
    }
  }

  return (
    <div 
      className={`group relative bg-white dark:bg-gray-800 rounded-3xl overflow-hidden border border-gray-200 dark:border-gray-700 shadow-lg hover:shadow-2xl transition-all duration-500 cursor-pointer aspect-[4/5] ${
        isFeatured ? 'md:scale-105 md:z-10' : ''
      }`}
      onClick={onOpenDetails ?? onViewContestants}
    >
      {/* Cover Image Section */}
      <div className="relative h-full w-full bg-gradient-to-br from-myfav-primary via-myfav-primary-dark to-purple-600 overflow-hidden">
        {coverImage && !imageError && (coverImage.startsWith('http') || coverImage.startsWith('/') || coverImage.startsWith('data:')) ? (
          <Image
            src={coverImage}
            alt={title}
            fill
            className="object-cover group-hover:scale-110 transition-transform duration-700 ease-out"
            priority={false}
            sizes="(max-width: 768px) 100vw, 50vw"
            unoptimized={true}
            onError={() => {
              console.error(`[ContestCard] Failed to load image: ${coverImage}`)
              setImageError(true)
            }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-8xl bg-gradient-to-br from-myfav-primary/30 via-myfav-primary-dark/30 to-purple-600/30">
            {coverImage && !coverImage.startsWith('http') && !coverImage.startsWith('/') && !coverImage.startsWith('data:') ? coverImage : '💎'}
          </div>
        )}
        
        {/* Gradient Overlay - Légère par défaut, plus sombre au hover */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent group-hover:from-black/80 group-hover:via-black/60 transition-all duration-500"></div>
        
        {/* Top Bar with Badges and Favorite - Always visible */}
        <div className="absolute top-0 left-0 right-0 p-4 flex items-start justify-between z-30">
          <div className="flex flex-wrap gap-2">
            <Badge className={`${getStatusColor(status)} border-0 text-xs font-bold shadow-lg backdrop-blur-md px-3 py-1.5`}>
              {getStatusLabel(status)}
            </Badge>
            {genderRestriction && (genderRestriction === 'male' || genderRestriction === 'female') && (
              <Badge className="bg-pink-500/95 text-white border-0 text-xs font-bold shadow-lg backdrop-blur-md px-3 py-1.5 whitespace-nowrap">
                {genderRestriction === 'male' 
                  ? (t('dashboard.contests.male_only') || 'Hommes uniquement')
                  : (t('dashboard.contests.female_only') || 'Femmes uniquement')
                }
              </Badge>
            )}
          </div>
          
          <button
            onClick={(e) => {
              e.stopPropagation()
              onToggleFavorite()
            }}
            className="p-2.5 bg-white/20 dark:bg-gray-800/20 backdrop-blur-md rounded-full hover:bg-white/30 dark:hover:bg-gray-700/30 transition-all shadow-lg hover:scale-110 z-30"
          >
            <Heart
              className={`w-5 h-5 transition-all ${
                isFavorite
                  ? 'fill-red-500 text-red-500 scale-110'
                  : 'text-white hover:text-red-300'
              }`}
            />
          </button>
        </div>

        {/* Title - Visible par défaut, masqué au hover */}
        <div className="absolute bottom-0 left-0 right-0 p-6 z-20 transition-opacity duration-500 group-hover:opacity-0">
          <div className="bg-black/40 backdrop-blur-md rounded-xl px-4 py-3 border border-white/10">
            <h3 className={`${isFeatured ? 'text-3xl' : 'text-2xl'} font-bold text-white drop-shadow-lg line-clamp-2 leading-tight`}>
              {title}
            </h3>
          </div>
        </div>

        {/* Hover Overlay - Shows additional info only on hover */}
        <div className="absolute inset-0 bg-black/75 backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-all duration-500 flex flex-col items-center justify-center p-6 z-20 pointer-events-none">
          {/* Time Remaining */}
          {canParticipate() && getCountdownText() && (
            <div className="mb-8 text-center transform translate-y-4 group-hover:translate-y-0 transition-transform duration-500 delay-100">
              <div className="flex items-center justify-center gap-2 mb-3">
                <Clock className="w-6 h-6 text-white animate-pulse" />
                <span className="text-white/90 text-sm font-semibold uppercase tracking-wide">
                  {t('dashboard.contests.time_remaining') || 'Temps restant'}
                </span>
            </div>
              <p className="text-4xl font-bold text-white font-mono tracking-tight">
                {getCountdownText()}
              </p>
          </div>
        )}

          {/* Number of Participants */}
          <div className={`text-center transform translate-y-4 group-hover:translate-y-0 transition-transform duration-500 ${canParticipate() && getCountdownText() ? 'mb-8' : 'mb-8'}`}>
            <div className="flex items-center justify-center gap-2 mb-3">
              <Users className="w-6 h-6 text-white" />
              <span className="text-white/90 text-sm font-semibold uppercase tracking-wide">
                {t('dashboard.contests.contestants')}
              </span>
          </div>
            <p className="text-4xl font-bold text-white">
              {contestants.toLocaleString()}
            </p>
        </div>

          {/* Participate Button */}
          {canParticipate() && onParticipate && (
            <div className="transform translate-y-4 group-hover:translate-y-0 transition-transform duration-500 delay-200 pointer-events-auto">
              <Button
                onClick={(e) => {
                  e.stopPropagation()
                  onParticipate()
                }}
                className="bg-gradient-to-r from-myfav-primary to-myfav-primary-dark hover:from-myfav-primary-dark hover:to-purple-600 text-white font-bold px-10 py-7 text-lg shadow-2xl hover:shadow-myfav-primary/50 transition-all hover:scale-110 rounded-xl"
            >
              {t('dashboard.contests.participate')}
                <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
