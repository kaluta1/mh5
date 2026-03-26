'use client'

import React, { useState, useEffect } from 'react'
import { convertToEmbedUrl, VideoInfo, cleanVideoUrl } from '@/lib/utils/video-platforms'
import { ExternalLink, Play, Loader2 } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

interface VideoEmbedProps {
  url: string | null | undefined
  className?: string
  autoplay?: boolean
  allowFullscreen?: boolean
  width?: string | number
  height?: string | number
}

interface TikTokMeta {
  videoId: string | null
  thumbnailUrl: string | null
  authorName: string | null
  title: string | null
  loading: boolean
  failed: boolean
}

/**
 * Fetches TikTok oEmbed metadata server-side (thumbnail, author, title, video ID).
 */
function useTikTokMeta(url: string | undefined): TikTokMeta {
  const [meta, setMeta] = useState<TikTokMeta>({
    videoId: null,
    thumbnailUrl: null,
    authorName: null,
    title: null,
    loading: false,
    failed: false,
  })

  useEffect(() => {
    if (!url) return

    setMeta(m => ({ ...m, loading: true, failed: false }))

    fetch(`/api/tiktok-resolve?url=${encodeURIComponent(url)}`)
      .then(res => {
        if (!res.ok) throw new Error('Resolve failed')
        return res.json()
      })
      .then(data => {
        setMeta({
          videoId: data.videoId || null,
          thumbnailUrl: data.thumbnailUrl || null,
          authorName: data.authorName || null,
          title: data.title || null,
          loading: false,
          failed: !data.videoId && !data.thumbnailUrl,
        })
      })
      .catch(() => {
        setMeta(m => ({ ...m, loading: false, failed: true }))
      })
  }, [url])

  return meta
}

