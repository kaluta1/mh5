'use client'

import { useEffect, useState } from 'react'
import { UploadButton as UTUploadButton } from '@uploadthing/react'
import type { OurFileRouter } from '@/app/api/uploadthing/core'

interface UploadButtonProps {
  endpoint: keyof OurFileRouter
  onClientUploadComplete?: (res: any) => void
  onUploadError?: (error: Error) => void
  className?: string
  content?: {
    button?: (props: any) => React.ReactNode
    allowedContent?: () => React.ReactNode
  }
  headers?: Record<string, string>
}

export function UploadButton({
  endpoint,
  onClientUploadComplete,
  onUploadError,
  className,
  content,
  headers: customHeaders
}: UploadButtonProps) {
  const [token, setToken] = useState<string | null>(null)
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    // Récupérer le token depuis le localStorage
    const accessToken = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    setToken(accessToken)
    setIsReady(true)
  }, [])

  if (!isReady || !token) {
    return (
      <div className="text-sm text-red-600 dark:text-red-400">
        Please log in to upload files
      </div>
    )
  }

  return (
    <UTUploadButton<OurFileRouter, typeof endpoint>
      endpoint={endpoint}
      onClientUploadComplete={onClientUploadComplete}
      onUploadError={onUploadError}
      className={className}
      content={content}
      headers={{
        Authorization: `Bearer ${token}`,
        ...customHeaders
      }}
    />
  )
}
