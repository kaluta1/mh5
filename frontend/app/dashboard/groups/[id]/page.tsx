'use client'

import { useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'

/** Legacy URL: open chat in the unified WhatsApp-style groups UI. */
export default function GroupDetailRedirectPage() {
  const params = useParams()
  const router = useRouter()
  const id = params?.id

  useEffect(() => {
    if (id != null && id !== '') {
      router.replace(`/dashboard/groups?g=${encodeURIComponent(String(id))}`)
    } else {
      router.replace('/dashboard/groups')
    }
  }, [id, router])

  return (
    <div className="flex items-center justify-center py-24 text-muted-foreground">
      <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" aria-hidden />
      <span className="sr-only">Redirecting…</span>
    </div>
  )
}
