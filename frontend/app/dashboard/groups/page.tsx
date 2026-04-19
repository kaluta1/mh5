'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { WhatsAppGroupsShell } from '@/components/dashboard/groups/whatsapp-groups-shell'

export default function GroupsPage() {
  const { isAuthenticated } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
    }
  }, [isAuthenticated, router])

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="h-[calc(100vh-4rem)] sm:h-[calc(100vh-5rem)] md:h-[min(720px,calc(100vh-6rem))] -mx-2 sm:-mx-4 md:-mx-6 flex flex-col min-h-0">
      <WhatsAppGroupsShell />
    </div>
  )
}
