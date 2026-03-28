'use client'

import { useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'

import api from '@/lib/api'

export default function UsernameProfileRedirectPage() {
  const params = useParams()
  const router = useRouter()
  const username = String(params.username || '')

  useEffect(() => {
    const resolveUser = async () => {
      if (!username) {
        router.replace('/dashboard/feed')
        return
      }

      try {
        const response = await api.get(`/api/v1/users/by-username/${encodeURIComponent(username)}`)
        const userId = response.data?.id

        if (userId) {
          router.replace(`/dashboard/users/${userId}`)
          return
        }
      } catch (error) {
        console.error('Error resolving mentioned user:', error)
      }

      router.replace('/dashboard/feed')
    }

    resolveUser()
  }, [router, username])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="flex items-center gap-3 text-gray-600 dark:text-gray-300">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>Opening profile...</span>
      </div>
    </div>
  )
}
