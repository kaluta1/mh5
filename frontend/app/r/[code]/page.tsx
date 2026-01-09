'use client'

import { useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { Loader2 } from 'lucide-react'

export default function ReferralRedirectPage() {
  const router = useRouter()
  const params = useParams()
  const code = params.code as string

  useEffect(() => {
    if (code) {
      // Stocker le code de parrainage dans localStorage
      localStorage.setItem('referral_code', code)
      
      // Tracker le clic sur le lien de parrainage (optionnel)
      fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/track-click/${code}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      }).catch(console.error)
      
      // Rediriger vers la page d'inscription avec le code
      router.push(`/register?ref=${code}`)
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
