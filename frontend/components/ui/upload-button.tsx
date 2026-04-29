'use client'

import { useEffect, useRef, useState } from 'react'
import type { OurFileRouter } from '@/app/api/uploadthing/core'
import { useLanguage } from '@/contexts/language-context'
import { Upload, Loader2 } from 'lucide-react'
import { API_URL } from '@/lib/config'

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
  const [isUploading, setIsUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

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
      'imageUploader': '30MB',
      'videoUploader': '1GB'
    }
    return sizes[endpoint] || '10MB'
  }

  const toBytes = (sizeLabel: string): number => {
    const match = sizeLabel.trim().toUpperCase().match(/^(\d+(?:\.\d+)?)\s*(KB|MB|GB)$/)
    if (!match) return 0
    const value = Number(match[1])
    const unit = match[2]
    if (unit === 'KB') return value * 1024
    if (unit === 'MB') return value * 1024 * 1024
    if (unit === 'GB') return value * 1024 * 1024 * 1024
    return 0
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

  const acceptedTypes = endpoint === 'videoUploader' ? 'video/*' : 'image/*'

  const handlePickFile = () => {
    if (isUploading) return
    inputRef.current?.click()
  }

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return
    try {
      setIsUploading(true)
      const maxSizeLabel = getMaxFileSize(endpoint)
      const maxSizeBytes = toBytes(maxSizeLabel)

      if (maxSizeBytes > 0) {
        const oversizedFile = files.find((file) => file.size > maxSizeBytes)
        if (oversizedFile) {
          throw new Error(
            `${t('verification.file_too_large_with_size') || 'File is too large. Maximum size allowed'}: ${maxSizeLabel}`
          )
        }
      }

      const uploadedResults: Array<{ id?: number; url: string; name: string; size: number; type: string }> = []
      for (const file of files) {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('title', file.name)

        const response = await fetch(`${API_URL}/api/v1/media/upload`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            ...customHeaders,
          },
          body: formData,
        })

        if (!response.ok) {
          if (response.status === 413) {
            throw new Error(
              `${t('verification.file_too_large_with_size') || 'File is too large. Maximum size allowed'}: ${maxSizeLabel}`
            )
          }
          let message = 'Upload failed'
          try {
            const errorData = await response.json()
            message = errorData?.detail || errorData?.error || message
          } catch {
            // Keep generic message when body is not JSON
          }
          throw new Error(message)
        }

        const data = await response.json()
        const url = data?.url || data?.path
        if (!url) {
          throw new Error('Upload succeeded but no file URL was returned')
        }

        uploadedResults.push({
          id: typeof data?.id === 'number' ? data.id : undefined,
          url,
          name: data?.title || file.name,
          size: file.size,
          type: file.type,
        })
      }

      onClientUploadComplete?.(uploadedResults)
    } catch (error) {
      handleUploadError(error)
    } finally {
      setIsUploading(false)
      event.currentTarget.value = ''
    }
  }

  return (
    <div className={className}>
      <input
        ref={inputRef}
        type="file"
        accept={acceptedTypes}
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
