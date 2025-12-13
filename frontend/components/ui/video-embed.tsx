'use client'

import React from 'react'
import { convertToEmbedUrl, VideoInfo } from '@/lib/utils/video-platforms'

interface VideoEmbedProps {
  url: string
  className?: string
  autoplay?: boolean
  allowFullscreen?: boolean
  width?: string | number
  height?: string | number
}

export function VideoEmbed({
  url,
  className = '',
  autoplay = false,
  allowFullscreen = true,
  width = '100%',
  height = '100%'
}: VideoEmbedProps) {
  const videoInfo: VideoInfo = convertToEmbedUrl(url)
  
  // Si c'est une vidéo directe, utiliser la balise <video>
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
  
  // Si la plateforme n'est pas supportée, retourner null ou un message d'erreur
  if (videoInfo.platform === 'unknown') {
    return (
      <div className={`flex items-center justify-center bg-gray-100 dark:bg-gray-800 ${className}`} style={{ width, height }}>
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          URL vidéo non supportée
        </p>
      </div>
    )
  }
  
  // TikTok nécessite un script spécial
  if (videoInfo.platform === 'tiktok') {
    return (
      <div className={className} style={{ width, height }}>
        <blockquote
          className="tiktok-embed"
          cite={videoInfo.originalUrl}
          data-video-id={videoInfo.videoId}
          style={{ maxWidth: '100%', minWidth: '325px' }}
        >
          <section>
            <a
              target="_blank"
              rel="noopener noreferrer"
              href={videoInfo.originalUrl}
            >
              Voir la vidéo sur TikTok
            </a>
          </section>
        </blockquote>
        <script async src="https://www.tiktok.com/embed.js"></script>
      </div>
    )
  }
  
  // Pour YouTube, Vimeo et Facebook, utiliser iframe
  const iframeParams = new URLSearchParams()
  if (autoplay) {
    iframeParams.append('autoplay', '1')
  }
  if (!allowFullscreen) {
    iframeParams.append('fs', '0')
  }
  
  // Paramètres spécifiques par plateforme
  if (videoInfo.platform === 'youtube') {
    iframeParams.append('rel', '0')
    iframeParams.append('modestbranding', '1')
  }
  
  const embedUrlWithParams = iframeParams.toString()
    ? `${videoInfo.embedUrl}?${iframeParams.toString()}`
    : videoInfo.embedUrl
  
  return (
    <iframe
      src={embedUrlWithParams}
      className={className}
      style={{ width, height }}
      frameBorder="0"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowFullScreen={allowFullscreen}
      title="Video embed"
    />
  )
}