export function VideoEmbed({
  url,
  className = '',
  autoplay = false,
  allowFullscreen = true,
  width = '100%',
  height = '100%'
}: VideoEmbedProps) {
  const { t } = useLanguage()

  const cleanedUrl = url ? cleanVideoUrl(url) : ''
  const videoInfo: VideoInfo = cleanedUrl ? convertToEmbedUrl(cleanedUrl) : { platform: 'unknown', embedUrl: '', originalUrl: '' }

  const tiktokMeta = useTikTokMeta(
    videoInfo.platform === 'tiktok' ? videoInfo.originalUrl : undefined
  )

  if (!url) {
    return (
      <div className={`flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-lg ${className}`} style={{ width, height }}>
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          {t('participation.invalid_url') || 'Invalid video URL'}
        </p>
      </div>
    )
  }

  // ── Direct video file ──
  if (videoInfo.platform === 'direct') {
    return (
      <video
        src={videoInfo.embedUrl}
        controls
        autoPlay={autoplay}
        className={className}
        style={{ width, height }}
        playsInline
      />
    )
  }

  // ── Unknown / unsupported platform ──
  if (videoInfo.platform === 'unknown') {
    return (
      <div className={`flex flex-col items-center justify-center bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-6 ${className}`} style={{ width, height }}>
        <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center mb-3">
          <ExternalLink className="w-5 h-5 text-red-500" />
        </div>
        <p className="text-red-600 dark:text-red-400 text-sm font-medium text-center">
          {t('participation.unsupported_platform') || 'Link not allowed'}
        </p>
        <p className="text-red-400 dark:text-red-500 text-xs mt-1 text-center">
          {t('participation.only_youtube_tiktok') || 'Only YouTube and TikTok are accepted'}
        </p>
      </div>
    )
  }

  // ── TikTok ──
  if (videoInfo.platform === 'tiktok') {
    const openUrl = videoInfo.originalUrl

    if (tiktokMeta.loading) {
      return (
        <div className={`${className} flex flex-col items-center justify-center bg-black rounded-xl`} style={{ width, height }}>
          <Loader2 className="w-8 h-8 text-white animate-spin mb-3" />
          <p className="text-white/60 text-sm">{t('common.loading') || 'Loading...'}</p>
        </div>
      )
    }

    // Thumbnail available → show YouTube-like preview card, click to open TikTok
    if (tiktokMeta.thumbnailUrl) {
      return (
        <a
          href={openUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={`${className} relative block cursor-pointer group rounded-xl overflow-hidden bg-black`}
          style={{ width, height }}
          title={tiktokMeta.title || 'Watch on TikTok'}
        >
          {/* Thumbnail image */}
          <img
            src={tiktokMeta.thumbnailUrl}
            alt={tiktokMeta.title || 'TikTok video'}
            className="w-full h-full object-cover"
          />

          {/* Hover overlay */}
          <div className="absolute inset-0 bg-black/10 group-hover:bg-black/30 transition-colors duration-200" />

          {/* Play button */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-14 h-14 rounded-full bg-white/90 group-hover:bg-white flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform duration-200">
              <Play className="w-7 h-7 text-black ml-1" fill="black" />
            </div>
          </div>

          {/* TikTok badge — bottom right */}
          <div className="absolute bottom-3 right-3 flex items-center gap-1.5 bg-black/60 rounded-full px-2.5 py-1">
            <svg viewBox="0 0 24 24" className="w-4 h-4 fill-white" xmlns="http://www.w3.org/2000/svg">
              <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 00-.79-.05 6.34 6.34 0 00-6.34 6.34 6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.33-6.34V8.8a8.18 8.18 0 004.78 1.52V6.87a4.85 4.85 0 01-1.01-.18z"/>
            </svg>
            <span className="text-white text-xs font-semibold">TikTok</span>
          </div>

          {/* Author name — bottom left */}
          {tiktokMeta.authorName && (
            <div className="absolute bottom-3 left-3 text-white text-xs font-medium drop-shadow-md">
              @{tiktokMeta.authorName}
            </div>
          )}
        </a>
      )
    }

    // No thumbnail but have a numeric video ID → try iframe
    if (tiktokMeta.videoId && /^\d+$/.test(tiktokMeta.videoId)) {
      return (
        <div className={`${className} flex items-center justify-center bg-black rounded-xl overflow-hidden`} style={{ width, height }}>
          <iframe
            src={`https://www.tiktok.com/embed/v2/${tiktokMeta.videoId}`}
            className="rounded-lg"
            style={{ width: '100%', maxWidth: '325px', height: '100%', minHeight: '500px', border: 'none' }}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen={allowFullscreen}
            title="TikTok video"
          />
        </div>
      )
    }

    // Full fallback — plain "Watch on TikTok" button
    return (
      <div
        className={`${className} flex flex-col items-center justify-center bg-black rounded-xl overflow-hidden gap-4 p-6`}
        style={{ width, height }}
      >
        <svg viewBox="0 0 24 24" className="w-12 h-12 fill-white" xmlns="http://www.w3.org/2000/svg">
          <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 00-.79-.05 6.34 6.34 0 00-6.34 6.34 6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.33-6.34V8.8a8.18 8.18 0 004.78 1.52V6.87a4.85 4.85 0 01-1.01-.18z"/>
        </svg>
        <a
          href={openUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 bg-white text-black font-semibold text-sm px-5 py-2.5 rounded-full hover:bg-gray-100 transition-colors"
        >
          <Play className="w-4 h-4" />
          {t('participation.watch_on_tiktok') || 'Watch on TikTok'}
        </a>
      </div>
    )
  }

  // ── YouTube ──
  if (videoInfo.platform === 'youtube') {
    if (videoInfo.videoId) {
      const iframeParams = new URLSearchParams()
      if (autoplay) iframeParams.append('autoplay', '1')
      iframeParams.append('rel', '0')
      iframeParams.append('modestbranding', '1')

      const embedUrl = `https://www.youtube.com/embed/${videoInfo.videoId}${iframeParams.toString() ? '?' + iframeParams.toString() : ''}`

      return (
        <iframe
          src={embedUrl}
          className={`${className} rounded-xl`}
          style={{ width, height }}
          frameBorder="0"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen={allowFullscreen}
          title="YouTube video"
        />
      )
    }

    return (
      <iframe
        src={videoInfo.originalUrl}
        className={`${className} rounded-xl`}
        style={{ width, height }}
        frameBorder="0"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen={allowFullscreen}
        title="YouTube video"
      />
    )
  }

  // ── Vimeo ──
  if (videoInfo.platform === 'vimeo') {
    const iframeParams = new URLSearchParams()
    if (autoplay) iframeParams.append('autoplay', '1')

    const embedUrl = videoInfo.embedUrl.startsWith('https://player.vimeo.com')
      ? `${videoInfo.embedUrl}${iframeParams.toString() ? '?' + iframeParams.toString() : ''}`
      : videoInfo.embedUrl

    return (
      <iframe
        src={embedUrl}
        className={`${className} rounded-xl`}
        style={{ width, height }}
        frameBorder="0"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen={allowFullscreen}
        title="Vimeo video"
      />
    )
  }

  // ── Facebook ──
  if (videoInfo.platform === 'facebook') {
    return (
      <iframe
        src={videoInfo.embedUrl}
        className={`${className} rounded-xl`}
        style={{ width, height }}
        frameBorder="0"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen={allowFullscreen}
        title="Facebook video"
      />
    )
  }

  // ── Other unsupported platforms ──
  return (
    <div className={`flex flex-col items-center justify-center bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-6 ${className}`} style={{ width, height }}>
      <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center mb-3">
        <ExternalLink className="w-5 h-5 text-red-500" />
      </div>
      <p className="text-red-600 dark:text-red-400 text-sm font-medium text-center">
        {t('participation.unsupported_platform') || 'Link not allowed'}
      </p>
    </div>
  )
}
