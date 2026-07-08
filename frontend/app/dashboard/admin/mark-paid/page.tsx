'use client'

import { useLanguage } from '@/contexts/language-context'
import { useState } from 'react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/toast'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Search,
  BadgeCheck,
  Loader2,
  CheckCircle2,
  ShieldCheck,
  CreditCard,
} from 'lucide-react'

interface AdminUser {
  id: number
  email: string
  username: string | null
  full_name: string | null
  first_name: string | null
  last_name: string | null
  avatar_url: string | null
  identity_verified?: boolean
  kyc_status?: string
}

interface PaymentStatus {
  user_id: number
  available_credits: Record<string, number>
  identity_verified: boolean
}

const PRODUCTS: { code: string; labelKey: string; fallback: string }[] = [
  { code: 'kyc', labelKey: 'admin.mark_paid.product_kyc', fallback: 'KYC Verification' },
  { code: 'mfm_membership', labelKey: 'admin.mark_paid.product_mfm', fallback: 'Founding Member (MFM)' },
  { code: 'annual_membership', labelKey: 'admin.mark_paid.product_annual', fallback: 'Annual Membership' },
]

export default function MarkPaidPage() {
  const { t } = useLanguage()
  const { addToast } = useToast()

  const [searchTerm, setSearchTerm] = useState('')
  const [loading, setLoading] = useState(false)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [paymentStatus, setPaymentStatus] = useState<PaymentStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [product, setProduct] = useState('kyc')
  const [notes, setNotes] = useState('')
  const [granting, setGranting] = useState(false)

  const handleSearch = async () => {
    const term = searchTerm.trim().toLowerCase()
    if (!term) return
    try {
      setLoading(true)
      const response = await api.get('/api/v1/admin/users')
      const all: AdminUser[] = response.data || []
      const filtered = all.filter((u) =>
        [u.email, u.username, u.full_name, u.first_name, u.last_name]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(term))
      )
      setUsers(filtered.slice(0, 25))
      if (filtered.length === 0) {
        addToast(t('admin.mark_paid.no_users') || 'No users found', 'error')
      }
    } catch (error: any) {
      addToast(error.response?.data?.detail || t('admin.mark_paid.search_error') || 'Search failed', 'error')
    } finally {
      setLoading(false)
    }
  }

  const selectUser = async (user: AdminUser) => {
    setSelectedUser(user)
    setPaymentStatus(null)
    try {
      setStatusLoading(true)
      const response = await api.get(`/api/v1/admin/users/${user.id}/payment-status`)
      setPaymentStatus(response.data)
    } catch (error: any) {
      addToast(error.response?.data?.detail || t('admin.mark_paid.status_error') || 'Failed to load payment status', 'error')
    } finally {
      setStatusLoading(false)
    }
  }

  const grantPayment = async (verifyIdentity: boolean = false) => {
    if (!selectedUser) return
    try {
      setGranting(true)
      const response = await api.post(`/api/v1/admin/users/${selectedUser.id}/grant-payment`, {
        product_code: product,
        notes: notes.trim() || undefined,
        verify_identity: verifyIdentity,
      })
      const result = response.data
      if (result.status === 'already_paid') {
        addToast(t('admin.mark_paid.already_paid') || 'User already has a valid credit for this product', 'success')
      } else {
        addToast(t('admin.mark_paid.granted') || 'User marked as paid successfully', 'success')
      }
      if (verifyIdentity && result.identity_verified) {
        addToast(t('admin.mark_paid.identity_verified_toast') || 'Identity marked as verified', 'success')
      }
      setPaymentStatus((prev) =>
        prev
          ? {
              ...prev,
              available_credits: result.available_credits,
              identity_verified: result.identity_verified ?? prev.identity_verified,
            }
          : prev
      )
      setNotes('')
    } catch (error: any) {
      addToast(error.response?.data?.detail || t('admin.mark_paid.grant_error') || 'Failed to mark as paid', 'error')
    } finally {
      setGranting(false)
    }
  }

  const displayName = (u: AdminUser) => u.full_name || u.username || u.email

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary rounded-xl p-8 border border-myhigh5-primary/30 shadow-lg">
        <div className="flex items-center gap-3">
          <BadgeCheck className="h-8 w-8 text-white" />
          <div>
            <h1 className="text-3xl font-bold text-white">
              {t('admin.mark_paid.title') || 'Mark User as Paid'}
            </h1>
            <p className="text-white/90 font-medium mt-1">
              {t('admin.mark_paid.description') ||
                'Search a user and grant a paid service credit so they can continue to the next step (e.g. KYC verification) without paying again.'}
            </p>
          </div>
        </div>
      </div>

      {/* Search */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder={t('admin.mark_paid.search_placeholder') || 'Search by email, username, or name...'}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSearch()
                }}
                className="pl-10"
              />
            </div>
            <Button onClick={handleSearch} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : (t('admin.mark_paid.search') || 'Search')}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Results */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t('admin.mark_paid.results') || 'Search results'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {users.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 py-6 text-center">
                {t('admin.mark_paid.no_results') || 'Search for a user to begin.'}
              </p>
            ) : (
              users.map((u) => (
                <button
                  key={u.id}
                  onClick={() => selectUser(u)}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-colors ${
                    selectedUser?.id === u.id
                      ? 'border-myhigh5-primary bg-myhigh5-primary/5'
                      : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800'
                  }`}
                >
                  <Avatar className="h-9 w-9">
                    <AvatarImage src={u.avatar_url || undefined} />
                    <AvatarFallback>{displayName(u)[0]?.toUpperCase() || 'U'}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium truncate">{displayName(u)}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{u.email}</p>
                  </div>
                  {(u.identity_verified || u.kyc_status === 'verified') && (
                    <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                      <ShieldCheck className="h-3 w-3 mr-1" />
                      {t('admin.mark_paid.kyc_verified') || 'KYC'}
                    </Badge>
                  )}
                </button>
              ))
            )}
          </CardContent>
        </Card>

        {/* Grant panel */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t('admin.mark_paid.grant_title') || 'Grant payment credit'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedUser ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 py-6 text-center">
                {t('admin.mark_paid.select_user') || 'Select a user from the results.'}
              </p>
            ) : (
              <>
                <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                  <Avatar className="h-10 w-10">
                    <AvatarImage src={selectedUser.avatar_url || undefined} />
                    <AvatarFallback>{displayName(selectedUser)[0]?.toUpperCase() || 'U'}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <p className="font-medium truncate">{displayName(selectedUser)}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{selectedUser.email}</p>
                  </div>
                </div>

                {/* Current credits */}
                <div>
                  <p className="text-sm font-semibold mb-2">
                    {t('admin.mark_paid.current_credits') || 'Available credits'}
                  </p>
                  {statusLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
                  ) : paymentStatus ? (
                    <div className="flex flex-wrap gap-2">
                      {PRODUCTS.map((p) => {
                        const count = paymentStatus.available_credits?.[p.code] ?? 0
                        return (
                          <Badge
                            key={p.code}
                            variant="outline"
                            className={
                              count > 0
                                ? 'bg-green-50 text-green-700 border-green-200'
                                : 'bg-gray-50 text-gray-600 border-gray-200'
                            }
                          >
                            {count > 0 && <CheckCircle2 className="h-3 w-3 mr-1" />}
                            {(t(p.labelKey) || p.fallback)}: {count}
                          </Badge>
                        )
                      })}
                      <Badge
                        variant="outline"
                        className={
                          paymentStatus.identity_verified
                            ? 'bg-green-50 text-green-700 border-green-200'
                            : 'bg-gray-50 text-gray-600 border-gray-200'
                        }
                      >
                        <ShieldCheck className="h-3 w-3 mr-1" />
                        {t('admin.mark_paid.identity') || 'Identity'}:{' '}
                        {paymentStatus.identity_verified
                          ? (t('admin.mark_paid.verified') || 'Verified')
                          : (t('admin.mark_paid.not_verified') || 'Not verified')}
                      </Badge>
                    </div>
                  ) : null}
                </div>

                {/* Product select */}
                <div>
                  <label className="text-sm font-semibold mb-2 block">
                    {t('admin.mark_paid.product') || 'Service to grant'}
                  </label>
                  <select
                    value={product}
                    onChange={(e) => setProduct(e.target.value)}
                    className="block w-full pl-3 pr-10 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-myhigh5-primary focus:border-myhigh5-primary dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  >
                    {PRODUCTS.map((p) => (
                      <option key={p.code} value={p.code}>
                        {t(p.labelKey) || p.fallback}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Notes */}
                <div>
                  <label className="text-sm font-semibold mb-2 block">
                    {t('admin.mark_paid.notes') || 'Notes (optional)'}
                  </label>
                  <Input
                    placeholder={t('admin.mark_paid.notes_placeholder') || 'e.g. Paid via crypto, callback failed'}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Button onClick={() => grantPayment(false)} disabled={granting} className="w-full">
                    {granting ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        {t('admin.mark_paid.granting') || 'Processing...'}
                      </>
                    ) : (
                      <>
                        <CreditCard className="h-4 w-4 mr-2" />
                        {t('admin.mark_paid.grant_button') || 'Mark as paid'}
                      </>
                    )}
                  </Button>

                  {product === 'kyc' && (
                    <Button
                      onClick={() => grantPayment(true)}
                      disabled={granting}
                      variant="outline"
                      className="w-full"
                    >
                      <ShieldCheck className="h-4 w-4 mr-2" />
                      {t('admin.mark_paid.grant_and_verify_button') || 'Mark as paid + Verify identity'}
                    </Button>
                  )}
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {product === 'kyc'
                      ? (t('admin.mark_paid.verify_hint') ||
                        'Verify identity also marks KYC as approved (skips the verification step entirely).')
                      : (t('admin.mark_paid.paid_hint') ||
                        'Grants the paid credit so the user can continue without paying again.')}
                  </p>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
