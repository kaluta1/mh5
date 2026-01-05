'use client'

import { useRef, useState } from 'react'
import { useModeratedUpload } from '@/hooks/use-moderated-upload'
import { Upload, Loader2, AlertTriangle, CheckCircle } from 'lucide-react'
import { Button } from './button'

interface ModeratedUploadButtonProps {
  onUploadComplete: (files: { url: string; name: string; size: number; type: string }[]) => void
  onUploadError?: (error: string) => void
  accept?: string
  multiple?: boolean
  maxFiles?: number
  disabled?: boolean
  accessToken?: string
  verificationImageUrl?: string
  className?: string
  buttonText?: string
  uploadingText?: string
  allowedContentText?: string
}

export function ModeratedUploadButton({
  onUploadComplete,
  onUploadError,
  accept = 'image/*',
  multiple = false,
  maxFiles = 10,
  disabled = false,
  accessToken,
  verificationImageUrl,
  className = '',
  buttonText = 'Choisir un fichier',
  uploadingText = 'Modération et upload...',
  allowedContentText = 'Images uniquement'
}: ModeratedUploadButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [status, setStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')

  const { upload, uploadMultiple, isUploading, progress, error, moderationFlags } = useModeratedUpload({
    accessToken,
    verificationImageUrl,
    onSuccess: (result) => {
      setStatus('success')
      setTimeout(() => setStatus('idle'), 2000)
    },
    onError: (err) => {
      setStatus('error')
      onUploadError?.(err)
      setTimeout(() => setStatus('idle'), 3000)
    }
  })

  const handleClick = () => {
    if (!disabled && !isUploading) {
      inputRef.current?.click()
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    setStatus('uploading')

    if (multiple && files.length > 1) {
      const limitedFiles = files.slice(0, maxFiles)
      const results = await uploadMultiple(limitedFiles)
      if (results.length > 0) {
        onUploadComplete(results)
      }
    } else {
      const result = await upload(files[0])
      if (result) {
        onUploadComplete([result])
      }
    }

    // Reset input
    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  return (
    <div className={`flex flex-col items-center ${className}`}>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={handleFileChange}
        className="hidden"
        disabled={disabled || isUploading}
      />
      
      <Button
        type="button"
        onClick={handleClick}
        disabled={disabled || isUploading}
        className={`
          ${isUploading ? 'opacity-70' : ''}
          ${status === 'error' ? 'border-red-500 text-red-500' : ''}
          ${status === 'success' ? 'border-green-500 text-green-500' : ''}
        `}
        variant="outline"
      >
        {isUploading ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            {uploadingText} ({Math.round(progress)}%)
          </>
        ) : status === 'error' ? (
          <>
            <AlertTriangle className="w-4 h-4 mr-2" />
            Erreur de modération
          </>
        ) : status === 'success' ? (
          <>
            <CheckCircle className="w-4 h-4 mr-2" />
            Upload réussi
          </>
        ) : (
          <>
            <Upload className="w-4 h-4 mr-2" />
            {buttonText}
          </>
        )}
      </Button>

      <p className="text-xs text-gray-500 mt-2">
        {allowedContentText}
      </p>

      {/* Afficher les erreurs de modération */}
      {status === 'error' && moderationFlags.length > 0 && (
        <div className="mt-2 p-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded text-xs">
          <p className="text-red-700 dark:text-red-300 font-medium">Contenu rejeté :</p>
          <ul className="list-disc list-inside text-red-600 dark:text-red-400">
            {moderationFlags.map((flag, idx) => (
              <li key={idx}>{flag.description}</li>
            ))}
          </ul>
        </div>
      )}

      {status === 'error' && error && moderationFlags.length === 0 && (
        <p className="mt-2 text-xs text-red-500">{error}</p>
      )}
    </div>
  )
}
