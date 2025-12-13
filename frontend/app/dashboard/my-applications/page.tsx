'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { ApplicationsSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { contestService } from '@/services/contest-service'
import { AlertCircle } from 'lucide-react'
import Link from 'next/link'

interface Application {
  id: number
  contestId: number
  contestName: string
  contestLevel?: string
  title: string
  description: string
  rank?: number
  registrationDate: string
  status: string
  totalVotes?: number
  totalComments?: number
  totalLikes?: number
  coverImage?: string
}

export default function MyApplicationsPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { addToast } = useToast()
  
  const [applications, setApplications] = useState<Application[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    const loadApplications = async () => {
      if (!isAuthenticated || !user) {
        setPageLoading(false)
        return
      }

      try {
        setPageLoading(true)
        setError(null)

        // Récupérer tous les contests
        const contests = await contestService.getContests(0, 1000)
        
        const userApplications: Application[] = []

        // Pour chaque contest, récupérer les candidatures
        for (const contest of contests) {
          try {
            const contestants = await contestService.getContestantsByContest(contest.id)
            const userParticipation = contestants.find((c: any) => c.user_id === user.id)
            
            if (userParticipation) {
              // Extraire la première image comme coverImage
              let coverImage: string | undefined
              if (userParticipation.image_media_ids) {
                try {
                  const imageIds = JSON.parse(userParticipation.image_media_ids)
                  if (Array.isArray(imageIds) && imageIds.length > 0) {
                    coverImage = imageIds[0]
                  }
                } catch (e) {
                  console.error('Erreur parsing image_media_ids:', e)
                }
              }

              userApplications.push({
                id: userParticipation.id,
                contestId: Number(contest.id),
                contestName: contest.name,
                contestLevel: contest.level,
                title: userParticipation.title || '',
                description: userParticipation.description || '',
                rank: userParticipation.rank,
                registrationDate: userParticipation.registration_date,
                status: userParticipation.is_qualified ? 'approved' : 'pending',
                totalVotes: userParticipation.votes_count || 0,
                totalComments: userParticipation.comments_count || 0,
                totalLikes: userParticipation.reactions_count || 0,
                coverImage: coverImage
              })
            }
          } catch (err) {
            console.error(`Erreur lors du chargement des candidatures pour le contest ${contest.id}:`, err)
          }
        }

        setApplications(userApplications)
      } catch (err: any) {
        console.error('Erreur lors du chargement des candidatures:', err)
        setError(err?.message || 'Erreur lors du chargement des candidatures')
        addToast('Erreur lors du chargement des candidatures', 'error')
      } finally {
        setPageLoading(false)
      }
    }

    if (!isLoading) {
      loadApplications()
    }
  }, [isLoading, isAuthenticated, user, addToast])

  if (isLoading || pageLoading) {
    return <ApplicationsSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending':
        return 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800 text-yellow-900 dark:text-yellow-200'
      case 'approved':
        return 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-900 dark:text-green-200'
      case 'rejected':
        return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-900 dark:text-red-200'
      default:
        return 'bg-gray-50 dark:bg-gray-900/20 border-gray-200 dark:border-gray-800 text-gray-900 dark:text-gray-200'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'pending':
        return t('dashboard.contests.my_applications.status_pending')
      case 'approved':
        return t('dashboard.contests.my_applications.status_approved')
      case 'rejected':
        return t('dashboard.contests.my_applications.status_rejected')
      default:
        return status
    }
  }

  const canEditOrDelete = (app: Application): boolean => {
    // Vérifier si le contest est encore en phase de candidature
    // Pour l'instant, on suppose que si le statut est 'pending', on peut éditer/supprimer
    return app.status === 'pending'
  }

  const handleDeleteApplication = async (appId: number) => {
    setIsDeleting(true)
    try {
      await contestService.deleteContestant(appId)
      
      // Mettre à jour la liste locale après suppression réussie
      setApplications(applications.filter(app => app.id !== appId))
      addToast(t('common.deleted_successfully') || 'Candidature supprimée', 'success')
      setDeleteConfirmId(null)
    } catch (err: any) {
      console.error('Erreur lors de la suppression:', err)
      const errorMessage = err?.response?.data?.detail || err?.message || 'Erreur lors de la suppression'
      addToast(errorMessage, 'error')
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-10rem)] px-0 md:px-4 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            {t('dashboard.contests.my_applications.title')}
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            {t('dashboard.contests.my_applications.description')}
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <Card className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-red-900 dark:text-red-200">{error}</p>
            </div>
          </Card>
        )}

        {/* Empty State */}
        {applications.length === 0 ? (
          <Card className="text-center py-12">
            <p className="text-5xl mb-4">🏆</p>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              {t('dashboard.contests.my_applications.no_applications')}
            </p>
            <Link href="/dashboard/contests">
              <Button className="bg-myfav-primary hover:bg-myfav-primary-dark text-white">
                {t('dashboard.contests.my_applications.browse_contests')} →
              </Button>
            </Link>
          </Card>
        ) : (
          <div className="grid gap-4">
            {applications.map((app) => (
              <Card key={app.id} className="overflow-hidden hover:shadow-xl transition-shadow duration-200 border-l-4 border-l-myfav-primary">
                <div className="p-5">
                  <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                    {/* Left Content */}
                    <div className="flex-1">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                          {app.contestName}
                        </h3>
                        {app.contestLevel && (
                          <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">
                            {app.contestLevel === 'country' ? '🌍 Country' : 
                             app.contestLevel === 'continental' ? '🌎 Continental' :
                             app.contestLevel === 'regional' ? '🗺️ Regional' :
                             app.contestLevel}
                          </p>
                        )}
                      </div>
                    </div>
                    <p className="text-gray-600 dark:text-gray-400 text-sm mb-3 line-clamp-2">
                      {app.title}
                    </p>

                    {/* Status and Details */}
                    <div className="flex flex-wrap gap-2 mb-3">
                      {/* Status Badge */}
                      <Badge className={getStatusColor(app.status)}>
                        {getStatusLabel(app.status)}
                      </Badge>

                      {/* Rank */}
                      {app.rank && (
                        <Badge className="bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                          🏆 #{app.rank}
                        </Badge>
                      )}

                      {/* Registration Date */}
                      <Badge className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                        📅 {new Date(app.registrationDate).toLocaleDateString()}
                      </Badge>
                    </div>

                    {/* Stats Row */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-2.5 text-center border border-blue-100 dark:border-blue-900/30">
                        <p className="text-sm font-bold text-blue-600 dark:text-blue-400">{app.totalVotes || 0}</p>
                        <p className="text-xs text-gray-600 dark:text-gray-400">⚡ {t('dashboard.contests.received') || 'Votes'}</p>
                      </div>
                      <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-2.5 text-center border border-purple-100 dark:border-purple-900/30">
                        <p className="text-sm font-bold text-purple-600 dark:text-purple-400">{app.totalLikes || 0}</p>
                        <p className="text-xs text-gray-600 dark:text-gray-400">❤️ {t('common.likes') || 'Likes'}</p>
                      </div>
                      <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-2.5 text-center border border-green-100 dark:border-green-900/30">
                        <p className="text-sm font-bold text-green-600 dark:text-green-400">{app.totalComments || 0}</p>
                        <p className="text-xs text-gray-600 dark:text-gray-400">💬 {t('common.comments') || 'Comments'}</p>
                      </div>
                      <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-2.5 text-center border border-orange-100 dark:border-orange-900/30">
                        <p className="text-sm font-bold text-orange-600 dark:text-orange-400">{app.rank ? `#${app.rank}` : '-'}</p>
                        <p className="text-xs text-gray-600 dark:text-gray-400">🏆 {t('dashboard.contests.my_applications.rank') || 'Rank'}</p>
                      </div>
                    </div>
                  </div>

                  {/* Right Actions */}
                  <div className="flex gap-2 flex-col md:flex-row">
                    <Link href={`/dashboard/contests/${app.contestId}/participate?edit=true`}>
                      <Button
                        className="bg-myfav-primary hover:bg-myfav-primary-dark text-white w-full md:w-auto"
                        disabled={!canEditOrDelete(app)}
                        title={!canEditOrDelete(app) ? t('dashboard.contests.my_applications.edit_not_available') || 'Édition non disponible' : ''}
                      >
                        ✏️ {t('common.edit') || 'Éditer'}
                      </Button>
                    </Link>
                    <Button
                      variant="outline"
                      className="text-red-600 dark:text-red-400 border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-900/20 w-full md:w-auto"
                      onClick={() => setDeleteConfirmId(app.id)}
                      disabled={!canEditOrDelete(app)}
                      title={!canEditOrDelete(app) ? t('dashboard.contests.my_applications.delete_not_available') || 'Suppression non disponible' : ''}
                    >
                      🗑️ {t('common.delete') || 'Supprimer'}
                    </Button>
                  </div>
                </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Delete Confirmation Dialog - Outside the loop */}
        {deleteConfirmId !== null && (
          <ConfirmDialog
            open={deleteConfirmId !== null}
            onOpenChange={(open) => !open && setDeleteConfirmId(null)}
            title={`⚠️ ${t('common.confirm_delete')}`}
            message={t('dashboard.contests.my_applications.delete_confirm_message')}
            cancelText={t('common.cancel')}
            confirmText={isDeleting ? t('common.deleting') : t('common.delete')}
            onConfirm={() => handleDeleteApplication(deleteConfirmId)}
            isLoading={isDeleting}
            isDangerous={true}
          />
        )}
      </div>
    </div>
  )
}
