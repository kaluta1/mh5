'use client'

import { useLanguage } from '@/contexts/language-context'
import { Flag, Search, User, Calendar, CheckCircle2, Clock, XCircle, Eye } from 'lucide-react'
import { useState, useEffect } from 'react'
import api from '@/lib/api'
import { cacheService } from '@/lib/cache-service'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/toast'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface Report {
  id: number
  reason: string
  description: string | null
  status: string
  created_at: string
  reviewed_at: string | null
  reviewed_by: number | null
  moderator_notes: string | null
  contestant: {
    id: number
    title: string | null
    description: string | null
    verification_status: string
  } | null
  author: {
    id: number
    username: string | null
    full_name: string | null
    email: string
    avatar_url: string | null
    city: string | null
    country: string | null
    is_verified: boolean
  } | null
  reporter: {
    id: number
    username: string | null
    full_name: string | null
    email: string
    avatar_url: string | null
  } | null
  contest: {
    id: number
    name: string
  } | null
}

export default function ReportsPage() {
  const { t, language } = useLanguage()
  const { addToast } = useToast()


  const [reports, setReports] = useState<Report[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [selectedReport, setSelectedReport] = useState<Report | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  useEffect(() => {
    fetchReports()
  }, [statusFilter])

  const fetchReports = async () => {
    try {
      setLoading(true)
      const endpoint = '/api/v1/admin/reports'
      const params: any = {}

      if (statusFilter !== 'all') {
        params.status = statusFilter
      }

      // Vérifier le cache
      const cachedData = cacheService.get<Report[]>(endpoint, params)
      if (cachedData) {
        setReports(cachedData)
        setLoading(false)
        return
      }

      // Si pas de cache, faire l'appel API
      const urlParams = new URLSearchParams()
      if (statusFilter !== 'all') {
        urlParams.append('status', statusFilter)
      }
      const response = await api.get(`${endpoint}?${urlParams.toString()}`)
      const data = response.data || []
      setReports(data)

      // Mettre en cache (TTL de 5 minutes)
      cacheService.set(endpoint, data, params, 5 * 60 * 1000)
    } catch (error: any) {
      console.error('Erreur lors du chargement des reports:', error)
      addToast(error.response?.data?.detail || t('admin.reports.load_error') || 'Error loading reports', 'error')
    } finally {
      setLoading(false)
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-400"><Clock className="h-3 w-3 mr-1" />{t('admin.reports.pending') || 'Pending'}</Badge>
      case 'reviewed':
        return <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-400"><Eye className="h-3 w-3 mr-1" />{t('admin.reports.reviewed') || 'Reviewed'}</Badge>
      case 'resolved':
        return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-400"><CheckCircle2 className="h-3 w-3 mr-1" />{t('admin.reports.resolved') || 'Resolved'}</Badge>
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  const getVerificationStatusLabel = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'pending':
        return t('admin.reports.verification_status_pending') || 'Pending'
      case 'approved':
      case 'verified':
        return t('admin.reports.verification_status_approved') || 'Approved'
      case 'rejected':
        return t('admin.reports.verification_status_rejected') || 'Rejected'
      default:
        return status
    }
  }

  const getReasonLabel = (reason: string) => {
    switch (reason?.toLowerCase()) {
      case 'spam':
        return t('admin.reports.reason_spam') || t('contestants.report_contestant.reasons.spam') || 'Spam'
      case 'inappropriate':
        return t('admin.reports.reason_inappropriate') || t('contestants.report_contestant.reasons.inappropriate') || 'Inappropriate content'
      case 'harassment':
        return t('admin.reports.reason_harassment') || t('contestants.report_contestant.reasons.harassment') || 'Harassment'
      case 'fake':
        return t('admin.reports.reason_fake') || t('contestants.report_contestant.reasons.fake') || 'Fake account'
      case 'copyright':
        return t('admin.reports.reason_copyright') || t('contestants.report_contestant.reasons.copyright') || 'Copyright violation'
      case 'other':
        return t('admin.reports.reason_other') || t('contestants.report_contestant.reasons.other') || 'Other'
      default:
        return reason
    }
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return ''
    try {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString // Si la date est invalide, retourner la chaîne originale

      // Déterminer la locale basée sur la langue actuelle
      const languageMap: Record<string, string> = {
        'fr': 'fr-FR',
        'en': 'en-US',
        'es': 'es-ES',
        'de': 'de-DE'
      }
      // S'assurer que language est défini et valide
      const currentLanguage = language && typeof language === 'string' ? language : 'fr'
      const locale = languageMap[currentLanguage] || 'en-US'

      return date.toLocaleDateString(locale, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch (error) {
      console.error('Error formatting date:', error)
      return dateString
    }
  }

  const filteredReports = reports.filter((report) => {
    const matchesSearch =
      report.reason.toLowerCase().includes(searchTerm.toLowerCase()) ||
      report.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      report.author?.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      report.author?.username?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      report.reporter?.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      report.reporter?.username?.toLowerCase().includes(searchTerm.toLowerCase())
    return matchesSearch
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex items-center gap-3">
          <Flag className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
          <div>
            <h1 className="text-4xl font-bold text-white dark:text-white">
              {t('admin.reports.title') || 'Report Management'}
            </h1>
            <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium mt-1">
              {t('admin.reports.description') || 'Manage content reports'}
            </p>
          </div>
        </div>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder={t('admin.reports.search_placeholder') || 'Search for a report...'}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant={statusFilter === 'all' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('all')}
              >
                {t('admin.reports.all') || 'All'}
              </Button>
              <Button
                variant={statusFilter === 'pending' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('pending')}
              >
                {t('admin.reports.pending') || 'Pending'}
              </Button>
              <Button
                variant={statusFilter === 'reviewed' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('reviewed')}
              >
                {t('admin.reports.reviewed') || 'Reviewed'}
              </Button>
              <Button
                variant={statusFilter === 'resolved' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('resolved')}
              >
                {t('admin.reports.resolved') || 'Resolved'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Reports List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-myhigh5-primary"></div>
        </div>
      ) : filteredReports.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Flag className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">
              {searchTerm ? (t('admin.reports.no_reports_found') || 'No reports found') : (t('admin.reports.no_reports') || 'No reports yet')}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredReports.map((report) => (
            <Card key={report.id} className="hover:shadow-lg transition-shadow">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <CardTitle className="text-lg">{t('admin.reports.report_number') || 'Report #'}{report.id}</CardTitle>
                      {getStatusBadge(report.status)}
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      <span className="font-semibold">{t('admin.reports.reason') || 'Reason'}:</span> {getReasonLabel(report.reason)}
                    </p>
                    {report.description && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {report.description}
                      </p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSelectedReport(report)
                      setIsDialogOpen(true)
                    }}
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    {t('admin.reports.details') || 'Details'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Contestant */}
                  {report.contestant && (
                    <div className="space-y-2">
                      <h4 className="font-semibold text-sm text-gray-700 dark:text-gray-300">{t('admin.reports.reported_contestant') || 'Reported Contestant'}</h4>
                      <div className="text-sm">
                        <p className="font-medium">{report.contestant.title || (t('admin.reports.no_title') || 'No title')}</p>
                        <p className="text-gray-500 dark:text-gray-400 text-xs mt-1">
                          {t('admin.reports.status') || 'Status'}: {getVerificationStatusLabel(report.contestant.verification_status)}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Auteur */}
                  {report.author && (
                    <div className="space-y-2">
                      <h4 className="font-semibold text-sm text-gray-700 dark:text-gray-300">{t('admin.reports.contestant_author') || 'Contestant Author'}</h4>
                      <div className="flex items-center gap-2">
                        <Avatar className="h-8 w-8">
                          <AvatarImage src={report.author.avatar_url || undefined} />
                          <AvatarFallback>
                            {report.author.full_name?.[0] || report.author.username?.[0] || 'U'}
                          </AvatarFallback>
                        </Avatar>
                        <div className="text-sm">
                          <p className="font-medium">{report.author.full_name || report.author.username}</p>
                          <p className="text-gray-500 dark:text-gray-400 text-xs">
                            {report.author.city && report.author.country
                              ? `${report.author.city}, ${report.author.country}`
                              : report.author.email}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Reporter */}
                  {report.reporter && (
                    <div className="space-y-2">
                      <h4 className="font-semibold text-sm text-gray-700 dark:text-gray-300">{t('admin.reports.reporter') || 'Reporter'}</h4>
                      <div className="flex items-center gap-2">
                        <Avatar className="h-8 w-8">
                          <AvatarImage src={report.reporter.avatar_url || undefined} />
                          <AvatarFallback>
                            {report.reporter.full_name?.[0] || report.reporter.username?.[0] || 'U'}
                          </AvatarFallback>
                        </Avatar>
                        <div className="text-sm">
                          <p className="font-medium">{report.reporter.full_name || report.reporter.username}</p>
                          <p className="text-gray-500 dark:text-gray-400 text-xs">
                            {report.reporter.email}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                    <div className="flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      <span>{t('admin.reports.created_at') || 'Created on'} {formatDate(report.created_at)}</span>
                    </div>
                    {report.reviewed_at && (
                      <div className="flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" />
                        <span>{t('admin.reports.reviewed_at') || 'Reviewed on'} {formatDate(report.reviewed_at)}</span>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialog pour les détails */}
      {selectedReport && (
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('admin.reports.report_details') || 'Report Details'} #{selectedReport.id}</DialogTitle>
              <DialogDescription>
                {t('admin.reports.report_details_description') || 'Complete information about the report'}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <h4 className="font-semibold mb-2">{t('admin.reports.reason_label') || 'Report Reason'}</h4>
                <p className="text-sm">{getReasonLabel(selectedReport.reason)}</p>
              </div>

              {selectedReport.description && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.reports.description_label') || 'Description'}</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedReport.description}</p>
                </div>
              )}

              {selectedReport.contestant && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.reports.reported_contestant') || 'Reported Contestant'}</h4>
                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg">
                    <p className="text-sm font-medium">{selectedReport.contestant.title || (t('admin.reports.no_title') || 'No title')}</p>
                    {selectedReport.contestant.description && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {selectedReport.contestant.description}
                      </p>
                    )}
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                      {t('admin.reports.verification_status') || 'Verification Status'}: {getVerificationStatusLabel(selectedReport.contestant.verification_status)}
                    </p>
                  </div>
                </div>
              )}

              {selectedReport.author && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.reports.contestant_author') || 'Contestant Author'}</h4>
                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Avatar>
                        <AvatarImage src={selectedReport.author.avatar_url || undefined} />
                        <AvatarFallback>
                          {selectedReport.author.full_name?.[0] || selectedReport.author.username?.[0] || 'U'}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-medium">{selectedReport.author.full_name || selectedReport.author.username}</p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{selectedReport.author.email}</p>
                        {selectedReport.author.city && selectedReport.author.country && (
                          <p className="text-sm text-gray-600 dark:text-gray-400">
                            {selectedReport.author.city}, {selectedReport.author.country}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {selectedReport.reporter && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.reports.reporter') || 'Reporter'}</h4>
                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Avatar>
                        <AvatarImage src={selectedReport.reporter.avatar_url || undefined} />
                        <AvatarFallback>
                          {selectedReport.reporter.full_name?.[0] || selectedReport.reporter.username?.[0] || 'U'}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-medium">{selectedReport.reporter.full_name || selectedReport.reporter.username}</p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{selectedReport.reporter.email}</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {selectedReport.contest && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.reports.contest') || 'Contest'}</h4>
                  <p className="text-sm">{selectedReport.contest.name}</p>
                </div>
              )}

              {selectedReport.moderator_notes && (
                <div>
                  <h4 className="font-semibold mb-2">{t('admin.reports.moderator_notes') || 'Moderator Notes'}</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedReport.moderator_notes}</p>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
