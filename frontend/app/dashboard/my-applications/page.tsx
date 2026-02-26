'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { ApplicationsSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { DataTable, Column } from '@/components/ui/data-table'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { contestService } from '@/services/contest-service'
import { AlertCircle, Eye, Edit, Trash2, Radio, ExternalLink } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'

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
  totalFavorites?: number
  totalShares?: number
  coverImage?: string
  isLive?: boolean
}

export default function MyApplicationsPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { addToast } = useToast()
  const router = useRouter()

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

        // Récupérer les candidatures de l'utilisateur directement
        const myContestants = await contestService.getMyApplications(0, 500)

        // Ensure myContestants is an array before mapping
        if (!Array.isArray(myContestants)) {
          console.warn('getMyApplications returned non-array:', myContestants)
          setApplications([])
          return
        }

        const userApplications: Application[] = myContestants.map(c => {
          // Extraire l'image si contestant_image_url n'est pas défini
          let coverImage = c.contestant_image_url
          if (!coverImage && c.image_media_ids) {
            try {
              const imageIds = JSON.parse(c.image_media_ids)
              if (Array.isArray(imageIds) && imageIds.length > 0) {
                coverImage = imageIds[0]
              }
            } catch (e) {
              console.error('Erreur parsing image_media_ids:', e)
            }
          }

          return {
            id: c.id,
            contestId: c.contest_id || c.season_id,
            contestName: c.contest_title || t('common.unknown') || 'Unknown',
            contestLevel: c.contest_level,
            title: c.title || '',
            description: c.description || '',
            rank: c.rank,
            registrationDate: c.registration_date,
            status: c.is_qualified ? 'approved' : 'pending',
            totalVotes: c.votes_count,
            totalComments: c.comments_count || 0,
            totalLikes: c.reactions_count || 0,
            totalFavorites: c.favorites_count || 0,
            totalShares: c.shares_count || 0,
            coverImage: coverImage,
            isLive: false
          }
        })

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
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200 border-yellow-200 dark:border-yellow-800'
      case 'approved':
        return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 border-green-200 dark:border-green-800'
      case 'rejected':
        return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200 border-red-200 dark:border-red-800'
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 border-gray-200 dark:border-gray-600'
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

  const getLevelLabel = (level?: string) => {
    if (!level) return ''
    switch (level) {
      case 'country':
        return '🌍 ' + (t('dashboard.contests.country') || 'Country')
      case 'continental':
        return '🌎 ' + (t('dashboard.contests.continental') || 'Continental')
      case 'regional':
        return '🗺️ ' + (t('dashboard.contests.regional') || 'Regional')
      case 'global':
        return '🌐 ' + (t('dashboard.contests.global') || 'Global')
      default:
        return level
    }
  }

  const formatDate = (dateString: string) => {
    if (!dateString) return '-'
    return new Date(dateString).toLocaleDateString('fr-FR', {
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    })
  }

  const handleDeleteApplication = async (appId: number) => {
    setIsDeleting(true)
    try {
      await contestService.deleteContestant(appId)
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

  const handleViewDetails = (app: Application) => {
    if (router) {
      router.push(`/dashboard/my-applications/${app.id}`)
    }
  }

  const columns: Column<Application>[] = [
    {
      key: 'contest',
      header: t('dashboard.contests.my_applications.contest') || 'Concours',
      render: (app) => (
        <div className="flex items-center gap-3">
          {app.coverImage && (
            <img
              src={app.coverImage}
              alt={app.contestName}
              className="w-12 h-12 rounded-lg object-cover"
            />
          )}
          <div>
            <p className="font-semibold text-gray-900 dark:text-white">{app.contestName}</p>
            {app.contestLevel && (
              <p className="text-xs text-gray-500 dark:text-gray-400">{getLevelLabel(app.contestLevel)}</p>
            )}
          </div>
        </div>
      )
    },
    {
      key: 'title',
      header: t('dashboard.contests.my_applications.title') || 'Titre',
      render: (app) => (
        <div>
          <p className="font-medium text-gray-900 dark:text-white line-clamp-1">
            {app.title || t('dashboard.contests.my_applications.no_title')}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1 mt-1">
            {app.description}
          </p>
        </div>
      ),
      className: 'max-w-xs'
    },
    {
      key: 'status',
      header: t('dashboard.contests.my_applications.status') || 'Statut',
      render: (app) => (
        <Badge className={getStatusColor(app.status)}>
          {getStatusLabel(app.status)}
        </Badge>
      )
    },
    {
      key: 'rank',
      header: t('dashboard.contests.rank') || 'Rang',
      render: (app) => (
        app.rank ? (
          <Badge className="bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
            🏆 #{app.rank}
          </Badge>
        ) : (
          <span className="text-gray-400">-</span>
        )
      )
    },
    {
      key: 'stats',
      header: t('dashboard.contests.my_applications.statistics') || 'Statistiques',
      render: (app) => (
        <div className="flex gap-2 text-xs">
          <div className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
            <span>⚡</span>
            <span>{app.totalVotes || 0}</span>
          </div>
          <div className="flex items-center gap-1 text-purple-600 dark:text-purple-400">
            <span>❤️</span>
            <span>{app.totalLikes || 0}</span>
          </div>
          <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
            <span>💬</span>
            <span>{app.totalComments || 0}</span>
          </div>
          <div className="flex items-center gap-1 text-orange-600 dark:text-orange-400">
            <span>⭐</span>
            <span>{app.totalFavorites || 0}</span>
          </div>
        </div>
      )
    },
    {
      key: 'date',
      header: t('dashboard.contests.my_applications.date') || 'Date',
      render: (app) => (
        <span className="text-sm text-gray-600 dark:text-gray-400">
          {formatDate(app.registrationDate)}
        </span>
      )
    },
    {
      key: 'actions',
      header: t('common.actions') || 'Actions',
      render: (app) => (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation()
              handleViewDetails(app)
            }}
            className="h-8"
            title={t('dashboard.contests.my_applications.view_details') || 'Voir les détails'}
          >
            <Eye className="w-4 h-4" />
          </Button>
          <Link href={`/dashboard/contests/${app.contestId}/apply?edit=true&contestantId=${app.id}`}>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              title={t('common.edit') || 'Éditer'}
            >
              <Edit className="w-4 h-4" />
            </Button>
          </Link>
          <Link href={`/dashboard/contests/${app.contestId}/contestant/${app.id}`}>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              title={t('dashboard.contests.my_applications.view_page') || t('dashboard.contests.view_details') || 'Voir la page'}
            >
              <ExternalLink className="w-4 h-4" />
            </Button>
          </Link>
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation()
              setDeleteConfirmId(app.id)
            }}
            className="h-8 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-900/20"
            title={t('common.delete') || 'Supprimer'}
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      )
    }
  ]

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
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-red-900 dark:text-red-200">{error}</p>
            </div>
          </div>
        )}

        {/* Data Table */}
        <DataTable
          data={applications}
          columns={columns}
          emptyIcon={<span className="text-5xl">🏆</span>}
          emptyTitle={t('dashboard.contests.my_applications.no_applications')}
          emptyDescription={
            <div className="mt-4">
              <Link href="/dashboard/contests">
                <Button className="bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white">
                  {t('dashboard.contests.my_applications.browse_contests')} →
                </Button>
              </Link>
            </div>
          }
          onRowClick={(app) => handleViewDetails(app)}
          rowClassName="cursor-pointer"
        />

        {/* Delete Confirmation Dialog */}
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
