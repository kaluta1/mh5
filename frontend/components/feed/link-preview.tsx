'use client'

import { useState, useEffect, useCallback } from 'react'
import { Link as LinkIcon, ExternalLink } from 'lucide-react'

interface LinkPreviewProps {
  url: string
  /** compact: title + site badge + cover image only (feed cards) */
  variant?: 'full' | 'compact'
}

interface LinkMetadata {
  title?: string
  description?: string
  image?: string
  siteName?: string
  url?: string
}

function getYouTubeVideoId(url: string): string | undefined {
  const patterns = [
    /youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})/i,
    /youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})/i,
    /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/i,
    /youtu\.be\/([a-zA-Z0-9_-]{11})/i,
  ]
  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match?.[1]) return match[1]
  }
  return undefined
}

function shouldHideDescription(desc: string | undefined, metaUrl: string | undefined, originalUrl: string): boolean {
  const d = desc?.trim()
  if (!d) return true
  if (d === metaUrl || d === originalUrl) return true
  if (/^by\s+/i.test(d)) return true
  if (/^https?:\/\//i.test(d)) return true
  return false
}

export function LinkPreview({ url, variant = 'full' }: LinkPreviewProps) {
  const [metadata, setMetadata] = useState<LinkMetadata | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [imgSrc, setImgSrc] = useState<string | undefined>(undefined)
  const ytId = getYouTubeVideoId(url)

  useEffect(() => {
    let isCancelled = false

    const loadPreview = async () => {
      setIsLoading(true)

      try {
        const response = await fetch(`/link-preview?url=${encodeURIComponent(url)}`)
        const data = await response.json()

        if (!isCancelled) {
          if (response.ok) {
            setMetadata(data)
            setImgSrc(typeof data.image === 'string' ? data.image : undefined)
          } else {
            const urlObj = new URL(url)
            setMetadata({
              title: urlObj.hostname,
              description: url,
              siteName: urlObj.hostname.replace('www.', ''),
              url,
            })
            setImgSrc(undefined)
          }
        }
      } catch {
        if (!isCancelled) {
          try {
            const urlObj = new URL(url)
            setMetadata({
              title: urlObj.hostname,
              description: url,
              siteName: urlObj.hostname.replace('www.', ''),
              url,
            })
          } catch {
            setMetadata({
              title: url,
              description: url,
              siteName: 'Link',
              url,
            })
          }
          setImgSrc(undefined)
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false)
        }
      }
    }

    loadPreview()

    return () => {
      isCancelled = true
    }
  }, [url])

  useEffect(() => {
    if (metadata?.image) {
      setImgSrc(metadata.image)
    }
  }, [metadata?.image])

  const onImgError = useCallback(() => {
    if (!ytId || !imgSrc) return
    if (imgSrc.includes('maxresdefault')) {
      setImgSrc(`https://img.youtube.com/vi/${ytId}/hqdefault.jpg`)
    } else if (imgSrc.includes('hqdefault')) {
      setImgSrc(`https://img.youtube.com/vi/${ytId}/mqdefault.jpg`)
    }
  }, [imgSrc, ytId])

  if (isLoading) {
    return (
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-2" />
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/2" />
      </div>
    )
  }

  const showDescription =
    variant === 'full' &&
    !shouldHideDescription(metadata?.description, metadata?.url, url)

  const showFooterUrl = variant === 'full'

  const imageShellClass =
    variant === 'compact'
      ? 'relative w-full aspect-video overflow-hidden bg-black'
      : 'relative w-full aspect-video sm:aspect-[2/1] overflow-hidden bg-gray-100 dark:bg-gray-800'

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="block border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden hover:shadow-md transition-shadow"
    >
      {imgSrc && (
        <div className={imageShellClass}>
          <img
            src={imgSrc}
            alt=""
            className="absolute inset-0 h-full w-full object-cover object-center"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={onImgError}
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
        {showDescription && metadata?.description && (
          <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
            {metadata.description}
          </p>
        )}
        {showFooterUrl && (
          <div className="flex items-center gap-2 mt-2 text-xs text-myhigh5-primary">
            <span className="truncate">{metadata?.url || url}</span>
            <ExternalLink className="h-3 w-3 flex-shrink-0" />
          </div>
        )}
      </div>
    </a>
  )
}
