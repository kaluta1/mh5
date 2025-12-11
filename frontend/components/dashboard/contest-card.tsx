'use client'

import Image from 'next/image'
import { Heart, Users, Clock, ArrowRight, Eye, Mic, ShieldCheck, FileCheck, PawPrint, Users2, Music, Trophy, Calendar, Vote, Sparkles, MapPin, Star } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { Badge } from '@/components/ui/badge'
import { useState, useEffect } from 'react'

interface TopContestant {
  id: number
  author_name?: string
  author_avatar_url?: string
  image_url?: string
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
  topContestants?: TopContestant[]
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

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date())
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'city': return 'bg-cyan-500'
      case 'country': return 'bg-blue-500'
      case 'regional': return 'bg-green-500'
      case 'continental': return 'bg-purple-500'
      case 'global': return 'bg-amber-500'
      default: return 'bg-gray-500'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'city': return t('dashboard.contests.city') || 'Ville'
      case 'country': return t('dashboard.contests.country') || 'Pays'
      case 'regional': return t('dashboard.contests.regional') || 'Régional'
      case 'continental': return t('dashboard.contests.continental') || 'Continental'
      case 'global': return t('dashboard.contests.global') || 'Global'
      default: return status
    }
  }

  const isParticipationOngoing = () => isOpen
  
  const isEligibleForContest = () => {
    if (!isParticipationOngoing()) return false
    if (genderRestriction) {
      if (!userGender) return false
      if (genderRestriction === 'male' && userGender !== 'male') return false
      if (genderRestriction === 'female' && userGender !== 'female') return false
    }
    return true
  }

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
    if (participationEndDate) endDate = new Date(participationEndDate)
    if (votingStartDate) {
      const votingStart = new Date(votingStartDate)
      if (!endDate || votingStart < endDate) endDate = votingStart
    }
    if (!endDate || now > endDate) return ''
    const diffMs = endDate.getTime() - now.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    const diffHours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))
    if (diffDays > 0) return `${diffDays}j ${diffHours}h`
    if (diffHours > 0) return `${diffHours}h ${diffMinutes}m`
    if (diffMinutes > 0) return `${diffMinutes}m`
    return ''
  }

  return (
    <div 
      className="group relative cursor-pointer"
      onClick={onOpenDetails ?? onViewContestants}
    >
      {/* Card Container - Expands on hover */}
      <div className={`relative bg-gray-900 rounded-2xl overflow-hidden shadow-lg transition-all duration-300 ease-out group-hover:shadow-2xl group-hover:shadow-black/50 group-hover:-translate-y-2 ${
        isFeatured ? 'ring-2 ring-amber-500' : ''
      }`}>
        
        {/* Image Section - Fixed height */}
        <div className="relative aspect-[4/3] overflow-hidden">
          {coverImage && !imageError && (coverImage.startsWith('http') || coverImage.startsWith('/') || coverImage.startsWith('data:')) ? (
            <Image
              src={coverImage}
              alt={title}
              fill
              className="object-cover transition-transform duration-500 group-hover:scale-105"
              sizes="(max-width: 768px) 100vw, 33vw"
              unoptimized={true}
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-6xl bg-gradient-to-br from-myfav-primary via-purple-600 to-pink-500">
              {coverImage && !coverImage.startsWith('http') ? coverImage : '🏆'}
            </div>
          )}
          
          {/* Gradient overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-gray-900/80 via-transparent to-transparent" />
          
          {/* Status Badge - Top left */}
          <div className="absolute top-3 left-3">
            <Badge className={`${getStatusColor(status)} text-white border-0 text-xs font-semibold px-2.5 py-1 shadow-lg`}>
              {getStatusLabel(status)}
            </Badge>
          </div>
          
          {/* Favorite Button - Top right */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              onToggleFavorite()
            }}
            className="absolute top-3 right-3 p-2 bg-black/40 backdrop-blur-sm rounded-full hover:bg-black/60 transition-all opacity-0 group-hover:opacity-100"
          >
            <Heart className={`w-4 h-4 ${isFavorite ? 'fill-red-500 text-red-500' : 'text-white'}`} />
          </button>

          {/* Bottom info on image - Title */}
          <div className="absolute bottom-0 left-0 right-0 p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className={`w-10 h-10 rounded-xl ${getStatusColor(status)} flex items-center justify-center shadow-lg`}>
                <Trophy className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-white font-bold text-base leading-tight line-clamp-1">{title}</h3>
                <p className="text-gray-400 text-xs">{getStatusLabel(status)} • {contestants} {t('dashboard.contests.contestants') || 'participants'}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Expanded Info Panel - Shows on hover */}
        <div className="max-h-0 overflow-hidden transition-all duration-300 ease-out group-hover:max-h-[280px] bg-gray-800/95 backdrop-blur-sm">
          <div className="p-4 space-y-3">
            
            {/* Stats Row */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1.5">
                  <Users className="w-4 h-4 text-blue-400" />
                  <span className="text-white font-semibold text-sm">{contestants}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Vote className="w-4 h-4 text-amber-400" />
                  <span className="text-white font-semibold text-sm">{received}</span>
                </div>
              </div>
              {isOpen && (
                <span className="flex items-center gap-1.5 bg-green-500/20 text-green-400 px-2 py-1 rounded-full text-xs font-medium">
                  <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
                  {t('dashboard.contests.open') || 'Ouvert'}
                </span>
              )}
            </div>

            {/* Description/Requirements */}
            <div className="text-gray-400 text-xs leading-relaxed">
              {(requiresKyc || requiresVisualVerification || genderRestriction || minAge || maxAge) ? (
                <div className="flex flex-wrap gap-1.5">
                  {requiresKyc && (
                    <span className="inline-flex items-center gap-1 bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded text-[10px]">
                      <ShieldCheck className="w-3 h-3" /> KYC
                    </span>
                  )}
                  {requiresVisualVerification && (
                    <span className="inline-flex items-center gap-1 bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded text-[10px]">
                      <Eye className="w-3 h-3" /> Photo
                    </span>
                  )}
                  {requiresVoiceVerification && (
                    <span className="inline-flex items-center gap-1 bg-purple-500/10 text-purple-400 px-2 py-0.5 rounded text-[10px]">
                      <Mic className="w-3 h-3" /> Voix
                    </span>
                  )}
                  {genderRestriction && (
                    <span className="inline-flex items-center gap-1 bg-pink-500/10 text-pink-400 px-2 py-0.5 rounded text-[10px]">
                      {genderRestriction === 'female' ? '♀ Femmes' : '♂ Hommes'}
                    </span>
                  )}
                  {(minAge || maxAge) && (
                    <span className="inline-flex items-center gap-1 bg-orange-500/10 text-orange-400 px-2 py-0.5 rounded text-[10px]">
                      <Calendar className="w-3 h-3" />
                      {minAge && maxAge ? `${minAge}-${maxAge} ans` : minAge ? `${minAge}+ ans` : `<${maxAge} ans`}
                    </span>
                  )}
                </div>
              ) : (
                <p>{t('dashboard.contests.open_to_all') || 'Ouvert à tous les participants'}</p>
              )}
            </div>

            {/* Countdown if applicable */}
            {getCountdownText() && (
              <div className="flex items-center gap-2 text-xs">
                <Clock className="w-3.5 h-3.5 text-myfav-secondary" />
                <span className="text-gray-400">{t('dashboard.contests.time_remaining') || 'Temps restant'}:</span>
                <span className="text-white font-mono font-medium">{getCountdownText()}</span>
              </div>
            )}

            {/* Action Button */}
            <div className="pt-2">
              {canParticipate() && onParticipate ? (
                <Button
                  onClick={(e) => {
                    e.stopPropagation()
                    onParticipate()
                  }}
                  className="w-full bg-myfav-primary hover:bg-myfav-primary-dark text-white font-semibold py-2.5 text-sm rounded-xl transition-all"
                >
                  <Sparkles className="w-4 h-4 mr-2" />
                  {t('dashboard.contests.participate') || 'Participer'}
                </Button>
              ) : (
                <Button
                  onClick={(e) => {
                    e.stopPropagation()
                    onViewContestants()
                  }}
                  variant="outline"
                  className="w-full bg-white/5 hover:bg-white/10 text-white border-white/10 hover:border-white/20 font-medium py-2.5 text-sm rounded-xl"
                >
                  <Trophy className="w-4 h-4 mr-2" />
                  {t('dashboard.contests.view_contestants') || 'Voir les candidats'}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
