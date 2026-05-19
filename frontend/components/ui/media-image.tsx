'use client'

import { normalizeMediaUrl } from '@/lib/media-url'
import { cn } from '@/lib/utils'

type MediaImageProps = {
  src?: string | null
  alt: string
  width?: number
  height?: number
  fill?: boolean
  className?: string
  title?: string
  onError?: () => void
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
}: MediaImageProps) {
  const url = normalizeMediaUrl(src)
  if (!url) return null

  if (fill) {
    return (
      <img
        src={url}
        alt={alt}
        className={cn('h-full w-full object-cover', className)}
        title={title}
        onError={onError}
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
      onError={onError}
    />
  )
}
