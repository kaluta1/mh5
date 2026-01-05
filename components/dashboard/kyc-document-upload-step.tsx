'use client'

import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Upload, FileCheck, AlertCircle, X, Loader, Eye } from 'lucide-react'
import { UploadButton } from '@/components/ui/upload-button'

interface DocumentUploadData {
  documentFront: string
  documentBack: string
  selfie: string
}

interface KYCDocumentUploadStepProps {
  data: DocumentUploadData
  onChange: (field: keyof DocumentUploadData, value: string) => void
}

export function KYCDocumentUploadStep({ data, onChange }: KYCDocumentUploadStepProps) {
  const { t } = useLanguage()
  const [uploading, setUploading] = useState<{ [key: string]: boolean }>({
    documentFront: false,
    documentBack: false,
    selfie: false
  })
  const [errors, setErrors] = useState<{ [key: string]: string }>({})
  const [showPreview, setShowPreview] = useState<{ [key: string]: boolean }>({
    documentFront: false,
    documentBack: false,
    selfie: false
  })

  const handleUploadComplete = (
    fieldName: keyof DocumentUploadData,
    res: any
  ) => {
    if (res && res.length > 0) {
      const file = res[0]
      onChange(fieldName, file.url)
      setErrors(prev => ({ ...prev, [fieldName]: '' }))
    }
  }

  const handleUploadError = (
    fieldName: keyof DocumentUploadData,
    error: Error
  ) => {
    setErrors(prev => ({
      ...prev,
      [fieldName]: error.message || 'Upload failed'
    }))
  }

  const UploadBox = ({
    title,
    description,
    fieldName,
    value
  }: {
    title: string
    description: string
    fieldName: keyof DocumentUploadData
    value: string
  }) => (
    <div className={`border-2 border-dashed rounded-lg p-6 text-center transition-all ${
      value
        ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20'
        : 'border-gray-300 dark:border-gray-600 hover:border-myhigh5-primary dark:hover:border-myhigh5-primary'
    }`}>
      {value ? (
        <div className="flex flex-col items-center gap-3">
          {showPreview[fieldName] ? (
            <div className="relative w-full">
              <img
                src={value}
                alt={title}
                className="w-full h-48 object-cover rounded-lg"
              />
              <button
                type="button"
                onClick={() => setShowPreview(prev => ({ ...prev, [fieldName]: false }))}
                className="absolute top-2 right-2 p-2 bg-gray-900/50 hover:bg-gray-900/70 rounded-lg text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <FileCheck className="w-8 h-8 text-green-600 dark:text-green-400" />
              <p className="text-sm font-medium text-green-700 dark:text-green-300">
                File uploaded successfully
              </p>
              <p className="text-xs text-gray-600 dark:text-gray-400 break-all line-clamp-2">{value}</p>
            </div>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowPreview(prev => ({ ...prev, [fieldName]: !prev[fieldName] }))}
              className="text-xs bg-blue-600 hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600 text-white px-3 py-1 rounded flex items-center gap-1 transition-colors"
            >
              <Eye className="w-3 h-3" />
              {showPreview[fieldName] ? 'Hide' : 'Preview'}
            </button>
            <button
              type="button"
              onClick={() => onChange(fieldName, '')}
              className="text-xs text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 flex items-center gap-1"
            >
              <X className="w-3 h-3" />
              Remove
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <Upload className="w-8 h-8 text-gray-400 dark:text-gray-500" />
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-white">{title}</p>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{description}</p>
          </div>
          <UploadButton
            endpoint="kycDocumentUploader"
            onClientUploadComplete={(res: any) => handleUploadComplete(fieldName, res)}
            onUploadError={(error: Error) => handleUploadError(fieldName, error)}
            className="ut-button:bg-myhigh5-primary ut-button:hover:bg-myhigh5-primary-dark ut-button:px-4 ut-button:py-2 ut-button:text-sm"
            content={{
              button({ ready }) {
                if (ready) return <div>Choose Image</div>
                return 'Getting ready...'
              },
              allowedContent() {
                return 'Images only (JPEG, PNG, GIF) - Max 1MB'
              }
            }}
          />
        </div>
      )}

      {errors[fieldName] && (
        <div className="mt-3 flex gap-2 text-left">
          <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-red-600 dark:text-red-400">{errors[fieldName]}</p>
        </div>
      )}
    </div>
  )

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
          Upload Documents
        </h2>
        <p className="text-gray-600 dark:text-gray-400 text-sm">
          Upload photos of your document (front and back) and a selfie for verification
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <UploadBox
          title="Document Front"
          description="Upload the front side of your document"
          fieldName="documentFront"
          value={data.documentFront}
        />

        <UploadBox
          title="Document Back"
          description="Upload the back side of your document"
          fieldName="documentBack"
          value={data.documentBack}
        />

        <div className="md:col-span-2">
          <UploadBox
            title="Selfie"
            description="Upload a clear selfie for verification"
            fieldName="selfie"
            value={data.selfie}
          />
        </div>
      </div>

      {/* Info Box */}
      <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
        <p className="text-sm text-blue-900 dark:text-blue-100">
          <strong>Note:</strong> All files must be clear and legible. Maximum file size is 100MB. Supported formats: JPEG, PNG, GIF, MP4, WebM.
        </p>
      </div>
    </div>
  )
}
