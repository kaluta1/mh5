'use client'

import React, { useState, useEffect, useRef } from 'react'
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
  embedHtml: string | null
  loading: boolean
  failed: boolean
}

function TikTokOEmbed({
  embedHtml,
  originalUrl,
  title,
  className,
  width,
  height,
}: {
  embedHtml: string
  originalUrl?: string
  title?: string | null
  className: string
  width: string | number
  height: string | number
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const fallbackHtml = `
      <blockquote
        class="tiktok-embed"
        cite="${originalUrl || ''}"
        style="max-width: 605px; min-width: 325px; margin: 0 auto;"
      >
        <section>
          <a target="_blank" href="${originalUrl || '#'}">${title || 'Watch this video on TikTok'}</a>
        </section>
      </blockquote>
    `

    const sanitizedHtml = (embedHtml || fallbackHtml).replace(/<script[\s\S]*?<\/script>/gi, '').trim()
    container.innerHTML = sanitizedHtml

    const script = document.createElement('script')
    script.src = 'https://www.tiktok.com/embed.js'
    script.async = true
    script.setAttribute('data-tiktok-embed', 'true')
    container.appendChild(script)

    return () => {
      container.innerHTML = ''
    }
  }, [embedHtml, originalUrl, title])

  return (
    <div
      className={`${className} bg-black rounded-xl overflow-auto`}
      style={{ width, height, minHeight: '500px' }}
    >
      <div ref={containerRef} className="w-full h-full flex items-center justify-center" />
    </div>
  )
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
    embedHtml: null,
    loading: false,
    failed: false,
  })

  useEffect(() => {
    if (!url) return

    setMeta(m => ({ ...m, loading: true, failed: false }))

    fetch(`/tiktok-resolve?url=${encodeURIComponent(url)}`)
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
          embedHtml: data.embedHtml || null,
          loading: false,
          failed: !data.videoId && !data.thumbnailUrl && !data.embedHtml,
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
    const resolvedTikTokId =
      tiktokMeta.videoId && /^\d+$/.test(tiktokMeta.videoId)
        ? tiktokMeta.videoId
        : (videoInfo.videoId && /^\d+$/.test(videoInfo.videoId) ? videoInfo.videoId : null)

    if (tiktokMeta.loading) {
      return (
        <div className={`${className} flex flex-col items-center justify-center bg-black rounded-xl`} style={{ width, height }}>
          <Loader2 className="w-8 h-8 text-white animate-spin mb-3" />
          <p className="text-white/60 text-sm">{t('common.loading') || 'Loading...'}</p>
        </div>
      )
    }

    // Prefer in-page playback whenever TikTok provides a valid embed ID.
    if (resolvedTikTokId) {
      return (
        <div
          className={`${className} flex items-center justify-center bg-black rounded-xl overflow-hidden`}
          style={{ width, height }}
        >
          <iframe
            src={`https://www.tiktok.com/embed/v2/${resolvedTikTokId}`}
            className="rounded-lg"
            style={{ width: '100%', height: '100%', minHeight: '500px', border: 'none' }}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen={allowFullscreen}
            title="TikTok video"
          />
        </div>
      )
    }

    if (tiktokMeta.embedHtml) {
      return (
        <TikTokOEmbed
          embedHtml={tiktokMeta.embedHtml}
          originalUrl={openUrl}
          title={tiktokMeta.title}
          className={className}
          width={width}
          height={height}
        />
      )
    }

    if (openUrl) {
      return (
        <TikTokOEmbed
          embedHtml=""
          originalUrl={openUrl}
          title={tiktokMeta.title}
          className={className}
          width={width}
          height={height}
        />
      )
    }

    // Fallback when TikTok does not expose an embeddable video ID.
    return (
      <div
        className={`${className} flex flex-col items-center justify-center bg-black rounded-xl overflow-hidden gap-4 p-6`}
        style={{ width, height }}
      >
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
