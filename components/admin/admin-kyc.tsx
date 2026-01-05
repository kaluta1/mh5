'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { CheckCircle, XCircle, Eye, AlertCircle } from 'lucide-react'
import api from '@/lib/api'

interface KYCVerification {
  id: number
  user_id: number
  status: string
  verified_first_name?: string
  verified_last_name?: string
  verified_date_of_birth?: string
  verified_nationality?: string
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

export default function AdminKYC() {
  const [verifications, setVerifications] = useState<KYCVerification[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('pending')
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    fetchVerifications()
  }, [filter])

  const fetchVerifications = async () => {
    try {
      setLoading(true)
      const response = await api.get(`/api/v1/admin/kyc?status=${filter}`)
      setVerifications(response.data)
    } catch (error) {
      console.error('Erreur lors du chargement des KYC:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleApprove = async (id: number) => {
    try {
      await api.put(`/api/v1/admin/kyc/${id}/approve`)
      fetchVerifications()
    } catch (error) {
      console.error('Erreur lors de l\'approbation:', error)
    }
  }

  const handleReject = async (id: number, reason: string) => {
    try {
      await api.put(`/api/v1/admin/kyc/${id}/reject`, { reason })
      fetchVerifications()
    } catch (error) {
      console.error('Erreur lors du rejet:', error)
    }
  }

  const filteredVerifications = verifications.filter((v) =>
    v.user?.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
    v.user?.full_name?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { bg: string; text: string; label: string }> = {
      pending: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'En attente' },
      in_progress: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'En cours' },
      approved: { bg: 'bg-green-100', text: 'text-green-800', label: 'Approuvé' },
      rejected: { bg: 'bg-red-100', text: 'text-red-800', label: 'Rejeté' },
      requires_review: { bg: 'bg-orange-100', text: 'text-orange-800', label: 'Révision requise' }
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

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center gap-4">
        <div className="flex-1">
          <Input
            placeholder="Rechercher par email ou nom..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <Button
            variant={filter === 'pending' ? 'default' : 'outline'}
            onClick={() => setFilter('pending')}
          >
            En attente
          </Button>
          <Button
            variant={filter === 'approved' ? 'default' : 'outline'}
            onClick={() => setFilter('approved')}
          >
            Approuvés
          </Button>
          <Button
            variant={filter === 'rejected' ? 'default' : 'outline'}
            onClick={() => setFilter('rejected')}
          >
            Rejetés
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
                Aucune vérification KYC trouvée
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
                          <p className="text-xs text-gray-500 uppercase tracking-wide">Vérifications</p>
                          <div className="flex gap-2 mt-1">
                            <div className={`flex items-center gap-1 text-sm ${verification.identity_verified ? 'text-green-600' : 'text-gray-400'}`}>
                              <CheckCircle className="h-4 w-4" />
                              Identité
                            </div>
                            <div className={`flex items-center gap-1 text-sm ${verification.document_verified ? 'text-green-600' : 'text-gray-400'}`}>
                              <CheckCircle className="h-4 w-4" />
                              Document
                            </div>
                          </div>
                          <div className="flex gap-2 mt-1">
                            <div className={`flex items-center gap-1 text-sm ${verification.address_verified ? 'text-green-600' : 'text-gray-400'}`}>
                              <CheckCircle className="h-4 w-4" />
                              Adresse
                            </div>
                            <div className={`flex items-center gap-1 text-sm ${verification.face_verified ? 'text-green-600' : 'text-gray-400'}`}>
                              <CheckCircle className="h-4 w-4" />
                              Visage
                            </div>
                          </div>
                        </div>

                        <div>
                          <p className="text-xs text-gray-500 uppercase tracking-wide">Score de confiance</p>
                          <div className="mt-1 space-y-1">
                            {verification.identity_confidence_score && (
                              <p className="text-sm">Identité: {verification.identity_confidence_score}%</p>
                            )}
                            {verification.document_confidence_score && (
                              <p className="text-sm">Document: {verification.document_confidence_score}%</p>
                            )}
                            {verification.face_match_score && (
                              <p className="text-sm">Visage: {verification.face_match_score}%</p>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="mt-3 flex gap-2">
                        {getStatusBadge(verification.status)}
                        <span className="text-xs text-gray-500">
                          Soumis le {new Date(verification.submitted_at).toLocaleDateString('fr-FR')}
                        </span>
                      </div>

                      {verification.rejection_reason && (
                        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded flex gap-2">
                          <AlertCircle className="h-4 w-4 text-red-600 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-sm font-medium text-red-800">Raison du rejet</p>
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
                      >
                        <Eye className="h-4 w-4" />
                        Détails
                      </Button>
                      {verification.status === 'pending' && (
                        <>
                          <Button
                            size="sm"
                            className="gap-1 bg-green-600 hover:bg-green-700"
                            onClick={() => handleApprove(verification.id)}
                          >
                            <CheckCircle className="h-4 w-4" />
                            Approuver
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            className="gap-1"
                            onClick={() => handleReject(verification.id, 'Rejeté par l\'administrateur')}
                          >
                            <XCircle className="h-4 w-4" />
                            Rejeter
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
    </div>
  )
}
