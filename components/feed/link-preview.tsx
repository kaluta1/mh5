'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'
import { Link as LinkIcon, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'

interface LinkPreviewProps {
  url: string
}

interface LinkMetadata {
  title?: string
  description?: string
  image?: string
  siteName?: string
}

export function LinkPreview({ url }: LinkPreviewProps) {
  const [metadata, setMetadata] = useState<LinkMetadata | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // In a real app, you'd fetch this from your backend
    // For now, we'll just extract basic info from the URL
    const urlObj = new URL(url)
    setMetadata({
      title: urlObj.hostname,
      description: url,
      siteName: urlObj.hostname.replace('www.', ''),
    })
    setIsLoading(false)
  }, [url])

  if (isLoading) {
    return (
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-2" />
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/2" />
      </div>
    )
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="block border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden hover:shadow-md transition-shadow"
    >
      {metadata?.image && (
        <div className="relative w-full h-48 bg-gray-100 dark:bg-gray-800">
          <Image
            src={metadata.image}
            alt={metadata.title || ''}
            fill
            className="object-cover"
          />
        </div>
      )}
      <div className="p-4">
        {metadata?.siteName && (
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-1">
            <LinkIcon className="h-3 w-3" />
            <span>{metadata.siteName}</span>
          </div>
        )}
        {metadata?.title && (
          <h4 className="font-semibold text-gray-900 dark:text-white mb-1 line-clamp-2">
            {metadata.title}
          </h4>
        )}
        {metadata?.description && (
          <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
            {metadata.description}
          </p>
        )}
        <div className="flex items-center gap-2 mt-2 text-xs text-myhigh5-primary">
          <span>{url}</span>
          <ExternalLink className="h-3 w-3" />
        </div>
      </div>
    </a>
  )
}

