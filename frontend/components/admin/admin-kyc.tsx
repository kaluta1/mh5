'use client'

import { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { CheckCircle, XCircle, Eye, AlertCircle, FileText, ExternalLink } from 'lucide-react'
import api from '@/lib/api'
import { API_URL } from '@/lib/config'

interface KYCVerification {
  id: number
  user_id: number
  status: string
  verified_first_name?: string
  verified_last_name?: string
  verified_date_of_birth?: string
  verified_nationality?: string
  verified_address?: string
  identity_verified: boolean
  address_verified: boolean
  document_verified: boolean
  face_verified: boolean
  identity_confidence_score?: number
  document_confidence_score?: number
  face_match_score?: number
  rejection_reason?: string
  submitted_at: string
  processed_at?: string
  user?: {
    id: number
    email: string
    full_name?: string
    avatar_url?: string
  }
}

interface KYCDocumentDetail {
  id: number
  verification_id: number
  document_type: string
  front_image_url?: string | null
  back_image_url?: string | null
  front_public_url?: string | null
  back_public_url?: string | null
  verification_notes?: string | null
  is_verified: boolean
  uploaded_at: string
  verified_at?: string | null
}

interface KYCAdminDetail extends KYCVerification {
  documents: KYCDocumentDetail[]
  user_email?: string | null
  user_full_name?: string | null
}

const API_BASE = API_URL.replace(/\/+$/, '')

function resolveAssetUrl(url?: string | null): string {
  if (!url || !String(url).trim()) return ''
  const u = String(url).trim()
  if (u.startsWith('http://') || u.startsWith('https://')) return u
  return u.startsWith('/') ? `${API_BASE}${u}` : `${API_BASE}/${u}`
}

function isLikelyImageUrl(url: string): boolean {
  return /\.(jpe?g|png|gif|webp)(\?|$)/i.test(url)
}

function parsePoaNotes(notes?: string | null): { name?: string; address?: string } {
  if (!notes) return {}
  try {
    const j = JSON.parse(notes) as { name_on_document?: string; address_as_shown_on_document?: string }
    return {
      name: j.name_on_document,
      address: j.address_as_shown_on_document,
    }
  } catch {
    return {}
  }
}

const POA_TYPES = new Set(['utility_bill', 'address_proof', 'bank_statement'])

export default function AdminKYC() {
  const { t, language } = useLanguage()
  const [verifications, setVerifications] = useState<KYCVerification[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('pending')
  const [searchTerm, setSearchTerm] = useState('')

  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState<KYCAdminDetail | null>(null)

  useEffect(() => {
    fetchVerifications()
  }, [filter])

  const fetchVerifications = async () => {
    try {
      setLoading(true)
      const response = await api.get('/api/v1/kyc/admin/verifications', {
        params: { status_filter: filter === 'all' ? undefined : filter, limit: 200 },
      })
      setVerifications(Array.isArray(response.data) ? response.data : [])
    } catch (error) {
      console.error('Error loading KYC:', error)
      setVerifications([])
    } finally {
      setLoading(false)
    }
  }

  const openDetail = useCallback(async (verificationId: number) => {
    setDetailOpen(true)
    setDetailLoading(true)
    setDetail(null)
    try {
      const { data } = await api.get<KYCAdminDetail>(
        `/api/v1/kyc/admin/verification/${verificationId}/detail`
      )
      setDetail(data)
    } catch (e) {
      console.error('KYC detail:', e)
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  const handleApprove = async (id: number) => {
    try {
      await api.post(`/api/v1/kyc/admin/verification/${id}/approve`)
      fetchVerifications()
      if (detail?.id === id) openDetail(id)
    } catch (error) {
      console.error('Error approving:', error)
    }
  }

  const handleReject = async (id: number, reason: string) => {
    try {
      const payload = new URLSearchParams()
      payload.set('reason', reason)

      await api.post(`/api/v1/kyc/admin/verification/${id}/reject`, payload, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      })
      fetchVerifications()
      if (detail?.id === id) openDetail(id)
    } catch (error) {
      console.error('Error rejecting:', error)
    }
  }

  const filteredVerifications = (Array.isArray(verifications) ? verifications : []).filter((v) => {
    const email = v.user?.email?.toLowerCase() || ''
    const fullName = v.user?.full_name?.toLowerCase() || ''
    const query = searchTerm.toLowerCase()

    return email.includes(query) || fullName.includes(query)
  })

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { bg: string; text: string; label: string }> = {
      pending: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: t('admin.kyc.pending') || 'Pending' },
      in_progress: { bg: 'bg-blue-100', text: 'text-blue-800', label: language === 'fr' ? 'En cours' : 'In progress' },
      pending_proof_of_address: {
        bg: 'bg-teal-100',
        text: 'text-teal-900',
        label: language === 'fr' ? 'Justificatif domicile' : 'Proof of address',
      },
      approved: { bg: 'bg-green-100', text: 'text-green-800', label: t('admin.kyc.approved') || 'Approved' },
      rejected: { bg: 'bg-red-100', text: 'text-red-800', label: t('admin.kyc.rejected') || 'Rejected' },
      requires_review: { bg: 'bg-orange-100', text: 'text-orange-800', label: language === 'fr' ? 'Révision requise' : 'Requires review' },
      expired: { bg: 'bg-gray-100', text: 'text-gray-800', label: 'Expired' },
    }
    const badge = badges[status] || badges.pending
    return <span className={`px-2 py-1 rounded text-sm font-medium ${badge.bg} ${badge.text}`}>{badge.label}</span>
  }

  const getVerificationScore = (v: KYCVerification) => {
    let score = 0
    if (v.identity_verified) score += 25
    if (v.address_verified) score += 25
    if (v.document_verified) score += 25
    if (v.face_verified) score += 25
    return score
  }

  const canModerate = (status: string) =>
    ['pending', 'in_progress', 'pending_proof_of_address', 'requires_review'].includes(status)

  const poaDocuments = (detail?.documents || []).filter((d) => POA_TYPES.has(d.document_type))

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-4">
        <div className="flex-1">
          <Input
            placeholder={t('admin.kyc.search_placeholder') || 'Search by email or name...'}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant={filter === 'pending' ? 'default' : 'outline'} onClick={() => setFilter('pending')}>
            {t('admin.kyc.pending') || 'Pending'}
          </Button>
          <Button
            variant={filter === 'pending_proof_of_address' ? 'default' : 'outline'}
            onClick={() => setFilter('pending_proof_of_address')}
          >
            {language === 'fr' ? 'Justif. domicile' : 'PoA pending'}
          </Button>
          <Button variant={filter === 'in_progress' ? 'default' : 'outline'} onClick={() => setFilter('in_progress')}>
            {language === 'fr' ? 'En cours' : 'In progress'}
          </Button>
          <Button variant={filter === 'approved' ? 'default' : 'outline'} onClick={() => setFilter('approved')}>
            {t('admin.kyc.approved') || 'Approved'}
          </Button>
          <Button variant={filter === 'rejected' ? 'default' : 'outline'} onClick={() => setFilter('rejected')}>
            {t('admin.kyc.rejected') || 'Rejected'}
          </Button>
          <Button variant={filter === 'all' ? 'default' : 'outline'} onClick={() => setFilter('all')}>
            {language === 'fr' ? 'Tous' : 'All'}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      ) : (
        <div className="grid gap-4">
          {filteredVerifications.length === 0 ? (
            <Card>
              <CardContent className="pt-6 text-center text-gray-500">
                {t('admin.kyc.no_kyc') || 'No KYC verifications found'}
              </CardContent>
            </Card>
          ) : (
            filteredVerifications.map((verification) => (
              <Card key={verification.id}>
                <CardContent className="pt-6">
                  <div className="flex justify-between items-start gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        {verification.user?.avatar_url && (
                          <img
                            src={verification.user.avatar_url}
                            alt={verification.user.full_name}
                            className="h-12 w-12 rounded-full object-cover"
                          />
                        )}
                        <div>
                          <h3 className="font-semibold text-lg">
                            {verification.verified_first_name} {verification.verified_last_name}
                          </h3>
                          <p className="text-sm text-gray-600">{verification.user?.email}</p>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4 mt-4">
                        <div>
                          <p className="text-xs text-gray-500 uppercase tracking-wide">
                            {language === 'fr' ? 'Vérifications' : 'Verifications'}
                          </p>
                          <div className="flex gap-2 mt-1">
                            <div
                              className={`flex items-center gap-1 text-sm ${verification.identity_verified ? 'text-green-600' : 'text-gray-400'}`}
                            >
                              <CheckCircle className="h-4 w-4" />
                              {t('admin.kyc.identity') || 'Identity'}
                            </div>
                            <div
                              className={`flex items-center gap-1 text-sm ${verification.document_verified ? 'text-green-600' : 'text-gray-400'}`}
                            >
                              <CheckCircle className="h-4 w-4" />
                              {t('admin.kyc.document') || 'Document'}
                            </div>
                          </div>
                          <div className="flex gap-2 mt-1">
                            <div
                              className={`flex items-center gap-1 text-sm ${verification.address_verified ? 'text-green-600' : 'text-gray-400'}`}
                            >
                              <CheckCircle className="h-4 w-4" />
                              {t('admin.kyc.address') || 'Address'}
                            </div>
                            <div
                              className={`flex items-center gap-1 text-sm ${verification.face_verified ? 'text-green-600' : 'text-gray-400'}`}
                            >
                              <CheckCircle className="h-4 w-4" />
                              {t('admin.kyc.face') || 'Face'}
                            </div>
                          </div>
                        </div>

                        <div>
                          <p className="text-xs text-gray-500 uppercase tracking-wide">
                            {t('admin.kyc.verification_score') || 'Confidence Score'}
                          </p>
                          <div className="mt-1 space-y-1">
                            {verification.identity_confidence_score != null && (
                              <p className="text-sm">
                                {t('admin.kyc.identity') || 'Identity'}: {verification.identity_confidence_score}%
                              </p>
                            )}
                            {verification.document_confidence_score != null && (
                              <p className="text-sm">
                                {t('admin.kyc.document') || 'Document'}: {verification.document_confidence_score}%
                              </p>
                            )}
                            {verification.face_match_score != null && (
                              <p className="text-sm">
                                {t('admin.kyc.face') || 'Face'}: {verification.face_match_score}%
                              </p>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 mt-2">{getVerificationScore(verification)}%</p>
                        </div>
                      </div>

                      <div className="mt-3 flex gap-2 flex-wrap items-center">
                        {getStatusBadge(verification.status)}
                        <span className="text-xs text-gray-500">
                          {language === 'fr' ? 'Soumis le' : 'Submitted on'}{' '}
                          {new Date(verification.submitted_at).toLocaleDateString(language === 'fr' ? 'fr-FR' : 'en-US')}
                        </span>
                      </div>

                      {verification.rejection_reason && (
                        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded flex gap-2">
                          <AlertCircle className="h-4 w-4 text-red-600 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-sm font-medium text-red-800">
                              {t('admin.kyc.rejection_reason') || 'Rejection Reason'}
                            </p>
                            <p className="text-sm text-red-700">{verification.rejection_reason}</p>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1"
                        onClick={() => openDetail(verification.id)}
                      >
                        <Eye className="h-4 w-4" />
                        {t('admin.kyc.view') || 'Details'}
                      </Button>
                      {canModerate(verification.status) && (
                        <>
                          <Button
                            size="sm"
                            className="gap-1 bg-green-600 hover:bg-green-700"
                            onClick={() => handleApprove(verification.id)}
                          >
                            <CheckCircle className="h-4 w-4" />
                            {t('admin.kyc.approve') || 'Approve'}
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            className="gap-1"
                            onClick={() =>
                              handleReject(
                                verification.id,
                                language === 'fr' ? 'Rejeté par l\'administrateur' : 'Rejected by administrator'
                              )
                            }
                          >
                            <XCircle className="h-4 w-4" />
                            {t('admin.kyc.reject') || 'Reject'}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{language === 'fr' ? 'Détail KYC' : 'KYC detail'}</DialogTitle>
            <DialogDescription>
              {language === 'fr'
                ? 'Documents enregistrés, dont le justificatif de domicile après vérification.'
                : 'Stored documents, including proof of address after verification.'}
            </DialogDescription>
          </DialogHeader>

          {detailLoading && (
            <div className="flex justify-center py-8 text-sm text-gray-500">
              {language === 'fr' ? 'Chargement…' : 'Loading…'}
            </div>
          )}

          {!detailLoading && detail && (
            <div className="space-y-6 text-left">
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {detail.user_email || detail.user?.email || `User #${detail.user_id}`}
                </p>
                {(detail.user_full_name || detail.user?.full_name) && (
                  <p className="text-sm text-gray-600 dark:text-gray-400">{detail.user_full_name || detail.user?.full_name}</p>
                )}
                <div className="mt-2">{getStatusBadge(detail.status)}</div>
              </div>

              {detail.verified_address ? (
                <div className="rounded-lg border border-gray-200 dark:border-gray-600 p-3 bg-gray-50 dark:bg-gray-900/40">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                    {language === 'fr' ? 'Adresse résidentielle déclarée (verrouillée)' : 'Declared residential address'}
                  </p>
                  <p className="text-sm whitespace-pre-wrap text-gray-800 dark:text-gray-200">{detail.verified_address}</p>
                </div>
              ) : null}

              <div>
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  {language === 'fr' ? 'Justificatif de domicile' : 'Proof of address'}
                </h4>
                {poaDocuments.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    {language === 'fr'
                      ? 'Aucun document de type facture / relevé / lettre enregistré pour cette vérification.'
                      : 'No utility bill / bank statement / address letter on file for this verification.'}
                  </p>
                ) : (
                  <div className="space-y-4">
                    {poaDocuments.map((doc) => {
                      const front = resolveAssetUrl(doc.front_public_url || doc.front_image_url)
                      const back = resolveAssetUrl(doc.back_public_url || doc.back_image_url)
                      const meta = parsePoaNotes(doc.verification_notes)
                      return (
                        <div
                          key={doc.id}
                          className="rounded-lg border border-gray-200 dark:border-gray-600 p-4 space-y-3"
                        >
                          <p className="text-xs text-gray-500 uppercase">{doc.document_type.replace(/_/g, ' ')}</p>
                          {(meta.name || meta.address) && (
                            <div className="text-sm space-y-1 bg-amber-50 dark:bg-amber-950/30 p-2 rounded">
                              {meta.name && (
                                <p>
                                  <span className="font-medium">{language === 'fr' ? 'Nom saisi' : 'Name on doc'}: </span>
                                  {meta.name}
                                </p>
                              )}
                              {meta.address && (
                                <p>
                                  <span className="font-medium">{language === 'fr' ? 'Adresse saisie' : 'Address on doc'}: </span>
                                  {meta.address}
                                </p>
                              )}
                            </div>
                          )}
                          {front && (
                            <div>
                              <p className="text-xs text-gray-500 mb-1">{language === 'fr' ? 'Fichier principal' : 'Main file'}</p>
                              {isLikelyImageUrl(front) ? (
                                <a href={front} target="_blank" rel="noopener noreferrer" className="block">
                                  <img src={front} alt="PoA front" className="max-h-64 rounded border object-contain" />
                                </a>
                              ) : (
                                <a
                                  href={front}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
                                >
                                  <ExternalLink className="h-4 w-4" />
                                  PDF / {language === 'fr' ? 'Ouvrir le fichier' : 'Open file'}
                                </a>
                              )}
                            </div>
                          )}
                          {back && (
                            <div>
                              <p className="text-xs text-gray-500 mb-1">{language === 'fr' ? 'Deuxième page' : 'Second page'}</p>
                              {isLikelyImageUrl(back) ? (
                                <a href={back} target="_blank" rel="noopener noreferrer" className="block">
                                  <img src={back} alt="PoA back" className="max-h-64 rounded border object-contain" />
                                </a>
                              ) : (
                                <a
                                  href={back}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
                                >
                                  <ExternalLink className="h-4 w-4" />
                                  PDF / {language === 'fr' ? 'Ouvrir le fichier' : 'Open file'}
                                </a>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {(detail.documents || []).filter((d) => !POA_TYPES.has(d.document_type)).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                    {language === 'fr' ? 'Autres documents' : 'Other documents'}
                  </h4>
                  <ul className="text-sm text-gray-600 space-y-2">
                    {(detail.documents || [])
                      .filter((d) => !POA_TYPES.has(d.document_type))
                      .map((doc) => {
                        const front = resolveAssetUrl(doc.front_public_url || doc.front_image_url)
                        return (
                          <li key={doc.id}>
                            {doc.document_type}:{' '}
                            {front ? (
                              <a href={front} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                                {language === 'fr' ? 'Voir' : 'View'}
                              </a>
                            ) : (
                              '—'
                            )}
                          </li>
                        )
                      })}
                  </ul>
                </div>
              )}

              {canModerate(detail.status) && (
                <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-200 dark:border-gray-600">
                  <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => handleApprove(detail.id)}>
                    <CheckCircle className="h-4 w-4 mr-1" />
                    {t('admin.kyc.approve') || 'Approve'}
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() =>
                      handleReject(
                        detail.id,
                        language === 'fr' ? 'Rejeté par l\'administrateur' : 'Rejected by administrator'
                      )
                    }
                  >
                    <XCircle className="h-4 w-4 mr-1" />
                    {t('admin.kyc.reject') || 'Reject'}
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
