'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { contestService, ContestantWithAuthorAndStats } from '@/services/contest-service'
import { Metadata } from 'next'

export default function PublicContestantPage() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const contestantId = params.id as string
  const refCode = searchParams.get('ref')
  const [contestant, setContestant] = useState<ContestantWithAuthorAndStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadContestant = async () => {
      if (!contestantId) return

      try {
        const data = await contestService.getContestantById(Number(contestantId))
        setContestant(data)
      } catch (error) {
        console.error('Error loading contestant:', error)
      } finally {
        setLoading(false)
      }
    }

    loadContestant()
  }, [contestantId])

  useEffect(() => {
    // Attendre que le chargement de l'authentification soit terminé
    if (isLoading || loading) {
      return
    }

    // Si un code de référence est présent, le sauvegarder dans localStorage
    if (refCode) {
      localStorage.setItem('referral_code', refCode)
    }

    // Si l'utilisateur est connecté, rediriger vers la page dashboard
    if (isAuthenticated && user) {
      router.push(`/dashboard/contestants/${contestantId}`)
      return
    }

    // Si l'utilisateur n'est pas connecté, rediriger vers la page d'inscription
    if (!isAuthenticated) {
      if (refCode) {
        router.push(`/register?ref=${refCode}`)
      } else {
        router.push('/register')
      }
    }
  }, [isAuthenticated, isLoading, user, router, contestantId, refCode, loading])

  // Afficher un loader pendant le traitement
  if (loading || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-myfav-primary mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Chargement...</p>
        </div>
      </div>
    )
  }

  // Afficher les métadonnées pour le preview (même si on redirige)
  return (
    <>
      {/* Métadonnées Open Graph pour le preview */}
      {contestant && (
        <>
          <meta property="og:title" content={contestant.title || `${contestant.author_name || 'Contestant'} - MyHigh5`} />
          <meta property="og:description" content={contestant.description || `Découvrez ${contestant.author_name || 'ce participant'} sur MyHigh5`} />
          <meta property="og:type" content="profile" />
          <meta property="og:url" content={`${typeof window !== 'undefined' ? window.location.origin : ''}/contestants/${contestantId}`} />
          {/* SEO Image Fallback Logic */}
          {(() => {
            const seoImage = contestant.contestant_image_url || contestant.contest_image_url || contestant.author_avatar_url;

            return seoImage ? (
              <>
                <meta property="og:image" content={seoImage} />
                <meta name="twitter:image" content={seoImage} />
              </>
            ) : null;
          })()}
          <meta name="twitter:card" content="summary_large_image" />
          <meta name="twitter:title" content={contestant.title || `${contestant.author_name || 'Contestant'} - MyHigh5`} />
          <meta name="twitter:description" content={contestant.description || `Découvrez ${contestant.author_name || 'ce participant'} sur MyHigh5`} />
        </>
      )}

      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-myfav-primary mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Redirection...</p>
        </div>
      </div>
    </>
  )
}
