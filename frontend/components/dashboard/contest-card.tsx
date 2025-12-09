'use client'

import Image from 'next/image'
import { Heart, Users, Clock, ArrowRight, Eye, Mic, ShieldCheck, FileCheck, PawPrint, Users2, Music, Trophy, Calendar, Vote, Sparkles, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { Badge } from '@/components/ui/badge'
import { useState, useEffect } from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

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
  canParticipate?: boolean
  isKycVerified?: boolean
  // Verification requirements
  requiresKyc?: boolean
  verificationType?: 'none' | 'visual' | 'voice' | 'brand' | 'content'
  participantType?: 'individual' | 'pet' | 'club' | 'content'
  requiresVisualVerification?: boolean
  requiresVoiceVerification?: boolean
  requiresBrandVerification?: boolean
  requiresContentVerification?: boolean
  minAge?: number | null
  maxAge?: number | null
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
  canParticipate: userCanParticipate = true,
  isKycVerified = false,
  // Verification requirements - KYC n'est PAS requis par défaut
  requiresKyc = false,
  verificationType = 'none',
  participantType = 'individual',
  requiresVisualVerification = false,
  requiresVoiceVerification = false,
  requiresBrandVerification = false,
  requiresContentVerification = false,
  minAge = null,
  maxAge = null,
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
    // Si le backend dit que la soumission est ouverte (isOpen), faire confiance
    if (isOpen) return true
    
    // Sinon, vérifier les dates
    if (!participationStartDate || !participationEndDate) return false
    const now = currentTime
    const start = new Date(participationStartDate)
    const end = new Date(participationEndDate)
    const votingStart = votingStartDate ? new Date(votingStartDate) : null
    
    if (now < start || now > end) return false
    if (votingStart && now >= votingStart) return false
    return true
  }
  
  const isEligibleForContest = () => {
    // Vérifier que la participation est en cours
    if (!isParticipationOngoing()) {
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

  // L'utilisateur peut participer seulement s'il est éligible au concours ET a complété son profil
  // Le KYC est requis uniquement si le concours l'exige
  const canParticipate = () => {
    if (!isEligibleForContest() || !userCanParticipate) return false
    if (requiresKyc && !isKycVerified) return false
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
            {/* Participant type badge */}
            {participantType !== 'individual' && (
              <Badge className="bg-indigo-500/95 text-white border-0 text-xs font-bold shadow-lg backdrop-blur-md px-3 py-1.5 whitespace-nowrap flex items-center gap-1">
                {participantType === 'pet' && <><PawPrint className="w-3 h-3" /> Animal</>}
                {participantType === 'club' && <><Users2 className="w-3 h-3" /> Club</>}
                {participantType === 'content' && <><Music className="w-3 h-3" /> Contenu</>}
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

        {/* Title and Verification badges - Visible par défaut, masqué au hover */}
        <div className="absolute bottom-0 left-0 right-0 p-6 z-20 transition-opacity duration-500 group-hover:opacity-0">
          <div className="bg-black/40 backdrop-blur-md rounded-xl px-4 py-3 border border-white/10">
            <h3 className={`${isFeatured ? 'text-3xl' : 'text-2xl'} font-bold text-white drop-shadow-lg line-clamp-2 leading-tight`}>
              {title}
            </h3>
            {/* Verification requirement icons */}
            {(requiresKyc || requiresVisualVerification || requiresVoiceVerification || requiresBrandVerification || requiresContentVerification || minAge || maxAge) && (
              <TooltipProvider>
                <div className="flex flex-wrap gap-2 mt-2">
                  {requiresKyc && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex items-center justify-center w-6 h-6 bg-emerald-500/80 rounded-full">
                          <ShieldCheck className="w-3.5 h-3.5 text-white" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent><p>KYC requis</p></TooltipContent>
                    </Tooltip>
                  )}
                  {requiresVisualVerification && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex items-center justify-center w-6 h-6 bg-blue-500/80 rounded-full">
                          <Eye className="w-3.5 h-3.5 text-white" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent><p>Vérification visuelle</p></TooltipContent>
                    </Tooltip>
                  )}
                  {requiresVoiceVerification && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex items-center justify-center w-6 h-6 bg-purple-500/80 rounded-full">
                          <Mic className="w-3.5 h-3.5 text-white" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent><p>Vérification vocale</p></TooltipContent>
                    </Tooltip>
                  )}
                  {requiresContentVerification && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex items-center justify-center w-6 h-6 bg-amber-500/80 rounded-full">
                          <FileCheck className="w-3.5 h-3.5 text-white" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent><p>Vérification contenu</p></TooltipContent>
                    </Tooltip>
                  )}
                  {(minAge || maxAge) && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex items-center justify-center px-2 h-6 bg-orange-500/80 rounded-full text-white text-xs font-bold">
                          {minAge && maxAge ? `${minAge}-${maxAge}` : minAge ? `${minAge}+` : `<${maxAge}`}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent><p>Âge requis: {minAge && maxAge ? `${minAge}-${maxAge} ans` : minAge ? `${minAge}+ ans` : `moins de ${maxAge} ans`}</p></TooltipContent>
                    </Tooltip>
                  )}
                </div>
              </TooltipProvider>
            )}
          </div>
        </div>

        {/* Hover Overlay - Shows additional info only on hover */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/80 to-black/60 backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-all duration-400 flex flex-col p-5 z-20 pointer-events-none">
          
          {/* Top Section - Level & Status */}
          <div className="flex items-center justify-between transform -translate-y-4 group-hover:translate-y-0 transition-transform duration-300">
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-myfav-secondary" />
              <span className="text-white/90 text-sm font-medium">{getStatusLabel(status)}</span>
            </div>
            {isOpen && (
              <span className="flex items-center gap-1.5 bg-green-500/20 text-green-400 px-2.5 py-1 rounded-full text-xs font-semibold border border-green-500/30">
                <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
                {t('dashboard.contests.open') || 'Ouvert'}
              </span>
            )}
          </div>

          {/* Middle Section - Stats */}
          <div className="flex-1 flex flex-col items-center justify-center gap-4">
            {/* Stats Grid */}
            <div className="grid grid-cols-2 gap-4 w-full max-w-[280px] transform translate-y-4 group-hover:translate-y-0 transition-transform duration-400 delay-75">
              {/* Participants */}
              <div className="bg-white/10 backdrop-blur-sm rounded-xl p-3 text-center border border-white/10">
                <div className="flex items-center justify-center gap-1.5 mb-1">
                  <Users className="w-4 h-4 text-blue-400" />
                  <span className="text-white/70 text-xs">{t('dashboard.contests.contestants') || 'Participants'}</span>
                </div>
                <p className="text-2xl font-bold text-white">{contestants.toLocaleString()}</p>
              </div>
              
              {/* Votes */}
              <div className="bg-white/10 backdrop-blur-sm rounded-xl p-3 text-center border border-white/10">
                <div className="flex items-center justify-center gap-1.5 mb-1">
                  <Vote className="w-4 h-4 text-amber-400" />
                  <span className="text-white/70 text-xs">{t('dashboard.contests.votes') || 'Votes'}</span>
                </div>
                <p className="text-2xl font-bold text-white">{received.toLocaleString()}</p>
              </div>
            </div>

            {/* Time Remaining */}
            {canParticipate() && getCountdownText() && (
              <div className="bg-gradient-to-r from-myfav-primary/20 to-purple-500/20 backdrop-blur-sm rounded-xl px-4 py-2.5 border border-myfav-primary/30 transform translate-y-4 group-hover:translate-y-0 transition-transform duration-400 delay-100">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-myfav-secondary animate-pulse" />
                  <span className="text-white/80 text-xs">{t('dashboard.contests.time_remaining') || 'Temps restant'}</span>
                  <span className="text-white font-bold font-mono">{getCountdownText()}</span>
                </div>
              </div>
            )}

            {/* Requirements Summary */}
            {(requiresKyc || requiresVisualVerification || requiresVoiceVerification || genderRestriction) && (
              <div className="flex flex-wrap items-center justify-center gap-2 transform translate-y-4 group-hover:translate-y-0 transition-transform duration-400 delay-150">
                {requiresKyc && (
                  <span className="flex items-center gap-1 bg-emerald-500/20 text-emerald-300 px-2 py-1 rounded-lg text-xs border border-emerald-500/30">
                    <ShieldCheck className="w-3 h-3" /> KYC
                  </span>
                )}
                {genderRestriction && (
                  <span className="flex items-center gap-1 bg-pink-500/20 text-pink-300 px-2 py-1 rounded-lg text-xs border border-pink-500/30">
                    {genderRestriction === 'female' ? '♀' : '♂'} {genderRestriction === 'female' ? (t('dashboard.contests.women') || 'Femmes') : (t('dashboard.contests.men') || 'Hommes')}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Bottom Section - Action Button */}
          <div className="transform translate-y-4 group-hover:translate-y-0 transition-transform duration-400 delay-200 pointer-events-auto">
            {canParticipate() && onParticipate ? (
              <Button
                onClick={(e) => {
                  e.stopPropagation()
                  onParticipate()
                }}
                className="w-full bg-myfav-primary hover:bg-myfav-primary-dark text-white font-bold py-4 text-base shadow-lg shadow-myfav-primary/20 hover:shadow-myfav-primary/40 transition-all hover:scale-[1.02] rounded-xl group/btn relative overflow-hidden"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover/btn:translate-x-full transition-transform duration-700" />
                <Sparkles className="w-5 h-5 mr-2" />
                {t('dashboard.contests.participate') || 'Participer'}
                <ArrowRight className="w-5 h-5 ml-2 group-hover/btn:translate-x-1 transition-transform" />
              </Button>
            ) : (
              <Button
                onClick={(e) => {
                  e.stopPropagation()
                  onViewContestants()
                }}
                variant="outline"
                className="w-full bg-white/10 hover:bg-white/20 text-white border-white/20 hover:border-white/40 font-semibold py-4 text-base rounded-xl transition-all"
              >
                <Trophy className="w-5 h-5 mr-2" />
                {t('dashboard.contests.view_contestants') || 'Voir les candidats'}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
