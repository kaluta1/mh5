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

/**
 * Résout une URL TikTok (courte ou longue) en ID numérique
 * Utilise l'API route /api/tiktok-resolve qui suit les redirections côté serveur
 */
function useTikTokResolve(url: string | undefined, videoId: string | undefined) {
  const [resolvedId, setResolvedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    // Si on a déjà un ID numérique, pas besoin de résoudre
    if (videoId && /^\d+$/.test(videoId)) {
      setResolvedId(videoId)
      return
    }

    if (!url) return

    setLoading(true)
    setFailed(false)

    // Utiliser notre API route serveur pour résoudre l'URL
    fetch(`/api/tiktok-resolve?url=${encodeURIComponent(url)}`)
      .then(res => {
        if (!res.ok) throw new Error('Resolve failed')
        return res.json()
      })
      .then(data => {
        if (data.videoId) {
          setResolvedId(data.videoId)
        } else {
          setFailed(true)
        }
      })
      .catch(() => {
        setFailed(true)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [url, videoId])

  return { resolvedId, loading, failed }
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
  const [iframeError, setIframeError] = useState(false)

  const cleanedUrl = url ? cleanVideoUrl(url) : ''
  const videoInfo: VideoInfo = cleanedUrl ? convertToEmbedUrl(cleanedUrl) : { platform: 'unknown', embedUrl: '', originalUrl: '' }

  // Résoudre TikTok URL courte → ID numérique
  const tiktokResolve = useTikTokResolve(
    videoInfo.platform === 'tiktok' ? videoInfo.originalUrl : undefined,
    videoInfo.platform === 'tiktok' ? videoInfo.videoId : undefined
  )

  if (!url) {
    return (
      <div className={`flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-lg ${className}`} style={{ width, height }}>
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          {t('participation.invalid_url') || 'URL vidéo non valide'}
        </p>
      </div>
    )
  }

  // ── Vidéo directe ──
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

  // ── Plateforme inconnue / non autorisée ──
  if (videoInfo.platform === 'unknown') {
    return (
      <div className={`flex flex-col items-center justify-center bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-6 ${className}`} style={{ width, height }}>
        <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center mb-3">
          <ExternalLink className="w-5 h-5 text-red-500" />
        </div>
        <p className="text-red-600 dark:text-red-400 text-sm font-medium text-center">
          {t('participation.unsupported_platform') || 'Lien non autorisé'}
        </p>
        <p className="text-red-400 dark:text-red-500 text-xs mt-1 text-center">
          {t('participation.only_youtube_tiktok') || 'Seuls YouTube et TikTok sont acceptés'}
        </p>
      </div>
    )
  }

  // ── TikTok ──
  if (videoInfo.platform === 'tiktok') {
    // Chargement de la résolution
    if (tiktokResolve.loading) {
      return (
        <div className={`${className} flex flex-col items-center justify-center bg-black rounded-xl`} style={{ width, height }}>
          <Loader2 className="w-8 h-8 text-white animate-spin mb-3" />
          <p className="text-white/60 text-sm">{t('common.loading') || 'Chargement...'}</p>
        </div>
      )
    }

    // ID numérique résolu → iframe embed
    const tiktokId = tiktokResolve.resolvedId
    if (tiktokId && /^\d+$/.test(tiktokId) && !iframeError) {
      return (
        <div className={`${className} flex items-center justify-center bg-black rounded-xl overflow-hidden`} style={{ width, height }}>
          <iframe
            src={`https://www.tiktok.com/embed/v2/${tiktokId}`}
            className="rounded-lg"
            style={{ width: '100%', maxWidth: '325px', height: '100%', minHeight: '500px', border: 'none' }}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen={allowFullscreen}
            title="TikTok video"
            onError={() => setIframeError(true)}
          />
        </div>
      )
    }

    // Fallback: resolution failed or no numeric ID — show a direct link to TikTok
    const tiktokFallbackUrl = videoInfo.originalUrl
    return (
      <div
        className={`${className} flex flex-col items-center justify-center bg-black rounded-xl overflow-hidden gap-4 p-6`}
        style={{ width, height }}
      >
        {/* TikTok logo-like icon */}
        <svg viewBox="0 0 24 24" className="w-12 h-12 fill-white" xmlns="http://www.w3.org/2000/svg">
          <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 00-.79-.05 6.34 6.34 0 00-6.34 6.34 6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.33-6.34V8.8a8.18 8.18 0 004.78 1.52V6.87a4.85 4.85 0 01-1.01-.18z"/>
        </svg>
        <p className="text-white/80 text-sm text-center font-medium">
          {t('participation.tiktok_preview_unavailable') || 'Preview unavailable — watch on TikTok'}
        </p>
        <a
          href={tiktokFallbackUrl}
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

  // ── YouTube (tous formats) ──
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

    // YouTube URL reconnue mais ID non extrait → essayer d'embed l'URL directement
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

  // ── Autres (Instagram, Snapchat) → non autorisé ──
  return (
    <div className={`flex flex-col items-center justify-center bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-6 ${className}`} style={{ width, height }}>
      <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center mb-3">
        <ExternalLink className="w-5 h-5 text-red-500" />
      </div>
      <p className="text-red-600 dark:text-red-400 text-sm font-medium text-center">
        {t('participation.unsupported_platform') || 'Lien non autorisé'}
      </p>
    </div>
  )
}
