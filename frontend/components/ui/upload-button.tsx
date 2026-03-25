'use client'

import { useEffect, useState } from 'react'
import { UploadButton as UTUploadButton } from '@uploadthing/react'
import type { OurFileRouter } from '@/app/api/uploadthing/core'
import { useLanguage } from '@/contexts/language-context'

interface UploadButtonProps {
  endpoint: keyof OurFileRouter
  onClientUploadComplete?: (res: any) => void
  onUploadError?: (error: unknown) => void
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
  const { t } = useLanguage()
  const [token, setToken] = useState<string | null>(null)
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    // Récupérer le token depuis le localStorage
    const accessToken = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    setToken(accessToken)
    setIsReady(true)
  }, [])

  // Map endpoint to max file sizes based on core.ts configuration
  const getMaxFileSize = (endpoint: keyof OurFileRouter): string => {
    const sizes: Record<string, string> = {
      'kycDocumentUploader': '1MB',
      'profileImageUploader': '1MB',
      'profileAvatar': '2MB',
      'participationDocumentUploader': '8MB',
      'contestantMedia': '8MB',
      'verificationMedia': '8MB',
      'imageUploader': '8MB',
      'videoUploader': '32MB'
    }
    return sizes[endpoint] || '10MB'
  }

  const handleUploadError = (error: unknown) => {
    // uploadthing can pass different error shapes; never assume `error` is an Error instance.
    let errorMessage = ''
    if (error instanceof Error) {
      errorMessage = error.message
    } else if (typeof error === 'string') {
      errorMessage = error
    } else {
      try {
        errorMessage = JSON.stringify(error)
      } catch {
        errorMessage = String(error)
      }
    }

    // Handle FileSizeMismatch error with clear message
    if (errorMessage.includes('FileSizeMismatch') || errorMessage.includes('Invalid config')) {
      const maxSize = getMaxFileSize(endpoint)
      errorMessage = `${t('verification.file_too_large_with_size') || 'File is too large. Maximum size allowed'}: ${maxSize}`
    }
    // Handle other file size errors
    else if (errorMessage.toLowerCase().includes('file') && errorMessage.toLowerCase().includes('large')) {
      const maxSize = getMaxFileSize(endpoint)
      errorMessage = `${t('verification.file_too_large_with_size') || 'File is too large. Maximum size allowed'}: ${maxSize}`
    }

    // Create a new error with the improved message
    const enhancedError = new Error(errorMessage)
    onUploadError?.(enhancedError)
  }

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
      onUploadError={handleUploadError}
      className={className}
      content={content}
      headers={{
        Authorization: `Bearer ${token}`,
        ...customHeaders
      }}
    />
  )
}
