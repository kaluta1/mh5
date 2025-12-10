'use client'

import Image from 'next/image'
import { Heart, Users, Clock, ArrowRight, Eye, Mic, ShieldCheck, FileCheck, PawPrint, Users2, Music, Trophy, Calendar, Vote, Sparkles, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { Badge } from '@/components/ui/badge'
import { useState, useEffect } from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface TopContestant {
  id: number
  author_name?: string
  author_avatar_url?: string
  image_url?: string  // Image de soumission du contestant
  votes_count?: number
  rank?: number
}

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
  // Top contestants for preview
  topContestants?: TopContestant[]
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
  topContestants = [],
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

  // Debug: Log topContestants data
  console.log(`Contest ${id} - topContestants:`, topContestants?.length || 0, topContestants?.map(c => ({ id: c.id, image_url: c.image_url?.substring(0, 50) })))

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
    // Le backend est l'autorité principale via isOpen (is_submission_open)
    // Si isOpen est false, les inscriptions sont fermées
    if (!isOpen) return false
    
    // Si isOpen est true, on peut aussi vérifier les dates côté client pour le décompte
    // mais le backend a déjà vérifié, donc on fait confiance
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
        
        {/* Top Bar with Badges - Visible par défaut, masqué au hover */}
        <div className="absolute top-0 left-0 right-0 p-4 flex items-start justify-between z-30 transition-all duration-300 group-hover:opacity-0 group-hover:-translate-y-4">
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
        </div>

        {/* Top Contestants Images - Horizontal, petites, en bas */}
        {topContestants && topContestants.length > 0 && (
          <div className="absolute bottom-20 left-3 right-3 z-25 transition-all duration-300 group-hover:opacity-0 group-hover:translate-y-2">
            <div className="flex items-center gap-1.5">
              {/* Horizontal small images */}
              {topContestants.slice(0, 5).map((contestant, index) => (
                <div
                  key={contestant.id}
                  className="relative w-9 h-9 rounded-lg border border-white/80 shadow-md overflow-hidden bg-gradient-to-br from-gray-600 to-gray-800 flex-shrink-0"
                >
                  {contestant.image_url ? (
                    <Image
                      src={contestant.image_url}
                      alt={contestant.author_name || 'Participant'}
                      fill
                      className="object-cover"
                      sizes="36px"
                      unoptimized
                    />
                  ) : contestant.author_avatar_url ? (
                    <Image
                      src={contestant.author_avatar_url}
                      alt={contestant.author_name || 'Participant'}
                      fill
                      className="object-cover"
                      sizes="36px"
                      unoptimized
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-white text-xs font-bold bg-gradient-to-br from-myfav-primary to-purple-600">
                      {contestant.author_name?.charAt(0)?.toUpperCase() || '?'}
                    </div>
                  )}
                  {/* Small rank indicator */}
                  {contestant.rank && contestant.rank <= 3 && (
                    <div className={`absolute -top-0.5 -left-0.5 w-3.5 h-3.5 rounded-full flex items-center justify-center text-[8px] font-bold text-white ${
                      contestant.rank === 1 ? 'bg-amber-500' : contestant.rank === 2 ? 'bg-gray-400' : 'bg-amber-700'
                    }`}>
                      {contestant.rank}
                    </div>
                  )}
                </div>
              ))}
              {/* Counter for more */}
              {contestants > 5 && (
                <span className="text-white/80 text-xs font-semibold bg-black/40 backdrop-blur-sm px-2 py-1 rounded-lg">
                  +{contestants - 5}
                </span>
              )}
            </div>
          </div>
        )}

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
          
          {/* Top Section - Level, Status & Favorite */}
          <div className="flex items-center justify-between transform -translate-y-4 group-hover:translate-y-0 transition-transform duration-300">
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-myfav-secondary" />
              <span className="text-white/90 text-sm font-medium">{getStatusLabel(status)}</span>
              {isOpen && (
                <span className="flex items-center gap-1.5 bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full text-xs font-semibold border border-green-500/30">
                  <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
                  {t('dashboard.contests.open') || 'Ouvert'}
                </span>
              )}
            </div>
            {/* Favorite Button - Only visible on hover */}
            <button
              onClick={(e) => {
                e.stopPropagation()
                onToggleFavorite()
              }}
              className="p-2.5 bg-white/20 backdrop-blur-md rounded-full hover:bg-white/30 transition-all shadow-lg hover:scale-110 pointer-events-auto"
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

            {/* Requirements Summary with explanatory text */}
            {(requiresKyc || requiresVisualVerification || requiresVoiceVerification || requiresBrandVerification || requiresContentVerification || genderRestriction || minAge || maxAge) && (
              <div className="w-full max-w-[320px] bg-white/5 backdrop-blur-sm rounded-xl p-3 border border-white/10 transform translate-y-4 group-hover:translate-y-0 transition-transform duration-400 delay-150">
                <p className="text-white/60 text-[10px] uppercase tracking-wider mb-2 text-center font-semibold">
                  {t('dashboard.contests.requirements') || 'Conditions requises'}
                </p>
                <div className="flex flex-wrap justify-center gap-1.5">
                  {requiresKyc && (
                    <span className="flex items-center gap-1 bg-emerald-500/20 text-emerald-300 px-2 py-1 rounded-lg text-[10px] border border-emerald-500/30">
                      <ShieldCheck className="w-3 h-3" /> {t('dashboard.contests.kyc_required') || 'Identité vérifiée'}
                    </span>
                  )}
                  {requiresVisualVerification && (
                    <span className="flex items-center gap-1 bg-blue-500/20 text-blue-300 px-2 py-1 rounded-lg text-[10px] border border-blue-500/30">
                      <Eye className="w-3 h-3" /> {t('dashboard.contests.visual_verification') || 'Photo de vous'}
                    </span>
                  )}
                  {requiresVoiceVerification && (
                    <span className="flex items-center gap-1 bg-purple-500/20 text-purple-300 px-2 py-1 rounded-lg text-[10px] border border-purple-500/30">
                      <Mic className="w-3 h-3" /> {t('dashboard.contests.voice_verification') || 'Vérification vocale'}
                    </span>
                  )}
                  {requiresBrandVerification && (
                    <span className="flex items-center gap-1 bg-amber-500/20 text-amber-300 px-2 py-1 rounded-lg text-[10px] border border-amber-500/30">
                      <Trophy className="w-3 h-3" /> {t('dashboard.contests.brand_verification') || 'Marque vérifiée'}
                    </span>
                  )}
                  {requiresContentVerification && (
                    <span className="flex items-center gap-1 bg-cyan-500/20 text-cyan-300 px-2 py-1 rounded-lg text-[10px] border border-cyan-500/30">
                      <FileCheck className="w-3 h-3" /> {t('dashboard.contests.content_verification') || 'Contenu original'}
                    </span>
                  )}
                  {genderRestriction && (
                    <span className="flex items-center gap-1 bg-pink-500/20 text-pink-300 px-2 py-1 rounded-lg text-[10px] border border-pink-500/30">
                      {genderRestriction === 'female' ? '♀' : '♂'} {genderRestriction === 'female' 
                        ? (t('dashboard.contests.female_only') || 'Femmes uniquement') 
                        : (t('dashboard.contests.male_only') || 'Hommes uniquement')}
                    </span>
                  )}
                  {(minAge || maxAge) && (
                    <span className="flex items-center gap-1 bg-orange-500/20 text-orange-300 px-2 py-1 rounded-lg text-[10px] border border-orange-500/30">
                      <Calendar className="w-3 h-3" /> 
                      {minAge && maxAge 
                        ? `${minAge}-${maxAge} ${t('dashboard.contests.years') || 'ans'}`
                        : minAge 
                          ? `${minAge}+ ${t('dashboard.contests.years') || 'ans'}`
                          : `< ${maxAge} ${t('dashboard.contests.years') || 'ans'}`
                      }
                    </span>
                  )}
                </div>
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
