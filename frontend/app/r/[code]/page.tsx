'use client'

import { Suspense } from 'react'
import { useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { logger } from '@/lib/logger'
import { resolvePublicApiBase } from '@/lib/config'

function ReferralRedirectPageContent() {
  const router = useRouter()
  const params = useParams()
  const code = params.code as string

  useEffect(() => {
    if (code) {
      // Stocker le code de parrainage dans localStorage
      localStorage.setItem('referral_code', code)

      // Tracker le clic sur le lien de parrainage (optionnel)
      fetch(`${resolvePublicApiBase()}/api/v1/affiliates/track-click/${code}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      }).catch((error) => {
        logger.error('Failed to track referral click', error)
      })

      // Redirect to home with referral code — home page handles register CTA for guests
      router.push(`/?ref=${code}`)
    }
  }, [code, router])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-gray-900 dark:via-blue-900/20 dark:to-purple-900/20 flex items-center justify-center">
      <div className="text-center">
        <Loader2 className="w-12 h-12 animate-spin text-myfav-primary mx-auto mb-4" />
        <p className="text-lg text-gray-700 dark:text-gray-200">Redirection en cours...</p>
      </div>
    </div>
  )
}

export default function ReferralRedirectPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-gray-900 dark:via-blue-900/20 dark:to-purple-900/20 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-myfav-primary mx-auto mb-4" />
          <p className="text-lg text-gray-700 dark:text-gray-200">Redirection en cours...</p>
        </div>
      </div>
    }>
      <ReferralRedirectPageContent />
    </Suspense>
  )
}
