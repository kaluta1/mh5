'use client'

import { useState } from 'react'
import { Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'

interface MediaUploaderProps {
  onMediaSelect: (file: File) => void
  previewUrl?: string
  onRemove?: () => void
  isLoading?: boolean
}

export function MediaUploader({
  onMediaSelect,
  previewUrl,
  onRemove,
  isLoading = false
}: MediaUploaderProps) {
  const { t } = useLanguage()
  const [error, setError] = useState<string>('')

  const handleFileSelect = (file: File) => {
    // Vérifier le type de fichier
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'video/mp4', 'video/webm']
    if (!validTypes.includes(file.type)) {
      setError('invalid_file_type')
      return
    }

    // Vérifier la taille (max 100MB)
    if (file.size > 100 * 1024 * 1024) {
      setError('file_too_large')
      return
    }

    setError('')
    onMediaSelect(file)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleFileSelect(file)
    }
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    
    const file = e.dataTransfer.files?.[0]
    if (file) {
      handleFileSelect(file)
    }
  }

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
  }

  if (previewUrl) {
    return (
      <div className="relative">
        <div className="relative w-full h-64 rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-700">
          {previewUrl.startsWith('data:image') ? (
            <img
              src={previewUrl}
              alt="Preview"
              className="w-full h-full object-cover"
            />
          ) : (
            <video
              src={previewUrl}
              className="w-full h-full object-cover"
              controls
            />
          )}
        </div>
        <button
          type="button"
          onClick={onRemove}
          disabled={isLoading}
          className="absolute top-2 right-2 bg-red-500 hover:bg-red-600 disabled:bg-red-400 text-white p-2 rounded-lg transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    )
  }

  return (
    <div>
      <label>
        <input
          type="file"
          accept="image/*,video/*"
          onChange={handleChange}
          disabled={isLoading}
          className="hidden"
        />
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-8 text-center cursor-pointer hover:border-myhigh5-primary hover:bg-myhigh5-primary/5 transition-all disabled:opacity-50"
        >
          <Upload className="w-12 h-12 text-gray-400 dark:text-gray-500 mx-auto mb-3" />
          <p className="text-gray-600 dark:text-gray-400 font-medium mb-1">
            {t('dashboard.contests.participation_form.drag_drop')}
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-500">
            {t('dashboard.contests.participation_form.file_info')}
          </p>
        </div>
      </label>
      
      {error && (
        <p className="text-red-600 dark:text-red-400 text-sm mt-2">
          {t(`dashboard.contests.participation_form.error.${error}`)}
        </p>
      )}
    </div>
  )
}
