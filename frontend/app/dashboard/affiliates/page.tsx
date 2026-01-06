'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { 
  Users, 
  UserPlus, 
  Link as LinkIcon,
  Copy,
  Euro,
  Award,
  ChevronRight,
  Zap,
  Target,
  CheckCircle,
  Clock,
  Mail,
  Send,
  X,
  DollarSign
} from 'lucide-react'
import Link from 'next/link'
import { InviteDialog } from '@/components/dashboard/invite-dialog'
import { cacheService } from '@/lib/cache-service'

interface Affiliate {
  id: string
  name: string
  avatar?: string
  joinedAt: string
  level: number
  totalEarnings: number
  status: 'active' | 'inactive'
  country?: string
  city?: string
  identity_verified?: boolean
  has_paid_kyc?: boolean
  commissions_generated?: number
}

interface Invitation {
  id: number
  email: string
  message?: string
  referral_code: string
  status: 'pending' | 'accepted' | 'expired' | 'cancelled'
  sent_at: string
  accepted_at?: string
}

export default function AffiliatesPage() {
  const { t, language } = useLanguage()
  const router = useRouter()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { addToast } = useToast()
  
  // Mapping des langues vers les locales
  const localeMap: Record<string, string> = {
    fr: 'fr-FR',
    en: 'en-US',
    es: 'es-ES',
    de: 'de-DE'
  }
  
  const [referralCode, setReferralCode] = useState('')
  const [referralLinks, setReferralLinks] = useState({
    register: '',
    home: '',
    contestants: ''
  })
  const [copiedLink, setCopiedLink] = useState<string | null>(null)
  const [showLinksDialog, setShowLinksDialog] = useState(false)
  const [showCommissionsDialog, setShowCommissionsDialog] = useState(false)
  const [totalAffiliates, setTotalAffiliates] = useState(0)
  const [directAffiliates, setDirectAffiliates] = useState(0)
  const [totalCommissions, setTotalCommissions] = useState(0)
  const [conversionRate, setConversionRate] = useState(0)
  const [affiliates, setAffiliates] = useState<Affiliate[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [showInviteDialog, setShowInviteDialog] = useState(false)
  const [activeTab, setActiveTab] = useState<'affiliates' | 'pending'>('affiliates')
  const [pendingInvitations, setPendingInvitations] = useState<Invitation[]>([])
  const [invitationStats, setInvitationStats] = useState({
    total_sent: 0,
    pending: 0,
    accepted: 0,
    expired: 0,
    conversion_rate: 0
  })
  const [sponsorInfo, setSponsorInfo] = useState<{
    id: number
    username?: string
    full_name?: string
    first_name?: string
    last_name?: string
    avatar_url?: string
    personal_referral_code?: string
    country?: string
    city?: string
  } | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    } else if (!isLoading && isAuthenticated) {
      loadAffiliatesData()
    }
  }, [isLoading, isAuthenticated, router])

  const getBaseUrl = () => {
    if (typeof window !== 'undefined') {
      return window.location.origin
    }
    return process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'
  }

  const generateReferralLinks = (code: string) => {
    const baseUrl = getBaseUrl()
    return {
      register: `${baseUrl}/register?ref=${code}`,
      home: `${baseUrl}/?ref=${code}`,
      contestants: `${baseUrl}/contests?ref=${code}`
    }
  }

  const loadAffiliatesData = async () => {
    try {
      const token = localStorage.getItem('access_token')
      if (!token) return
      
      const headers = { 'Authorization': `Bearer ${token}` }
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      // Récupérer les statistiques d'affiliation (avec cache)
      const statsEndpoint = '/api/v1/affiliates/stats'
      const statsCacheKey = statsEndpoint
      const cachedStats = cacheService.get<any>(statsCacheKey)
      
      if (cachedStats) {
        const stats = cachedStats
        const code = stats.referral_code || ''
        setReferralCode(code)
        setReferralLinks(generateReferralLinks(code))
        setTotalAffiliates(stats.total_affiliates || 0)
        setDirectAffiliates(stats.direct_referrals || 0)
        setTotalCommissions(stats.total_commissions || 0)
        setConversionRate(stats.conversion_rate || 0)
      } else {
        const statsResponse = await fetch(`${baseUrl}${statsEndpoint}`, { headers })
        
        if (statsResponse.ok) {
          const stats = await statsResponse.json()
          const code = stats.referral_code || ''
          setReferralCode(code)
          setReferralLinks(generateReferralLinks(code))
          setTotalAffiliates(stats.total_affiliates || 0)
          setDirectAffiliates(stats.direct_referrals || 0)
          setTotalCommissions(stats.total_commissions || 0)
          setConversionRate(stats.conversion_rate || 0)
          // Mettre en cache
          cacheService.set(statsCacheKey, stats)
        } else {
          // Utiliser le code de l'utilisateur depuis /me si stats non disponible
          const code = user?.personal_referral_code || ''
          setReferralCode(code)
          setReferralLinks(generateReferralLinks(code))
        }
      }
      
      // Récupérer les parrainages directs (filleuls) avec les commissions (avec cache)
      const referralsEndpoint = '/api/v1/affiliates/referrals/detailed'
      const referralsParams = { limit: 10 }
      const referralsCacheKey = referralsEndpoint
      const cachedReferrals = cacheService.get<any[]>(referralsCacheKey, referralsParams)
      
      if (cachedReferrals) {
        setAffiliates(cachedReferrals.map((r: any) => ({
          id: r.id?.toString() || '',
          name: [r.first_name, r.last_name].filter(Boolean).join(' ') || r.full_name || r.username || 'N/A',
          avatar: r.avatar_url,
          joinedAt: r.created_at || new Date().toISOString(),
          level: 1,
          totalEarnings: r.commissions_generated || 0,
          status: 'active',
          country: r.country,
          city: r.city,
          identity_verified: r.identity_verified,
          has_paid_kyc: r.has_paid_kyc,
          commissions_generated: r.commissions_generated || 0
        })))
      } else {
        const referralsResponse = await fetch(`${baseUrl}${referralsEndpoint}?limit=10`, { headers })
        
        if (referralsResponse.ok) {
          const referralsData = await referralsResponse.json()
          const mappedData = referralsData.map((r: any) => ({
            id: r.id?.toString() || '',
            name: [r.first_name, r.last_name].filter(Boolean).join(' ') || r.full_name || r.username || 'N/A',
            avatar: r.avatar_url,
            joinedAt: r.created_at || new Date().toISOString(),
            level: 1,
            totalEarnings: r.commissions_generated || 0,
            status: 'active',
            country: r.country,
            city: r.city,
            identity_verified: r.identity_verified,
            has_paid_kyc: r.has_paid_kyc,
            commissions_generated: r.commissions_generated || 0
          }))
          setAffiliates(mappedData)
          // Mettre en cache les données brutes (avant mapping)
          cacheService.set(referralsCacheKey, referralsData, referralsParams)
        }
      }

      // Récupérer les informations du parrain de l'utilisateur connecté (avec cache)
      const sponsorEndpoint = '/api/v1/affiliates/sponsor'
      const sponsorCacheKey = sponsorEndpoint
      const cachedSponsor = cacheService.get<any>(sponsorCacheKey)
      
      if (cachedSponsor) {
        setSponsorInfo(cachedSponsor)
      } else {
        const sponsorResponse = await fetch(`${baseUrl}${sponsorEndpoint}`, { headers })
        if (sponsorResponse.ok) {
          const sponsorData = await sponsorResponse.json()
          if (sponsorData) {
            setSponsorInfo(sponsorData)
            // Mettre en cache
            cacheService.set(sponsorCacheKey, sponsorData)
          }
        }
      }

      // Récupérer les invitations en attente
      const invitationsResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/invitations/pending`, {
        headers
      })
      if (invitationsResponse.ok) {
        const invitationsData = await invitationsResponse.json()
        setPendingInvitations(invitationsData)
      }

      // Récupérer les stats d'invitation
      const invStatsResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/invitations/stats`, {
        headers
      })
      if (invStatsResponse.ok) {
        const invStatsData = await invStatsResponse.json()
        setInvitationStats(invStatsData)
      }
    } catch (error) {
      console.error('Error loading affiliates data:', error)
      // Fallback au code de parrainage de l'utilisateur
      const code = user?.personal_referral_code || ''
      setReferralCode(code)
      setReferralLinks(generateReferralLinks(code))
    } finally {
      setPageLoading(false)
    }
  }

  const copyToClipboard = async (text: string, linkType?: string) => {
    try {
      await navigator.clipboard.writeText(text)
      if (linkType) {
        setCopiedLink(linkType)
      }
      addToast(t('dashboard.affiliates.copied') || 'Lien copié !', 'success')
      setTimeout(() => {
        setCopiedLink(null)
      }, 2000)
    } catch (error) {
      addToast(t('dashboard.affiliates.copy_error') || 'Erreur lors de la copie', 'error')
    }
  }

  const getLevelBadge = (level: number) => {
    const colors = [
      'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
      'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
      'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
    ]
    return colors[level - 1] || colors[0]
  }

  const cancelInvitation = async (invitationId: number) => {
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/invitations/${invitationId}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      )
      
      if (response.ok) {
        setPendingInvitations(prev => prev.filter(inv => inv.id !== invitationId))
        setInvitationStats(prev => ({
          ...prev,
          pending: prev.pending - 1
        }))
        addToast(t('dashboard.affiliates.invitation_cancelled') || 'Invitation annulée', 'success')
      } else {
        addToast(t('dashboard.affiliates.cancel_error') || 'Erreur lors de l\'annulation', 'error')
      }
    } catch (error) {
      console.error('Error cancelling invitation:', error)
      addToast('Erreur lors de l\'annulation', 'error')
    }
  }

  if (isLoading || pageLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 bg-gray-200 dark:bg-gray-700 rounded-2xl" />
          ))}
        </div>
        <div className="h-48 bg-gray-200 dark:bg-gray-700 rounded-2xl" />
        <div className="h-96 bg-gray-200 dark:bg-gray-700 rounded-2xl" />
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-myhigh5-primary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
              <Users className="w-5 h-5 text-white" />
            </div>
            {t('dashboard.affiliates.title')}
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {t('dashboard.affiliates.subtitle')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button 
            onClick={() => setShowLinksDialog(true)}
            variant="outline"
            size="sm"
            className="rounded-xl"
          >
            <LinkIcon className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">{t('dashboard.affiliates.view_links') || 'Liens'}</span>
          </Button>
          <Button 
            onClick={() => setShowCommissionsDialog(true)}
            variant="outline"
            size="sm"
            className="rounded-xl"
          >
            <Award className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">{t('dashboard.affiliates.view_commissions') || 'Commissions'}</span>
          </Button>
          <Button 
            onClick={() => setShowInviteDialog(true)}
            size="sm"
            className="rounded-xl bg-myhigh5-primary hover:bg-myhigh5-primary/90 shadow-lg shadow-myhigh5-primary/25"
          >
            <UserPlus className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">{t('dashboard.affiliates.invite')}</span>
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl p-3 sm:p-5 border border-gray-100 dark:border-gray-700 shadow-sm">
          <div className="flex items-center gap-2 sm:gap-3 mb-2 sm:mb-3">
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
              <Users className="w-4 h-4 sm:w-5 sm:h-5 text-myhigh5-primary" />
            </div>
          </div>
          <p className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">{totalAffiliates}</p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('dashboard.affiliates.total_affiliates')}</p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl p-3 sm:p-5 border border-gray-100 dark:border-gray-700 shadow-sm">
          <div className="flex items-center gap-2 sm:gap-3 mb-2 sm:mb-3">
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
              <UserPlus className="w-4 h-4 sm:w-5 sm:h-5 text-green-600 dark:text-green-400" />
            </div>
          </div>
          <p className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">{directAffiliates}</p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('dashboard.affiliates.direct_affiliates')}</p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl p-3 sm:p-5 border border-gray-100 dark:border-gray-700 shadow-sm">
          <div className="flex items-center gap-2 sm:gap-3 mb-2 sm:mb-3">
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
              <DollarSign className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-600 dark:text-emerald-400" />
            </div>
          </div>
          <p className="text-lg sm:text-2xl font-bold text-gray-900 dark:text-white">
            {totalCommissions.toLocaleString('fr-FR', { style: 'currency', currency: 'USD' })}
          </p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('dashboard.affiliates.total_commissions')}</p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl p-3 sm:p-5 border border-gray-100 dark:border-gray-700 shadow-sm">
          <div className="flex items-center gap-2 sm:gap-3 mb-2 sm:mb-3">
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center">
              <Target className="w-4 h-4 sm:w-5 sm:h-5 text-purple-600 dark:text-purple-400" />
            </div>
          </div>
          <p className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">{conversionRate}%</p>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('dashboard.affiliates.conversion_rate')}</p>
        </div>
      </div>

      {/* Dialog pour les liens de parrainage */}
      <Dialog open={showLinksDialog} onOpenChange={setShowLinksDialog}>
        <DialogContent className="max-w-[95vw] sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base sm:text-lg">
              <LinkIcon className="w-4 h-4 sm:w-5 sm:h-5 text-myhigh5-primary" />
              {t('dashboard.affiliates.your_referral_links') || 'Vos liens de parrainage'}
            </DialogTitle>
            <DialogDescription className="text-xs sm:text-sm">
              {t('dashboard.affiliates.links_description') || 'Copiez et partagez ces liens pour parrainer de nouveaux utilisateurs'}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-3 sm:space-y-4 mt-3 sm:mt-4">
            {/* Sponsor Info in dialog */}
            {sponsorInfo && (
              <div className="p-3 sm:p-4 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 rounded-lg sm:rounded-xl border border-amber-200 dark:border-amber-700/50">
                <div className="flex items-center gap-2 sm:gap-3">
                  <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-amber-100 dark:bg-amber-900/50 flex items-center justify-center overflow-hidden flex-shrink-0">
                    {sponsorInfo.avatar_url ? (
                      <img src={sponsorInfo.avatar_url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <Award className="w-4 h-4 sm:w-5 sm:h-5 text-amber-600 dark:text-amber-400" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">
                      {t('dashboard.affiliates.your_sponsor') || 'Votre parrain'}
                    </p>
                    <p className="font-semibold text-sm sm:text-base text-gray-900 dark:text-white truncate">
                      {[sponsorInfo.first_name, sponsorInfo.last_name].filter(Boolean).join(' ') || sponsorInfo.full_name || sponsorInfo.username || 'Parrain'}
                    </p>
                    <div className="flex flex-wrap items-center gap-1 sm:gap-2 text-xs text-gray-500 dark:text-gray-400">
                      {(sponsorInfo.city || sponsorInfo.country) && (
                        <span className="truncate">{[sponsorInfo.city, sponsorInfo.country].filter(Boolean).join(', ')}</span>
                      )}
                      {sponsorInfo.personal_referral_code && (
                        <span className="font-mono bg-amber-100 dark:bg-amber-900/50 px-1.5 py-0.5 rounded">{sponsorInfo.personal_referral_code}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Code de parrainage */}
            <div className="p-3 sm:p-4 bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 rounded-lg sm:rounded-xl border border-myhigh5-primary/20">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div>
                  <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('dashboard.affiliates.your_code')}</p>
                  <p className="text-xl sm:text-2xl font-bold font-mono text-myhigh5-primary">{referralCode}</p>
                </div>
                <Button 
                  onClick={() => copyToClipboard(referralCode, 'code')}
                  variant="outline"
                  size="sm"
                  className={`rounded-lg w-full sm:w-auto ${copiedLink === 'code' ? 'bg-green-100 border-green-500 text-green-700' : ''}`}
                >
                  {copiedLink === 'code' ? <CheckCircle className="w-4 h-4 mr-2" /> : <Copy className="w-4 h-4 mr-2" />}
                  {copiedLink === 'code' ? t('dashboard.affiliates.copied') : t('dashboard.affiliates.copy')}
                </Button>
              </div>
            </div>

            {/* Registration Link */}
            <div className="p-3 sm:p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg sm:rounded-xl border border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 sm:w-8 sm:h-8 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                  <UserPlus className="w-3 h-3 sm:w-4 sm:h-4 text-blue-600 dark:text-blue-400" />
                </div>
                <span className="font-medium text-sm sm:text-base text-gray-900 dark:text-white">{t('dashboard.affiliates.link_register') || "Lien d'inscription"}</span>
              </div>
              <div className="flex gap-2">
                <div className="flex-1 bg-white dark:bg-gray-900 rounded-lg p-2 sm:p-2.5 font-mono text-[10px] sm:text-xs text-gray-600 dark:text-gray-400 truncate border border-gray-200 dark:border-gray-700 overflow-hidden">
                  {referralLinks.register}
                </div>
                <Button 
                  onClick={() => copyToClipboard(referralLinks.register, 'register')}
                  size="sm"
                  variant="outline"
                  className={`rounded-lg flex-shrink-0 px-2 sm:px-3 ${copiedLink === 'register' ? 'bg-green-100 border-green-500 text-green-700' : ''}`}
                >
                  {copiedLink === 'register' ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
            </div>

            {/* Homepage Link */}
            <div className="p-3 sm:p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg sm:rounded-xl border border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 sm:w-8 sm:h-8 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center flex-shrink-0">
                  <Zap className="w-3 h-3 sm:w-4 sm:h-4 text-purple-600 dark:text-purple-400" />
                </div>
                <span className="font-medium text-sm sm:text-base text-gray-900 dark:text-white">{t('dashboard.affiliates.link_home') || "Lien page d'accueil"}</span>
              </div>
              <div className="flex gap-2">
                <div className="flex-1 bg-white dark:bg-gray-900 rounded-lg p-2 sm:p-2.5 font-mono text-[10px] sm:text-xs text-gray-600 dark:text-gray-400 truncate border border-gray-200 dark:border-gray-700 overflow-hidden">
                  {referralLinks.home}
                </div>
                <Button 
                  onClick={() => copyToClipboard(referralLinks.home, 'home')}
                  size="sm"
                  variant="outline"
                  className={`rounded-lg flex-shrink-0 px-2 sm:px-3 ${copiedLink === 'home' ? 'bg-green-100 border-green-500 text-green-700' : ''}`}
                >
                  {copiedLink === 'home' ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
            </div>

            {/* Contests Link */}
            <div className="p-3 sm:p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg sm:rounded-xl border border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 sm:w-8 sm:h-8 rounded-lg bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center flex-shrink-0">
                  <Users className="w-3 h-3 sm:w-4 sm:h-4 text-orange-600 dark:text-orange-400" />
                </div>
                <span className="font-medium text-sm sm:text-base text-gray-900 dark:text-white">{t('dashboard.affiliates.link_contestants') || 'Lien page concours'}</span>
              </div>
              <div className="flex gap-2">
                <div className="flex-1 bg-white dark:bg-gray-900 rounded-lg p-2 sm:p-2.5 font-mono text-[10px] sm:text-xs text-gray-600 dark:text-gray-400 truncate border border-gray-200 dark:border-gray-700 overflow-hidden">
                  {referralLinks.contestants}
                </div>
                <Button 
                  onClick={() => copyToClipboard(referralLinks.contestants, 'contestants')}
                  size="sm"
                  variant="outline"
                  className={`rounded-lg flex-shrink-0 px-2 sm:px-3 ${copiedLink === 'contestants' ? 'bg-green-100 border-green-500 text-green-700' : ''}`}
                >
                  {copiedLink === 'contestants' ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Dialog pour les niveaux de commission */}
      <Dialog open={showCommissionsDialog} onOpenChange={setShowCommissionsDialog}>
        <DialogContent className="max-w-[95vw] sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base sm:text-lg">
              <Award className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-500" />
              {t('dashboard.affiliates.commission_tiers')}
            </DialogTitle>
            <DialogDescription className="text-xs sm:text-sm">
              {t('dashboard.affiliates.ten_levels') || '10 niveaux de commission'}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-3 sm:space-y-4 mt-3 sm:mt-4">
            {/* Level 1 - Direct */}
            <div className="flex items-center gap-3 sm:gap-4 p-3 sm:p-4 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg sm:rounded-xl border border-emerald-200 dark:border-emerald-700/50">
              <div className="w-10 h-10 sm:w-14 sm:h-14 rounded-full bg-emerald-500 flex items-center justify-center shadow-lg shadow-emerald-500/25 flex-shrink-0">
                <span className="text-base sm:text-xl font-bold text-white">1</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <h3 className="font-semibold text-sm sm:text-base text-gray-900 dark:text-white">{t('dashboard.affiliates.level')} 1</h3>
                    <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('dashboard.affiliates.direct_referrals')}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-2xl sm:text-3xl font-bold text-emerald-500">10%</p>
                    <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400 hidden sm:block">{t('dashboard.affiliates.direct_commission') || 'Commission directe'}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Levels 2-10 - Indirect */}
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg sm:rounded-xl p-3 sm:p-4 border border-gray-200 dark:border-gray-700">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs sm:text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('dashboard.affiliates.levels') || 'Niveaux'} 2 - 10
                  </span>
                  <span className="text-[10px] sm:text-xs bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 px-1.5 sm:px-2 py-0.5 rounded-full">
                    {t('dashboard.affiliates.indirect_commission') || 'Indirect'}
                  </span>
                </div>
                <p className="text-xl sm:text-2xl font-bold text-emerald-500">1%</p>
              </div>
              
              <div className="flex flex-wrap gap-1.5 sm:gap-2">
                {[2, 3, 4, 5, 6, 7, 8, 9, 10].map((level) => (
                  <div 
                    key={level}
                    className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center text-xs sm:text-sm font-semibold text-emerald-600 dark:text-emerald-400"
                  >
                    {level}
                  </div>
                ))}
              </div>
              
              <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400 mt-2 sm:mt-3">
                {t('dashboard.affiliates.indirect_description') || 'Gagnez 1% sur chaque niveau de votre réseau, jusqu\'au 10ème niveau.'}
              </p>
            </div>

            {/* Total potential */}
            <div className="p-3 sm:p-4 bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20 rounded-lg sm:rounded-xl border border-emerald-200 dark:border-emerald-700/50">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="font-medium text-sm sm:text-base text-gray-900 dark:text-white">{t('dashboard.affiliates.total_potential') || 'Total potentiel'}</p>
                  <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">{t('dashboard.affiliates.max_commission') || 'Commission maximale sur 10 niveaux'}</p>
                </div>
                <p className="text-2xl sm:text-3xl font-bold text-emerald-600 dark:text-emerald-400">19%</p>
              </div>
            </div>

            {/* Cookie tracking info */}
            <div className="flex items-center gap-2 sm:gap-3 p-2.5 sm:p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-700/50">
              <div className="w-6 h-6 sm:w-8 sm:h-8 rounded-full bg-blue-100 dark:bg-blue-800/50 flex items-center justify-center flex-shrink-0">
                <Clock className="w-3 h-3 sm:w-4 sm:h-4 text-blue-600 dark:text-blue-400" />
              </div>
              <p className="text-xs sm:text-sm text-blue-700 dark:text-blue-300">
                {t('dashboard.affiliates.cookie_tracking') || 'Tracking par cookies : 30 jours'}
              </p>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Invite Dialog */}
      <InviteDialog
        isOpen={showInviteDialog}
        onClose={() => {
          setShowInviteDialog(false)
          // Recharger les invitations après fermeture
          loadAffiliatesData()
        }}
        referralCode={referralCode}
        referralLink={referralLinks.home}
      />

      {/* Tabs */}
      <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl border border-gray-100 dark:border-gray-700 overflow-hidden">
        {/* Tab Header */}
        <div className="p-4 sm:p-6 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-700 p-1 rounded-xl">
              <button
                onClick={() => setActiveTab('affiliates')}
                className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all ${
                  activeTab === 'affiliates'
                    ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                }`}
              >
                <Users className="w-4 h-4" />
                {t('dashboard.affiliates.your_affiliates') || 'Affiliés'}
                {directAffiliates > 0 && (
                  <span className="ml-1 px-1.5 py-0.5 text-xs bg-myhigh5-primary/10 text-myhigh5-primary rounded-full">
                    {directAffiliates}
                  </span>
                )}
              </button>
              <button
                onClick={() => setActiveTab('pending')}
                className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all ${
                  activeTab === 'pending'
                    ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                }`}
              >
                <Mail className="w-4 h-4" />
                {t('dashboard.affiliates.pending_invitations') || 'En attente'}
                {invitationStats.pending > 0 && (
                  <span className="ml-1 px-1.5 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 rounded-full">
                    {invitationStats.pending}
                  </span>
                )}
              </button>
            </div>

            {activeTab === 'affiliates' && (
              <Link href="/dashboard/affiliates/list">
                <Button variant="ghost" size="sm" className="text-myhigh5-primary hover:text-myhigh5-primary/80 text-xs sm:text-sm">
                  {t('dashboard.affiliates.see_all')}
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </Link>
            )}
          </div>
        </div>
        
        {/* Tab Content - Affiliates */}
        {activeTab === 'affiliates' && (
          <>
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {affiliates.map((affiliate) => (
                <div 
                  key={affiliate.id} 
                  className="p-3 sm:p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                >
                  <div className="flex items-start sm:items-center gap-3 sm:gap-4">
                    <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-myhigh5-primary flex items-center justify-center text-white font-semibold shadow-lg shadow-myhigh5-primary/20 flex-shrink-0">
                      {affiliate.name.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-medium text-sm sm:text-base text-gray-900 dark:text-white truncate">
                          {affiliate.name}
                        </p>
                        {affiliate.identity_verified && (
                          <span className="flex items-center gap-1 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 rounded text-xs text-green-600 dark:text-green-400">
                            <CheckCircle className="w-3 h-3" />
                            <span className="hidden sm:inline">KYC</span>
                          </span>
                        )}
                        {affiliate.has_paid_kyc && !affiliate.identity_verified && (
                          <span className="flex items-center gap-1 px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded text-xs text-amber-600 dark:text-amber-400">
                            <Clock className="w-3 h-3" />
                            <span className="hidden sm:inline">{t('dashboard.affiliates.kyc_pending') || 'KYC en cours'}</span>
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-1 sm:gap-2 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                        {(affiliate.city || affiliate.country) && (
                          <>
                            <span className="truncate max-w-[120px] sm:max-w-none">{[affiliate.city, affiliate.country].filter(Boolean).join(', ')}</span>
                            <span className="hidden sm:inline">•</span>
                          </>
                        )}
                        <span className="whitespace-nowrap">
                          {new Date(affiliate.joinedAt).toLocaleDateString(localeMap[language] || 'en-US', {
                            day: 'numeric',
                            month: 'short'
                          })}
                        </span>
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      {affiliate.commissions_generated && affiliate.commissions_generated > 0 ? (
                        <>
                          <p className="text-xs sm:text-sm font-semibold text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                            +${affiliate.commissions_generated.toFixed(2)}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 hidden sm:block">
                            {t('dashboard.affiliates.commission') || 'Commission'}
                          </p>
                        </>
                      ) : (
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          {t('dashboard.affiliates.no_commission') || 'Aucune commission'}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            
            {affiliates.length === 0 && (
              <div className="p-12 text-center">
                <div className="w-16 h-16 mx-auto rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
                  <Users className="w-8 h-8 text-gray-400" />
                </div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  {t('dashboard.affiliates.no_affiliates')}
                </h3>
                <p className="text-gray-500 dark:text-gray-400 mb-4">
                  {t('dashboard.affiliates.start_inviting')}
                </p>
                <Button 
                  onClick={() => setShowInviteDialog(true)}
                  className="rounded-xl bg-myhigh5-primary hover:bg-myhigh5-primary/90"
                >
                  <UserPlus className="w-4 h-4 mr-2" />
                  {t('dashboard.affiliates.invite_friends')}
                </Button>
              </div>
            )}
          </>
        )}

        {/* Tab Content - Pending Invitations */}
        {activeTab === 'pending' && (
          <>
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {pendingInvitations.map((invitation) => (
                <div 
                  key={invitation.id} 
                  className="p-3 sm:p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                >
                  <div className="flex items-start sm:items-center gap-3 sm:gap-4">
                    <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center text-amber-600 dark:text-amber-400 font-semibold flex-shrink-0">
                      <Mail className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm sm:text-base text-gray-900 dark:text-white truncate">
                        {invitation.email}
                      </p>
                      <div className="flex flex-wrap items-center gap-1 sm:gap-2 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {t('dashboard.affiliates.sent_on') || 'Envoyé le'}{' '}
                          {new Date(invitation.sent_at).toLocaleDateString(localeMap[language] || 'en-US', {
                            day: 'numeric',
                            month: 'short',
                            year: 'numeric'
                          })}
                        </span>
                      </div>
                      {invitation.message && (
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate italic">
                          "{invitation.message}"
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="px-2 py-1 text-xs font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 rounded-lg">
                        {t('dashboard.affiliates.pending') || 'En attente'}
                      </span>
                      <button
                        onClick={() => cancelInvitation(invitation.id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        title={t('dashboard.affiliates.cancel') || 'Annuler'}
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            
            {pendingInvitations.length === 0 && (
              <div className="p-12 text-center">
                <div className="w-16 h-16 mx-auto rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
                  <Mail className="w-8 h-8 text-gray-400" />
                </div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  {t('dashboard.affiliates.no_pending') || 'Aucune invitation en attente'}
                </h3>
                <p className="text-gray-500 dark:text-gray-400 mb-4">
                  {t('dashboard.affiliates.send_invitation_desc') || 'Envoyez des invitations à vos amis pour les parrainer'}
                </p>
                <Button 
                  onClick={() => setShowInviteDialog(true)}
                  className="rounded-xl bg-myhigh5-primary hover:bg-myhigh5-primary/90"
                >
                  <Send className="w-4 h-4 mr-2" />
                  {t('dashboard.affiliates.send_invitation') || 'Envoyer une invitation'}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
