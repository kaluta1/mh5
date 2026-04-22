'use client'

import { useEffect, useRef, useState } from 'react'
import { generateReactHelpers } from '@uploadthing/react'
import type { OurFileRouter } from '@/app/api/uploadthing/core'
import { useLanguage } from '@/contexts/language-context'
import { Upload, Loader2 } from 'lucide-react'

const { useUploadThing } = generateReactHelpers<OurFileRouter>({
  url: process.env.NEXT_PUBLIC_UPLOADTHING_URL?.replace(/\/+$/, '') || '/api/uploadthing',
})

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
  const inputRef = useRef<HTMLInputElement>(null)

  const { startUpload, isUploading } = useUploadThing(endpoint, {
    headers: token
      ? {
          Authorization: `Bearer ${token}`,
          ...customHeaders,
        }
      : customHeaders,
    onClientUploadComplete: (res) => {
      onClientUploadComplete?.(res)
    },
    onUploadError: (error) => {
      handleUploadError(error)
    },
  })

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

  const buttonContent = content?.button
    ? content.button({})
    : (t('profile_setup.choose_photo') || 'Choose photo')

  const handlePickFile = () => {
    if (isUploading) return
    inputRef.current?.click()
  }

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return
    try {
      await startUpload(files)
    } catch (error) {
      handleUploadError(error)
    } finally {
      event.currentTarget.value = ''
    }
  }

  return (
    <div className={className}>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        className="hidden"
        disabled={isUploading}
      />
      <button
        type="button"
        onClick={handlePickFile}
        disabled={isUploading}
        className="inline-flex items-center justify-center gap-2 rounded-lg bg-myhigh5-primary px-3 py-2 text-sm font-medium text-white transition hover:bg-myhigh5-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isUploading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('common.uploading') || 'Uploading...'}
          </>
        ) : (
          <>
            <Upload className="h-4 w-4" />
            {buttonContent}
          </>
        )}
      </button>
      {content?.allowedContent ? (
        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {content.allowedContent()}
        </div>
      ) : null}
    </div>
  )
}
