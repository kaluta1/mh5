'use client'

import { normalizeMediaUrl } from '@/lib/media-url'
import { cn } from '@/lib/utils'
import { useEffect, useState } from 'react'

type MediaImageProps = {
  src?: string | null
  alt: string
  width?: number
  height?: number
  fill?: boolean
  className?: string
  title?: string
  onError?: () => void
  fallbackSrc?: string | null
}

/**
 * User/API media must not go through next/image — the optimizer returns 400
 * when the API host is missing from remotePatterns or fetch fails server-side.
 */
export function MediaImage({
  src,
  alt,
  width,
  height,
  fill,
  className,
  title,
  onError,
  fallbackSrc,
}: MediaImageProps) {
  const primaryUrl = normalizeMediaUrl(src)
  const fallbackUrl = normalizeMediaUrl(fallbackSrc)
  const [url, setUrl] = useState(primaryUrl || fallbackUrl)

  useEffect(() => {
    setUrl(primaryUrl || fallbackUrl)
  }, [primaryUrl, fallbackUrl])

  if (!url) return null

  const handleError = () => {
    if (fallbackUrl && url !== fallbackUrl) setUrl(fallbackUrl)
    else setUrl('')
    onError?.()
  }

  if (fill) {
    return (
      <img
        src={url}
        alt={alt}
        className={cn('h-full w-full object-cover', className)}
        title={title}
        onError={handleError}
      />
    )
  }

  return (
    <img
      src={url}
      alt={alt}
      width={width}
      height={height}
      className={className}
      title={title}
      onError={handleError}
    />
  )
}
