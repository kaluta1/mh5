'use client'

import { useState, useEffect } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Shield, Ban, CheckCircle, XCircle, Edit2, Eye, Users, Trophy, Award, MapPin, Calendar, FileCheck, MessageCircle, X, MoreVertical, Trash2, CheckSquare, Square } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import api from '@/lib/api'

interface UserDetails {
  id: number
  email: string
  full_name?: string
  first_name?: string
  last_name?: string
  username?: string
  avatar_url?: string
  is_active: boolean
  is_verified: boolean
  is_admin: boolean
  created_at: string
  date_of_birth?: string
  city?: string
  country?: string
  continent?: string
  region?: string
  kyc_status?: string
  kyc_verified_at?: string
  participations_count: number
  prizes_count: number
  max_level_reached?: string
  contestants_count: number
  contests_participated: number
  phone_number?: string
  last_login?: string
  bio?: string
  gender?: string
  contest_comments?: Array<{
    id: number
    content: string
    created_at: string
    is_hidden?: boolean
    is_deleted?: boolean
    contestant?: {
      id: number
      title: string
    }
    contest?: {
      id: number
      name: string
    }
  }>
  contests_list?: Array<{
    id: number
    title: string
  }>
  contestants_list?: Array<{
    id: number
    title: string
    verification_status: string
  }>
}

