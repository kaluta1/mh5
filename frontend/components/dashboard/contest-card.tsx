'use client'

import * as React from 'react'
import Image from 'next/image'
import { Heart, Users, Clock, ArrowRight, Eye, Mic, ShieldCheck, FileCheck, PawPrint, Users2, Music, Trophy, Calendar, Vote, Sparkles, MapPin, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { Badge } from '@/components/ui/badge'
import { useState, useEffect } from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'

interface TopContestant {
  id: number
  user_id?: number  // ID de l'utilisateur qui a créé cette participation
  author_name?: string
  author_avatar_url?: string
  image_url?: string  // Image de soumission du contestant
  votes_count?: number
  rank?: number
}

interface ContestCardProps {
  id: string
  title: string
  description?: string
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
  isNomination?: boolean  // Indique si on est dans l'onglet Nomination
  votingType?: {
    id: number
    name: string
    voting_level: string
    commission_source: string
    commission_rules?: any
  } | null
  currentUserContesting?: boolean  // Indique si l'utilisateur connecté a déjà participé
  onViewContestants: () => void
  onToggleFavorite: () => void
  onParticipate?: () => void
  onOpenDetails?: () => void
}

export function ContestCard({
  id,
  title,
  description,
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
  isNomination = false,
  votingType = null,
  currentUserContesting = false,
  onViewContestants,
  onToggleFavorite,
  onParticipate,
  onOpenDetails
}: ContestCardProps) {
  const { t } = useLanguage()
  const [currentTime, setCurrentTime] = useState(new Date())
  const [imageError, setImageError] = useState(false)
  const [showInfoDialog, setShowInfoDialog] = useState(false)

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

    const daysUnit = t('dashboard.contests.time_unit_days') || 'j'
    const hoursUnit = t('dashboard.contests.time_unit_hours') || 'h'
    const minutesUnit = t('dashboard.contests.time_unit_minutes') || 'm'
    const secondsUnit = t('dashboard.contests.time_unit_seconds') || 's'

    if (diffDays > 0) {
      return `${diffDays}${daysUnit} ${diffHours}${hoursUnit}`
    } else if (diffHours > 0) {
      return `${diffHours}${hoursUnit} ${diffMinutes}${minutesUnit}`
    } else if (diffMinutes > 0) {
      return `${diffMinutes}${minutesUnit} ${diffSeconds}${secondsUnit}`
    } else if (diffSeconds > 0) {
      return `${diffSeconds}${secondsUnit}`
    } else {
      return `0${secondsUnit}`
    }
  }

  return (
    <div
      className={`relative bg-gray-900 rounded-xl overflow-hidden shadow-xl hover:shadow-2xl transition-all duration-300 flex flex-col border border-gray-800 hover:border-gray-700 ${isFeatured ? 'md:scale-105 md:z-10 ring-2 ring-myhigh5-primary/50' : ''
        }`}
    >
      {/* Cover Image Section */}
      <div className="relative w-full aspect-[4/3] bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary-dark to-purple-600 overflow-hidden cursor-pointer"
        onClick={onOpenDetails ?? onViewContestants}>
        {coverImage && !imageError && (coverImage.startsWith('http') || coverImage.startsWith('/') || coverImage.startsWith('data:')) ? (
          <Image
            src={coverImage}
            alt={title}
            fill
            className="object-cover"
            priority={false}
            sizes="(max-width: 768px) 100vw, 50vw"
            unoptimized={true}
            onError={() => {
              console.error(`[ContestCard] Failed to load image: ${coverImage}`)
              setImageError(true)
            }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-6xl bg-gradient-to-br from-myhigh5-primary/30 via-myhigh5-primary-dark/30 to-purple-600/30">
            {coverImage && !coverImage.startsWith('http') && !coverImage.startsWith('/') && !coverImage.startsWith('data:') ? coverImage : '💎'}
          </div>
        )}

        {/* Time remaining overlay on photo */}
        {isParticipationOngoing() && getCountdownText() && (
          <div className="absolute bottom-3 left-3 right-3 z-10" onClick={(e) => e.stopPropagation()}>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="bg-black/80 backdrop-blur-md rounded-lg px-2.5 py-1.5 border border-white/20 cursor-help">
                    <div className="flex items-center gap-1.5">
                      <Clock className="w-3 h-3 text-myhigh5-secondary animate-pulse flex-shrink-0" />
                      <span className="text-white text-[10px] font-medium truncate flex-1">
                        {isNomination
                          ? (t('dashboard.contests.time_remaining_to_nominate') || 'Temps restant pour nommer')
                          : (t('dashboard.contests.time_remaining_to_participate') || 'Temps restant pour concourir')
                        }
                      </span>
                      <span className="text-white font-bold font-mono text-[10px] flex-shrink-0">{getCountdownText()}</span>
                    </div>
                  </div>
                </TooltipTrigger>
                <TooltipContent className="bg-gray-800 text-white border-gray-700 max-w-xs">
                  <p className="text-xs">
                    {participationEndDate
                      ? `${t('dashboard.contests.tooltip_time_remaining') || 'Temps restant avant la fin des inscriptions'}: ${new Date(participationEndDate).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })}`
                      : t('dashboard.contests.tooltip_time_remaining') || 'Temps restant pour participer au concours'}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        )}

        {/* KYC badge on cover image - top right */}
        {requiresKyc && (
          <div className="absolute top-3 right-3 z-10" onClick={(e) => e.stopPropagation()}>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1 bg-emerald-500/90 backdrop-blur-md rounded-full px-2 py-1 border border-emerald-400/50 shadow-lg cursor-help">
                    <ShieldCheck className="w-3 h-3 text-white" />
                    <span className="text-white text-[10px] font-semibold whitespace-nowrap">
                      {t('dashboard.contests.kyc_required') || 'KYC'}
                    </span>
                  </div>
                </TooltipTrigger>
                <TooltipContent className="bg-gray-800 text-white border-gray-700">
                  <p className="text-xs">
                    {t('dashboard.contests.kyc_required_description') || 'Seuls les participants avec une identité vérifiée peuvent participer à ce concours'}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        )}

        {/* Info button - top right (or top left if KYC is shown) */}
        <div className={`absolute ${requiresKyc ? 'top-3 left-3' : 'top-3 right-3'} z-10`} onClick={(e) => e.stopPropagation()}>
          <Dialog open={showInfoDialog} onOpenChange={setShowInfoDialog}>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <DialogTrigger asChild>
                    <button className="p-2 bg-black/70 backdrop-blur-md rounded-full hover:bg-black/90 transition-all shadow-lg cursor-help">
                      <Info className="w-4 h-4 text-white" />
                    </button>
                  </DialogTrigger>
                </TooltipTrigger>
                <TooltipContent className="bg-gray-800 text-white border-gray-700">
                  <p className="text-xs">{t('dashboard.contests.tooltip_info') || 'Voir les détails et les conditions du concours'}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto bg-gray-900 border-gray-700">
              <DialogHeader>
                <DialogTitle className="text-white text-xl font-bold">{title}</DialogTitle>
              </DialogHeader>
              <div className="space-y-6 mt-4">
                {/* Contest Information */}
                <div>
                  <h3 className="text-white font-semibold mb-3">{t('dashboard.contests.contest_info') || 'Informations du concours'}</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {/* Level */}
                    <div className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                      <MapPin className="w-5 h-5 text-myhigh5-secondary" />
                      <div>
                        <p className="text-gray-400 text-xs mb-1">{t('dashboard.contests.level') || 'Niveau'}</p>
                        <p className="text-white font-medium text-sm">{getStatusLabel(status)}</p>
                      </div>
                    </div>
                    {/* Voting Type */}
                    {votingType && (
                      <div className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                        <Trophy className="w-5 h-5 text-yellow-400" />
                        <div>
                          <p className="text-gray-400 text-xs mb-1">{t('dashboard.contests.voting_type') || 'Type de vote'}</p>
                          <p className="text-white font-medium text-sm">{votingType.name}</p>
                          <p className="text-gray-500 text-xs mt-0.5">
                            {votingType.voting_level === 'country'
                              ? (t('dashboard.contests.voting_level_country') || 'National')
                              : votingType.voting_level === 'city'
                                ? (t('dashboard.contests.voting_level_city') || 'Ville')
                                : votingType.voting_level === 'regional'
                                  ? (t('dashboard.contests.voting_level_regional') || 'Régional')
                                  : votingType.voting_level === 'continent'
                                    ? (t('dashboard.contests.voting_level_continent') || 'Continental')
                                    : (t('dashboard.contests.voting_level_global') || 'Global')
                            }
                          </p>
                        </div>
                      </div>
                    )}
                    {/* Participant Type */}
                    {participantType && (
                      <div className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                        <Users2 className="w-5 h-5 text-blue-400" />
                        <div>
                          <p className="text-gray-400 text-xs mb-1">{t('dashboard.contests.participant_type') || 'Type de participant'}</p>
                          <p className="text-white font-medium text-sm">
                            {participantType === 'individual'
                              ? (t('dashboard.contests.participant_individual') || 'Individuel')
                              : participantType === 'pet'
                                ? (t('dashboard.contests.participant_pet') || 'Animal')
                                : participantType === 'club'
                                  ? (t('dashboard.contests.participant_club') || 'Club')
                                  : (t('dashboard.contests.participant_content') || 'Contenu')
                            }
                          </p>
                        </div>
                      </div>
                    )}
                    {/* Statistics */}
                    <div className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                      <Users className="w-5 h-5 text-green-400" />
                      <div>
                        <p className="text-gray-400 text-xs mb-1">{t('dashboard.contests.contestants') || 'Participants'}</p>
                        <p className="text-white font-medium text-sm">{contestants.toLocaleString()}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                      <Vote className="w-5 h-5 text-purple-400" />
                      <div>
                        <p className="text-gray-400 text-xs mb-1">{t('dashboard.contests.received') || 'Votes'}</p>
                        <p className="text-white font-medium text-sm">{received.toLocaleString()}</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Dates */}
                {(participationStartDate || participationEndDate || votingStartDate) && (
                  <div>
                    <h3 className="text-white font-semibold mb-3">{t('dashboard.contests.contest_dates') || 'Dates du concours'}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {participationStartDate && (
                        <div className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                          <Calendar className="w-5 h-5 text-blue-400" />
                          <div>
                            <p className="text-gray-400 text-xs mb-1">{t('dashboard.contests.submission_start') || 'Début des inscriptions'}</p>
                            <p className="text-white font-medium text-sm">{new Date(participationStartDate).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
                          </div>
                        </div>
                      )}
                      {participationEndDate && (
                        <div className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                          <Calendar className="w-5 h-5 text-orange-400" />
                          <div>
                            <p className="text-gray-400 text-xs mb-1">{t('dashboard.contests.submission_end') || 'Fin des inscriptions'}</p>
                            <p className="text-white font-medium text-sm">{new Date(participationEndDate).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
                          </div>
                        </div>
                      )}
                      {votingStartDate && (
                        <div className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                          <Calendar className="w-5 h-5 text-purple-400" />
                          <div>
                            <p className="text-gray-400 text-xs mb-1">{t('dashboard.contests.voting_start') || 'Début du vote'}</p>
                            <p className="text-white font-medium text-sm">{new Date(votingStartDate).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Description */}
                {description && (
                  <div>
                    <h3 className="text-white font-semibold mb-2">{t('dashboard.contests.description') || 'Description'}</h3>
                    <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap">{description}</p>
                  </div>
                )}

                {/* Requirements */}
                {(requiresKyc || requiresVisualVerification || requiresVoiceVerification || requiresBrandVerification || requiresContentVerification || genderRestriction || minAge || maxAge) && (
                  <div>
                    <h3 className="text-white font-semibold mb-3">{t('dashboard.contests.requirements') || 'Conditions requises'}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {requiresKyc && (
                        <div className="flex items-center gap-2 bg-emerald-500/20 border border-emerald-500/30 rounded-lg p-3">
                          <ShieldCheck className="w-5 h-5 text-emerald-300" />
                          <div>
                            <p className="text-emerald-300 font-medium text-sm">{t('dashboard.contests.kyc_required') || 'Identité vérifiée'}</p>
                            <p className="text-gray-400 text-xs">{t('dashboard.contests.kyc_required_description') || 'Seuls les participants avec une identité vérifiée peuvent participer à ce concours'}</p>
                          </div>
                        </div>
                      )}
                      {requiresVisualVerification && (
                        <div className="flex items-center gap-2 bg-blue-500/20 border border-blue-500/30 rounded-lg p-3">
                          <Eye className="w-5 h-5 text-blue-300" />
                          <div>
                            <p className="text-blue-300 font-medium text-sm">{t('dashboard.contests.visual_verification') || 'Photo de vous'}</p>
                            <p className="text-gray-400 text-xs">{t('dashboard.contests.visual_verification_description') || 'Une photo de vous est obligatoire pour participer à ce concours'}</p>
                          </div>
                        </div>
                      )}
                      {requiresVoiceVerification && (
                        <div className="flex items-center gap-2 bg-purple-500/20 border border-purple-500/30 rounded-lg p-3">
                          <Mic className="w-5 h-5 text-purple-300" />
                          <div>
                            <p className="text-purple-300 font-medium text-sm">{t('dashboard.contests.voice_verification') || 'Vérification vocale'}</p>
                            <p className="text-gray-400 text-xs">{t('dashboard.contests.voice_verification_description') || 'Une vérification vocale est obligatoire pour participer à ce concours'}</p>
                          </div>
                        </div>
                      )}
                      {requiresBrandVerification && (
                        <div className="flex items-center gap-2 bg-amber-500/20 border border-amber-500/30 rounded-lg p-3">
                          <Trophy className="w-5 h-5 text-amber-300" />
                          <div>
                            <p className="text-amber-300 font-medium text-sm">{t('dashboard.contests.brand_verification') || 'Marque vérifiée'}</p>
                            <p className="text-gray-400 text-xs">{t('dashboard.contests.brand_verification_description') || 'Seules les marques vérifiées peuvent participer à ce concours'}</p>
                          </div>
                        </div>
                      )}
                      {requiresContentVerification && (
                        <div className="flex items-center gap-2 bg-cyan-500/20 border border-cyan-500/30 rounded-lg p-3">
                          <FileCheck className="w-5 h-5 text-cyan-300" />
                          <div>
                            <p className="text-cyan-300 font-medium text-sm">{t('dashboard.contests.content_verification') || 'Contenu original'}</p>
                            <p className="text-gray-400 text-xs">{t('dashboard.contests.content_verification_description') || 'Seul le contenu original est autorisé pour participer à ce concours'}</p>
                          </div>
                        </div>
                      )}
                      {genderRestriction && (
                        <div className="flex items-center gap-2 bg-pink-500/20 border border-pink-500/30 rounded-lg p-3">
                          <span className="text-2xl">{genderRestriction === 'female' ? '♀' : '♂'}</span>
                          <div>
                            <p className="text-pink-300 font-medium text-sm">
                              {genderRestriction === 'female'
                                ? (t('dashboard.contests.female_only') || 'Femmes uniquement')
                                : (t('dashboard.contests.male_only') || 'Hommes uniquement')}
                            </p>
                            <p className="text-gray-400 text-xs">
                              {genderRestriction === 'female'
                                ? (t('dashboard.contests.gender_restriction_female_description') || 'Seules les participantes féminines sont autorisées à participer à ce concours')
                                : (t('dashboard.contests.gender_restriction_male_description') || 'Seuls les participants masculins sont autorisés à participer à ce concours')}
                            </p>
                          </div>
                        </div>
                      )}
                      {(minAge || maxAge) && (
                        <div className="flex items-center gap-2 bg-orange-500/20 border border-orange-500/30 rounded-lg p-3">
                          <Calendar className="w-5 h-5 text-orange-300" />
                          <div>
                            <p className="text-orange-300 font-medium text-sm">
                              {minAge && maxAge
                                ? `${minAge}-${maxAge} ${t('dashboard.contests.years') || 'ans'}`
                                : minAge
                                  ? `${minAge}+ ${t('dashboard.contests.years') || 'ans'}`
                                  : `< ${maxAge} ${t('dashboard.contests.years') || 'ans'}`
                              }
                            </p>
                            <p className="text-gray-400 text-xs">{t('dashboard.contests.age_restriction_description') || 'Seuls les participants dans la tranche d\'âge spécifiée peuvent participer'}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Bottom Section - Always visible details */}
      <div className="p-4 bg-gradient-to-b from-gray-900 to-gray-950 flex flex-col gap-3 border-t border-gray-800">
        {/* Title */}
        <h3 className="text-white font-bold text-base line-clamp-2 leading-tight hover:text-myhigh5-secondary transition-colors cursor-pointer"
          onClick={onOpenDetails ?? onViewContestants}>
          {title}
        </h3>

        {/* Status and Gender restriction */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Gender restriction before level */}
          {genderRestriction && (genderRestriction === 'male' || genderRestriction === 'female') && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="text-pink-400 text-xs font-medium whitespace-nowrap cursor-help">
                    {genderRestriction === 'female' ? '♀' : '♂'} {genderRestriction === 'female'
                      ? (t('dashboard.contests.female_only') || 'Femmes uniquement')
                      : (t('dashboard.contests.male_only') || 'Hommes uniquement')}
                  </span>
                </TooltipTrigger>
                <TooltipContent className="bg-gray-800 text-white border-gray-700">
                  <p className="text-xs">
                    {genderRestriction === 'female'
                      ? (t('dashboard.contests.tooltip_gender_restriction_female') || 'Ce concours est réservé aux femmes uniquement')
                      : (t('dashboard.contests.tooltip_gender_restriction_male') || 'Ce concours est réservé aux hommes uniquement')}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-1 cursor-help">
                  <MapPin className="w-3 h-3 text-myhigh5-secondary" />
                  <Badge className={`${getStatusColor(status)} border-0 text-[10px] font-medium px-1.5 py-0.5`}>
                    {getStatusLabel(status)}
                  </Badge>
                </div>
              </TooltipTrigger>
              <TooltipContent className="bg-gray-800 text-white border-gray-700">
                <p className="text-xs">
                  {status === 'city'
                    ? (t('dashboard.contests.tooltip_level_city') || 'Concours au niveau de la ville')
                    : status === 'country'
                      ? (t('dashboard.contests.tooltip_level_country') || 'Concours au niveau national')
                      : status === 'regional'
                        ? (t('dashboard.contests.tooltip_level_regional') || 'Concours au niveau régional')
                        : status === 'continental'
                          ? (t('dashboard.contests.tooltip_level_continental') || 'Concours au niveau continental')
                          : (t('dashboard.contests.tooltip_level_global') || 'Concours au niveau mondial')}
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          {isOpen && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="flex items-center gap-1 bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full text-[10px] font-semibold border border-green-500/30 whitespace-nowrap cursor-help">
                    <span className="w-1 h-1 bg-green-400 rounded-full animate-pulse" />
                    {t('dashboard.contests.open') || 'Ouvert'}
                  </span>
                </TooltipTrigger>
                <TooltipContent className="bg-gray-800 text-white border-gray-700">
                  <p className="text-xs">
                    {t('dashboard.contests.tooltip_open') || 'Les inscriptions sont actuellement ouvertes. Vous pouvez participer à ce concours.'}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>

        {/* Stats - Simplified: just icon + number */}
        <div className="flex items-center gap-3">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-1 text-gray-400 cursor-help">
                  <Users className="w-3.5 h-3.5" />
                  <span className="text-white font-semibold text-sm">{contestants.toLocaleString()}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent className="bg-gray-800 text-white border-gray-700">
                <p className="text-xs">
                  {t('dashboard.contests.tooltip_contestants') || `${contestants.toLocaleString()} participant${contestants > 1 ? 's' : ''} dans ce concours`}
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-1 text-gray-400 cursor-help">
                  <Vote className="w-3.5 h-3.5" />
                  <span className="text-white font-semibold text-sm">{received.toLocaleString()}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent className="bg-gray-800 text-white border-gray-700">
                <p className="text-xs">
                  {t('dashboard.contests.tooltip_votes') || `${received.toLocaleString()} vote${received > 1 ? 's' : ''} reçu${received > 1 ? 's' : ''} au total`}
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* Action Buttons - Always visible */}
        <div className="pt-1 flex gap-2">
          {canParticipate() && onParticipate ? (
            <>
              <Button
                onClick={(e) => {
                  e.stopPropagation()
                  onParticipate()
                }}
                className="flex-1 bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white font-semibold py-2.5 text-xs shadow-lg shadow-myhigh5-primary/20 hover:shadow-xl hover:shadow-myhigh5-primary/40 transition-all duration-300 hover:scale-[1.02] rounded-lg group/btn relative overflow-hidden"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover/btn:translate-x-full transition-transform duration-500" />
                <Sparkles className="w-3.5 h-3.5 mr-1.5 group-hover/btn:scale-110 group-hover/btn:rotate-12 transition-all duration-300" />
                {currentUserContesting
                  ? (t('dashboard.contests.edit') || 'Modifier')
                  : isNomination
                    ? (t('dashboard.contests.nominate') || 'Nommer')
                    : (t('dashboard.contests.participate') || 'Participer')
                }
                <ArrowRight className="w-3.5 h-3.5 ml-1.5 group-hover/btn:translate-x-1 group-hover/btn:scale-110 transition-all duration-300" />
              </Button>
              <Button
                onClick={(e) => {
                  e.stopPropagation()
                  onViewContestants()
                }}
                variant="outline"
                className="flex-1 bg-gray-800/50 hover:bg-gray-800 text-white border-gray-700 hover:border-myhigh5-primary/50 font-medium py-2.5 text-xs rounded-lg transition-all duration-300 group/view relative overflow-hidden hover:shadow-lg hover:shadow-myhigh5-primary/20"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-myhigh5-primary/10 via-myhigh5-primary/20 to-myhigh5-primary/10 opacity-0 group-hover/view:opacity-100 transition-opacity duration-300" />
                <Eye className="w-4 h-4 mr-1.5 group-hover/view:scale-110 group-hover/view:text-myhigh5-secondary transition-all duration-300 relative z-10" />
                <span className="relative z-10 group-hover/view:text-white transition-colors duration-300">
                  {t('dashboard.contests.view') || 'Voir'} {t('dashboard.contests.contestant') || 'participant'}{contestants > 1 ? 's' : ''}
                </span>
                <ArrowRight className="w-3.5 h-3.5 ml-1.5 group-hover/view:translate-x-1 group-hover/view:text-myhigh5-secondary transition-all duration-300 relative z-10" />
              </Button>
            </>
          ) : (
            <Button
              onClick={(e) => {
                e.stopPropagation()
                onViewContestants()
              }}
              className="w-full bg-gradient-to-r from-myhigh5-primary to-purple-600 hover:from-myhigh5-primary-dark hover:to-purple-700 text-white font-semibold py-2.5 text-xs rounded-lg transition-all duration-300 group/view relative overflow-hidden shadow-lg shadow-myhigh5-primary/20 hover:shadow-xl hover:shadow-myhigh5-primary/40 hover:scale-[1.02]"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover/view:translate-x-full transition-transform duration-500" />
              <Eye className="w-4 h-4 mr-2 relative z-10 group-hover/view:scale-110 transition-transform duration-300" />
              <span className="relative z-10 group-hover/view:drop-shadow-sm transition-all duration-300">
                {t('dashboard.contests.view') || 'Voir'} {contestants} {t('dashboard.contests.contestant') || 'participant'}{contestants > 1 ? 's' : ''}
              </span>
              <ArrowRight className="w-3.5 h-3.5 ml-2 group-hover/view:translate-x-1 group-hover/view:scale-110 transition-all duration-300 relative z-10" />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
