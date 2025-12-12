'use client'

import { useEffect } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'

export default function PublicContestantPage() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const contestantId = params.id as string
  const refCode = searchParams.get('ref')

  useEffect(() => {
    // Attendre que le chargement de l'authentification soit terminé
    if (isLoading) {
      return
    }

    // Si l'utilisateur est connecté, rediriger vers la page dashboard
    if (isAuthenticated && user) {
      router.push(`/dashboard/contestants/${contestantId}`)
      return
    }

    // Si l'utilisateur n'est pas connecté
    if (!isAuthenticated) {
      // Si un code de référence est présent, le sauvegarder dans localStorage
      if (refCode) {
        localStorage.setItem('referral_code', refCode)
      }
      
      // Rediriger vers la page d'inscription avec le code de référence
      if (refCode) {
        router.push(`/register?ref=${refCode}`)
      } else {
        router.push('/register')
      }
    }
  }, [isAuthenticated, isLoading, user, router, contestantId, refCode])

  // Afficher un loader pendant le traitement
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-myfav-primary mx-auto mb-4"></div>
        <p className="text-gray-600 dark:text-gray-400">Chargement...</p>
      </div>
    </div>
  )
}