export default function AdminUsers() {
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [users, setUsers] = useState<UserDetails[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedUser, setSelectedUser] = useState<UserDetails | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const [showComments, setShowComments] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [deleteUserId, setDeleteUserId] = useState<number | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [loadingCommentId, setLoadingCommentId] = useState<number | null>(null)
  const [loadingAction, setLoadingAction] = useState<'hide' | 'delete' | null>(null)
  const [loadingDetails, setLoadingDetails] = useState(false)

  useEffect(() => {
    fetchUsers()
  }, [filter])

  const fetchUsers = async () => {
    try {
      setLoading(true)
      let url = '/api/v1/admin/users'
      if (filter === 'admins') {
        url += '?is_admin=true'
      } else if (filter === 'inactive') {
        url += '?is_active=false'
      } else if (filter === 'verified') {
        url += '?is_verified=true'
      }
      const response = await api.get(url)
      setUsers(response.data)
    } catch (error) {
      console.error('Erreur lors du chargement des utilisateurs:', error)
      addToast(t('admin.users.load_error') || 'Erreur lors du chargement des utilisateurs', 'error')
    } finally {
      setLoading(false)
    }
  }

  const fetchUserDetails = async (userId: number) => {
    try {
      const response = await api.get(`/api/v1/admin/users/${userId}`)
      console.log('User details:', response.data)
      console.log('Comments:', response.data.contest_comments)
      setSelectedUser(response.data)
      setShowDetails(true)
    } catch (error) {
      console.error('Erreur lors du chargement des détails:', error)
      addToast(t('admin.users.load_details_error') || 'Erreur lors du chargement des détails', 'error')
    }
  }

  const handleToggleAdmin = async (userId: number, currentStatus: boolean) => {
    try {
      await api.put(`/api/v1/admin/users/${userId}/role`, {
        is_admin: !currentStatus
      })
      addToast(t('admin.users.toggle_admin_success') || 'Droits admin modifiés', 'success')
      fetchUsers()
    } catch (error) {
      console.error('Erreur lors de la modification du rôle:', error)
      addToast(t('admin.users.toggle_admin_error') || 'Erreur lors de la modification du rôle', 'error')
    }
  }

  const handleToggleActive = async (userId: number, currentStatus: boolean) => {
    try {
      await api.put(`/api/v1/admin/users/${userId}/status`, {
        is_active: !currentStatus
      })
      const message = currentStatus 
        ? t('admin.users.toggle_active_success_deactivate') || 'Utilisateur désactivé'
        : t('admin.users.toggle_active_success_activate') || 'Utilisateur activé'
      addToast(message, 'success')
      fetchUsers()
    } catch (error) {
      console.error('Erreur lors de la modification du statut:', error)
      addToast(t('admin.users.toggle_active_error') || 'Erreur lors de la modification du statut', 'error')
    }
  }

  const handleDeleteClick = (userId: number) => {
    setDeleteUserId(userId)
    setShowDeleteDialog(true)
  }

  const handleConfirmDelete = async () => {
    if (!deleteUserId) return
    
    setIsDeleting(true)
    try {
      await api.delete(`/api/v1/admin/users/${deleteUserId}`)
      addToast(t('admin.users.delete_success') || 'Utilisateur supprimé avec succès', 'success')
      fetchUsers()
      setShowDeleteDialog(false)
      setDeleteUserId(null)
    } catch (error) {
      console.error('Erreur lors de la suppression:', error)
      addToast(t('admin.users.delete_error') || 'Erreur lors de la suppression', 'error')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleVerifyKYC = async (userId: number) => {
    try {
      await api.put(`/api/v1/admin/users/${userId}/kyc/verify`)
      addToast(t('admin.users.kyc_verify_success') || 'KYC vérifié avec succès', 'success')
      fetchUsers()
    } catch (error) {
      console.error('Erreur lors de la vérification KYC:', error)
      addToast(t('admin.users.kyc_verify_success') || 'Erreur lors de la vérification KYC', 'error')
    }
  }

  const handleUnverifyKYC = async (userId: number) => {
    try {
      await api.put(`/api/v1/admin/users/${userId}/kyc/unverify`)
      addToast(t('admin.users.kyc_unverify_success') || 'Vérification KYC révoquée', 'success')
      fetchUsers()
    } catch (error) {
      console.error('Erreur lors de la révocation KYC:', error)
      addToast(t('admin.users.kyc_unverify_success') || 'Erreur lors de la révocation KYC', 'error')
    }
  }

  const handleDeleteComment = async (commentId: number) => {
    try {
      setLoadingCommentId(commentId)
      setLoadingAction('delete')
      await api.delete(`/api/v1/admin/comments/${commentId}`)
      addToast(t('admin.users.comment_delete_success') || 'Commentaire supprimé', 'success')
      if (selectedUser) {
        fetchUserDetails(selectedUser.id)
      }
    } catch (error) {
      console.error('Erreur lors de la suppression:', error)
      addToast(t('admin.users.comment_delete_error') || 'Erreur lors de la suppression', 'error')
    } finally {
      setLoadingCommentId(null)
      setLoadingAction(null)
    }
  }

  const handleHideComment = async (commentId: number, isHidden: boolean) => {
    try {
      setLoadingCommentId(commentId)
      setLoadingAction('hide')
      await api.put(`/api/v1/admin/comments/${commentId}`, {
        is_hidden: !isHidden
      })
      const message = !isHidden 
        ? t('admin.users.comment_hide_success') || 'Commentaire masqué'
        : t('admin.users.comment_show_success') || 'Commentaire affiché'
      addToast(message, 'success')
      if (selectedUser) {
        fetchUserDetails(selectedUser.id)
      }
    } catch (error) {
      console.error('Erreur lors du masquage:', error)
      const message = !isHidden
        ? t('admin.users.comment_hide_error') || 'Erreur lors du masquage'
        : t('admin.users.comment_show_error') || 'Erreur lors de l\'affichage'
      addToast(message, 'error')
    } finally {
      setLoadingCommentId(null)
      setLoadingAction(null)
    }
  }

  const filteredUsers = users.filter((u) =>
    u.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
    u.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    u.username?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="space-y-6 ">
      {/* Filters and Search */}
      <div className="bg-white mt-5 dark:bg-gray-800/50 rounded-xl p-5 border border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="flex-1 w-full">
            <Input
              placeholder="Rechercher par email, nom ou pseudo..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="dark:bg-gray-700 dark:border-gray-600 dark:text-white border-gray-300 focus:border-myhigh5-primary focus:ring-myhigh5-primary"
            />
          </div>
          <div className="flex gap-3 flex-wrap">
            <Button
              variant={filter === 'all' ? 'default' : 'outline'}
              onClick={() => setFilter('all')}
              className={filter === 'all' ? 'bg-myhigh5-primary hover:bg-myhigh5-primary/90' : ''}
            >
              {t('admin.users.all') || 'Tous'}
            </Button>
            <Button
              variant={filter === 'admins' ? 'default' : 'outline'}
              onClick={() => setFilter('admins')}
              className={filter === 'admins' ? 'bg-purple-600 hover:bg-purple-700' : ''}
            >
              {t('admin.users.admins') || 'Admins'}
            </Button>
            <Button
              variant={filter === 'verified' ? 'default' : 'outline'}
              onClick={() => setFilter('verified')}
              className={filter === 'verified' ? 'bg-green-600 hover:bg-green-700' : ''}
            >
              {t('admin.users.verified') || 'Vérifiés'}
            </Button>
            <Button
              variant={filter === 'inactive' ? 'default' : 'outline'}
              onClick={() => setFilter('inactive')}
              className={filter === 'inactive' ? 'bg-red-600 hover:bg-red-700' : ''}
            >
              {t('admin.users.inactive') || 'Inactifs'}
            </Button>
          </div>
        </div>
      </div>

      {/* Users Table */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-myhigh5-primary"></div>
        </div>
      ) : filteredUsers.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center text-gray-500">
            {t('admin.users.no_users') || 'Aucun utilisateur trouvé'}
          </CardContent>
        </Card>
      ) : (
        <Card className="overflow-hidden dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-700">
                <tr>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-gray-900 dark:text-white">{t('admin.users.table_user') || 'Utilisateur'}</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-gray-900 dark:text-white">{t('admin.users.table_email') || 'Email'}</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-900 dark:text-white">{t('admin.users.table_participations') || 'Participations'}</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-900 dark:text-white">{t('admin.users.table_prizes') || 'Prix'}</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-900 dark:text-white">{t('admin.users.table_candidates') || 'Candidats'}</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-900 dark:text-white">{t('admin.users.table_contests') || 'Contests'}</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-gray-900 dark:text-white">{t('admin.users.table_status') || 'Statut'}</th>
                  <th className="px-6 py-4 text-right text-sm font-semibold text-gray-900 dark:text-white">{t('admin.users.table_actions') || 'Actions'}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {filteredUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors">
                    {/* Utilisateur */}
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        {user.avatar_url ? (
                          <img
                            src={user.avatar_url}
                            alt={user.full_name}
                            className="h-10 w-10 rounded-full object-cover border border-myhigh5-primary/30"
                          />
                        ) : (
                          <div className="h-10 w-10 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center text-white font-bold text-sm">
                            {user.full_name?.charAt(0) || user.email.charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <p className="font-semibold text-gray-900 dark:text-white text-sm">
                            {user.full_name || user.username || 'Utilisateur'}
                          </p>
                          {user.username && (
                            <p className="text-xs text-gray-500 dark:text-gray-400">@{user.username}</p>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Email */}
                    <td className="px-6 py-4">
                      <p className="text-sm text-gray-600 dark:text-gray-400">{user.email}</p>
                    </td>

                    {/* Participations */}
                    <td className="px-6 py-4 text-center">
                      <span className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-semibold text-sm">
                        {user.participations_count}
                      </span>
                    </td>

                    {/* Prix */}
                    <td className="px-6 py-4 text-center">
                      <span className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 font-semibold text-sm">
                        {user.prizes_count}
                      </span>
                    </td>

                    {/* Candidats */}
                    <td className="px-6 py-4 text-center">
                      <span className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 font-semibold text-sm">
                        {user.contestants_count}
                      </span>
                    </td>

                    {/* Contests */}
                    <td className="px-6 py-4 text-center">
                      <span className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 font-semibold text-sm">
                        {user.contests_participated}
                      </span>
                    </td>

                    {/* Statut */}
                    <td className="px-6 py-4">
                      <div className="flex gap-1.5 flex-wrap">
                        {user.is_admin && (
                          <span className="inline-flex items-center gap-1 bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300 px-2 py-1 rounded-full text-xs font-semibold">
                            <Shield className="h-3 w-3" />
                            Admin
                          </span>
                        )}
                        {user.is_verified && (
                          <span className="inline-flex items-center gap-1 bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 px-2 py-1 rounded-full text-xs font-semibold">
                            <CheckCircle className="h-3 w-3" />
                            Vérifié
                          </span>
                        )}
                        {user.kyc_status === 'verified' && (
                          <span className="inline-flex items-center gap-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 px-2 py-1 rounded-full text-xs font-semibold">
                            <FileCheck className="h-3 w-3" />
                            KYC
                          </span>
                        )}
                        {!user.is_active && (
                          <span className="inline-flex items-center gap-1 bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 px-2 py-1 rounded-full text-xs font-semibold">
                            <Ban className="h-3 w-3" />
                            Inactif
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Actions */}
                    <td className="px-6 py-4 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-8 w-8 p-0 border-gray-300 dark:border-gray-600"
                          >
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-48">
                          <DropdownMenuItem
                            onClick={() => fetchUserDetails(user.id)}
                            className="gap-2 cursor-pointer"
                          >
                            <Eye className="h-4 w-4" />
                            <span>{t('admin.users.details') || 'Voir les détails'}</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => {
                              fetchUserDetails(user.id)
                              setShowComments(true)
                            }}
                            className="gap-2 cursor-pointer"
                          >
                            <MessageCircle className="h-4 w-4" />
                            <span>{t('admin.users.view_comments') || 'Voir les commentaires'}</span>
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => handleToggleAdmin(user.id, user.is_admin)}
                            className="gap-2 cursor-pointer"
                          >
                            <Shield className="h-4 w-4" />
                            <span>{user.is_admin ? t('admin.users.remove_admin') || 'Retirer admin' : t('admin.users.make_admin') || 'Faire admin'}</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => handleToggleActive(user.id, user.is_active)}
                            className="gap-2 cursor-pointer"
                          >
                            {user.is_active ? (
                              <>
                                <Ban className="h-4 w-4" />
                                <span>{t('admin.users.deactivate') || 'Désactiver'}</span>
                              </>
                            ) : (
                              <>
                                <CheckCircle className="h-4 w-4" />
                                <span>{t('admin.users.activate') || 'Activer'}</span>
                              </>
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {user.kyc_status === 'verified' ? (
                            <DropdownMenuItem
                              onClick={() => handleUnverifyKYC(user.id)}
                              className="gap-2 cursor-pointer text-orange-600 dark:text-orange-400"
                            >
                              <Square className="h-4 w-4" />
                              <span>{t('admin.users.unverify_kyc') || 'Révoquer KYC'}</span>
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem
                              onClick={() => handleVerifyKYC(user.id)}
                              className="gap-2 cursor-pointer text-green-600 dark:text-green-400"
                            >
                              <CheckSquare className="h-4 w-4" />
                              <span>{t('admin.users.verify_kyc') || 'Vérifier KYC'}</span>
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => handleDeleteClick(user.id)}
                            className="gap-2 cursor-pointer text-red-600 dark:text-red-400 focus:bg-red-50 dark:focus:bg-red-900/20"
                          >
                            <Trash2 className="h-4 w-4" />
                            <span>{t('admin.users.delete') || 'Supprimer'}</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* User Details Dialog */}
      {showDetails && selectedUser && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto dark:bg-gray-800">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4 border-b dark:border-gray-700">
              <CardTitle className="text-xl">{t('admin.users.details') || 'Détails de l\'utilisateur'}</CardTitle>
              <button
                onClick={() => setShowDetails(false)}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                <X className="h-5 w-5" />
              </button>
            </CardHeader>
            <CardContent className="pt-6 space-y-6">
              {/* Profile Section */}
              <div className="flex items-center gap-4">
                {selectedUser.avatar_url ? (
                  <img
                    src={selectedUser.avatar_url}
                    alt={selectedUser.full_name}
                    className="h-20 w-20 rounded-full object-cover border-2 border-myhigh5-primary/30"
                  />
                ) : (
                  <div className="h-20 w-20 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center text-white font-bold text-2xl">
                    {selectedUser.full_name?.charAt(0) || selectedUser.email.charAt(0).toUpperCase()}
                  </div>
                )}
                <div>
                  <h3 className="font-bold text-lg text-gray-900 dark:text-white">
                    {selectedUser.full_name || selectedUser.username || 'Utilisateur'}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedUser.email}</p>
                  {selectedUser.username && (
                    <p className="text-sm text-gray-500 dark:text-gray-500">@{selectedUser.username}</p>
                  )}
                </div>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                  <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 mb-1">Participations</p>
                  <p className="text-lg font-bold text-gray-900 dark:text-white">{selectedUser.participations_count}</p>
                </div>
                <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-3">
                  <p className="text-xs font-semibold text-yellow-600 dark:text-yellow-400 mb-1">Prix</p>
                  <p className="text-lg font-bold text-gray-900 dark:text-white">{selectedUser.prizes_count}</p>
                </div>
                <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3">
                  <p className="text-xs font-semibold text-purple-600 dark:text-purple-400 mb-1">Candidats</p>
                  <p className="text-lg font-bold text-gray-900 dark:text-white">{selectedUser.contestants_count}</p>
                </div>
                <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
                  <p className="text-xs font-semibold text-green-600 dark:text-green-400 mb-1">Contests</p>
                  <p className="text-lg font-bold text-gray-900 dark:text-white">{selectedUser.contests_participated}</p>
                </div>
              </div>

              {/* Personal Information */}
              <div className="border-t dark:border-gray-700 pt-4">
                <h4 className="font-semibold text-gray-900 dark:text-white mb-3">{t('admin.users.personal_info') || 'Informations personnelles'}</h4>
                <div className="grid grid-cols-2 gap-4">
                  {selectedUser.date_of_birth && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">{t('admin.users.date_of_birth') || 'Date de naissance'}</p>
                      <p className="text-sm text-gray-900 dark:text-white">{new Date(selectedUser.date_of_birth).toLocaleDateString('fr-FR')}</p>
                    </div>
                  )}
                  {selectedUser.phone_number && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">{t('admin.users.phone') || 'Téléphone'}</p>
                      <p className="text-sm text-gray-900 dark:text-white">{selectedUser.phone_number}</p>
                    </div>
                  )}
                  {selectedUser.city && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">{t('admin.users.city') || 'Ville'}</p>
                      <p className="text-sm text-gray-900 dark:text-white">{selectedUser.city}</p>
                    </div>
                  )}
                  {selectedUser.country && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">{t('admin.users.country') || 'Pays'}</p>
                      <p className="text-sm text-gray-900 dark:text-white">{selectedUser.country}</p>
                    </div>
                  )}
                  {selectedUser.region && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">{t('admin.users.region') || 'Région'}</p>
                      <p className="text-sm text-gray-900 dark:text-white">{selectedUser.region}</p>
                    </div>
                  )}
                  {selectedUser.continent && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">{t('admin.users.continent') || 'Continent'}</p>
                      <p className="text-sm text-gray-900 dark:text-white">{selectedUser.continent}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Account Status */}
              <div className="border-t dark:border-gray-700 pt-4">
                <h4 className="font-semibold text-gray-900 dark:text-white mb-3">{t('admin.users.account_status') || 'Statut du compte'}</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{t('admin.users.joined') || 'Inscrit'}</p>
                    <p className="text-sm text-gray-900 dark:text-white">{new Date(selectedUser.created_at).toLocaleDateString('fr-FR')}</p>
                  </div>
                  {selectedUser.last_login && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{t('admin.users.last_login') || 'Dernière connexion'}</p>
                      <p className="text-sm text-gray-900 dark:text-white">{new Date(selectedUser.last_login).toLocaleDateString('fr-FR')}</p>
                    </div>
                  )}
                  <div>
                    <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{t('admin.users.kyc_status') || 'KYC'}</p>
                    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-semibold ${
                      selectedUser.kyc_status === 'verified'
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300'
                        : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300'
                    }`}>
                      <FileCheck className="h-3 w-3" />
                      {selectedUser.kyc_status === 'verified' ? t('admin.users.kyc_verified') || 'Vérifié' : t('admin.users.kyc_pending') || 'En attente'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Close Button */}
              <div className="flex justify-end pt-4 border-t dark:border-gray-700">
                <Button
                  variant="outline"
                  onClick={() => setShowDetails(false)}
                >
                  {t('admin.users.cancel') || 'Fermer'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Comments Dialog */}
      {showComments && selectedUser && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto dark:bg-gray-800">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4 border-b dark:border-gray-700">
              <CardTitle className="text-xl">{t('admin.users.comments') || 'Commentaires'} - {selectedUser.full_name || selectedUser.username}</CardTitle>
              <button
                onClick={() => setShowComments(false)}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                <X className="h-5 w-5" />
              </button>
            </CardHeader>
            <CardContent className="pt-6">
              {selectedUser.contest_comments && selectedUser.contest_comments.length > 0 ? (
                <div className="space-y-4">
                  {selectedUser.contest_comments.map((comment: any) => (
                    <div key={comment.id} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                      <div className="flex justify-between items-start mb-3">
                        <div className="flex-1">
                          <div className="mb-2">
                            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('admin.users.contest_label') || 'Concours'}</p>
                            <p className="text-sm font-semibold text-gray-900 dark:text-white">{comment.contest?.name || 'Concours supprimé'}</p>
                          </div>
                          <div>
                            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{t('admin.users.contestant_label') || 'Candidat'}</p>
                            <p className="text-sm font-semibold text-gray-900 dark:text-white">{comment.contestant?.title || 'Candidat supprimé'}</p>
                          </div>
                          {comment.is_hidden && (
                            <p className="text-xs text-orange-500 font-medium mt-2">Masqué</p>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap ml-4">{new Date(comment.created_at).toLocaleDateString('fr-FR')}</p>
                      </div>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-3 bg-white dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700">{comment.content}</p>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleHideComment(comment.id, comment.is_hidden)}
                          className="text-xs"
                          disabled={loadingCommentId === comment.id}
                        >
                          {loadingCommentId === comment.id && loadingAction === 'hide' ? (
                            <div className="flex items-center gap-1">
                              <div className="w-3 h-3 border-2 border-gray-400 border-t-gray-700 rounded-full animate-spin" />
                              <span>{comment.is_hidden ? t('admin.users.show_comment') || 'Afficher' : t('admin.users.hide_comment') || 'Masquer'}</span>
                            </div>
                          ) : (
                            <span>{comment.is_hidden ? t('admin.users.show_comment') || 'Afficher' : t('admin.users.hide_comment') || 'Masquer'}</span>
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleDeleteComment(comment.id)}
                          className="text-xs"
                          disabled={loadingCommentId === comment.id}
                        >
                          {loadingCommentId === comment.id && loadingAction === 'delete' ? (
                            <div className="flex items-center gap-1">
                              <div className="w-3 h-3 border-2 border-white border-t-red-700 rounded-full animate-spin" />
                              <span>{t('admin.users.delete_comment') || 'Supprimer'}</span>
                            </div>
                          ) : (
                            <span>{t('admin.users.delete_comment') || 'Supprimer'}</span>
                          )}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <MessageCircle className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500 dark:text-gray-400">{t('admin.users.no_comments') || 'Aucun commentaire'}</p>
                </div>
              )}
              <div className="flex justify-end pt-4 border-t dark:border-gray-700 mt-4">
                <Button
                  variant="outline"
                  onClick={() => setShowComments(false)}
                >
                  {t('admin.users.cancel') || 'Fermer'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        title={t('admin.users.confirm_delete_title') || "Supprimer l'utilisateur"}
        message={t('admin.users.confirm_delete_message') || "Êtes-vous sûr de vouloir supprimer cet utilisateur ? Cette action est irréversible."}
        confirmText={t('admin.users.delete') || "Supprimer"}
        cancelText={t('admin.users.cancel') || "Annuler"}
        onConfirm={handleConfirmDelete}
        isLoading={isDeleting}
        isDangerous={true}
      />
    </div>
  )
}
