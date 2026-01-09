'use client'

import { useParams, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from 'lucide-react'
import AdminContestants from '@/components/admin/admin-contestants'
import api from '@/lib/api'

interface Contest {
  id: number
  name: string
  description?: string
}

export default function ContestContestantsPage() {
  const params = useParams()
  const router = useRouter()
  const contestId = params.contestId as string
  const [contest, setContest] = useState<Contest | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchContest = async () => {
      try {
        const response = await api.get(`/api/v1/admin/contests/${contestId}`)
        setContest(response.data)
      } catch (error) {
        console.error('Erreur lors du chargement du concours:', error)
      } finally {
        setLoading(false)
      }
    }

    if (contestId) {
      fetchContest()
    }
  }, [contestId])

  return (
    <div className="space-y-6">
      {/* Header with back button */}
      <div className="flex items-center gap-4">
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.back()}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Retour
        </Button>
        {!loading && contest && (
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
              Candidats - {contest.name}
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">
              {contest.description}
            </p>
          </div>
        )}
      </div>

      {/* Contestants list */}
      {!loading && (
        <AdminContestants contestId={parseInt(contestId)} />
      )}
    </div>
  )
}
