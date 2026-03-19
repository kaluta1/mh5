/**
 * Utilitaires pour gérer les URLs de plateformes vidéo
 * Plateformes acceptées : YouTube, TikTok, Vimeo, Facebook
 */

export type VideoPlatform = 'youtube' | 'tiktok' | 'vimeo' | 'facebook' | 'instagram' | 'snapchat' | 'direct' | 'unknown'

export interface VideoInfo {
  platform: VideoPlatform
  embedUrl: string
  originalUrl: string
  videoId?: string
}

/**
 * Nettoie une URL en extrayant uniquement la première URL valide
 * (supprime le texte parasite collé après le lien, ex: partage TikTok Lite)
 */
export function cleanVideoUrl(url: string | null | undefined): string {
  if (!url || typeof url !== 'string') return ''
  let cleaned = url.trim()

  // Gérer le double-encoding JSON : ["[\"https://youtu.be/xxx\"]"]
  // Essayer de parser comme JSON si ça commence par [ ou "
  let maxDepth = 3
  while (maxDepth-- > 0 && (cleaned.startsWith('[') || cleaned.startsWith('"'))) {
    try {
      const parsed = JSON.parse(cleaned)
      if (Array.isArray(parsed) && parsed.length > 0) {
        cleaned = String(parsed[0]).trim()
      } else if (typeof parsed === 'string') {
        cleaned = parsed.trim()
      } else {
        break
      }
    } catch {
      break
    }
  }

  // Extraire la première URL complète (http/https)
  const urlMatch = cleaned.match(/https?:\/\/[^\s"'<>\[\]]+/)
  return urlMatch ? urlMatch[0].replace(/\/+$/, '') : cleaned
}

/**
 * Détecte la plateforme vidéo d'une URL
 */
export function detectVideoPlatform(url: string | null | undefined): VideoPlatform {
  if (!url || typeof url !== 'string') return 'unknown'

  const lowerUrl = cleanVideoUrl(url).toLowerCase()

  // YouTube — tous les formats
  if (
    lowerUrl.includes('youtube.com') ||
    lowerUrl.includes('youtu.be') ||
    lowerUrl.includes('m.youtube.com') ||
    lowerUrl.includes('music.youtube.com') ||
    lowerUrl.includes('youtube-nocookie.com')
  ) {
    return 'youtube'
  }

  // TikTok — tous les formats
  if (lowerUrl.includes('tiktok.com')) {
    return 'tiktok'
  }

  // Vimeo
  if (lowerUrl.includes('vimeo.com')) {
    return 'vimeo'
  }

  // Facebook
  if (lowerUrl.includes('facebook.com') || lowerUrl.includes('fb.com') || lowerUrl.includes('fb.watch')) {
    return 'facebook'
  }

  // Instagram
  if (lowerUrl.includes('instagram.com') || lowerUrl.includes('instagr.am')) {
    return 'instagram'
  }

  // Snapchat
  if (lowerUrl.includes('snapchat.com') || lowerUrl.includes('snap.com')) {
    return 'snapchat'
  }

  // Vidéo directe (fichier vidéo)
  const videoExtensions = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v']
  if (videoExtensions.some(ext => lowerUrl.endsWith(ext) || lowerUrl.includes(ext + '?'))) {
    return 'direct'
  }

  return 'unknown'
}

/**
 * Extrait l'ID vidéo d'une URL YouTube
 * Supporte TOUS les formats : watch, shorts, live, embed, youtu.be, music, playlist, attribution_link, nocookie
 */
function extractYouTubeId(url: string): string | null {
  const trimmed = url.trim()

  const patterns = [
    /youtube\.com\/live\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/v\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})/,
    /youtu\.be\/([a-zA-Z0-9_-]{11})/,
    /m\.youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})/,
    /music\.youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})/,
    /youtube-nocookie\.com\/embed\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/attribution_link.*v(?:%3D|=)([a-zA-Z0-9_-]{11})/,
  ]

  for (const pattern of patterns) {
    const match = trimmed.match(pattern)
    if (match && match[1]) return match[1]
  }

  // Fallback: v= param
  const vParam = trimmed.match(/[?&]v=([a-zA-Z0-9_-]{11})/)
  if (vParam && vParam[1]) return vParam[1]

  return null
}

/**
 * Extrait l'ID vidéo d'une URL TikTok
 * Supporte TOUS les formats : @user/video/ID, vt/vm/t.tiktok.com, /t/ web format
 */
function extractTikTokId(url: string): string | null {
  const trimmed = url.trim()

  const patterns = [
    /tiktok\.com\/.*\/video\/(\d+)/,
    /tiktok\.com\/.*\/photo\/(\d+)/,
    /(?:vt|vm|t)\.tiktok\.com\/([a-zA-Z0-9_-]+)/,
    /tiktok\.com\/t\/([a-zA-Z0-9_-]+)/,
  ]

  for (const pattern of patterns) {
    const match = trimmed.match(pattern)
    if (match && match[1]) return match[1]
  }

  return null
}

/**
 * Extrait l'ID vidéo d'une URL Vimeo
 */
function extractVimeoId(url: string): string | null {
  const patterns = [
    /vimeo\.com\/(\d+)/,
    /vimeo\.com\/video\/(\d+)/,
    /player\.vimeo\.com\/video\/(\d+)/,
  ]
  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match && match[1]) return match[1]
  }
  return null
}

/**
 * Extrait l'ID vidéo d'une URL Facebook
 */
function extractFacebookId(url: string): string | null {
  const patterns = [
    /facebook\.com\/watch\/?\?v=(\d+)/,
    /facebook\.com\/.*\/videos\/(\d+)/,
    /facebook\.com\/reel\/(\d+)/,
    /fb\.watch\/([a-zA-Z0-9_-]+)/,
  ]
  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match && match[1]) return match[1]
  }
  return null
}

/**
 * Convertit une URL de plateforme vidéo en URL embed
 */
export function convertToEmbedUrl(url: string | null | undefined): VideoInfo {
  if (!url) {
    return { platform: 'unknown', embedUrl: '', originalUrl: '' }
  }

  // Nettoyer l'URL (supprime texte parasite ex: partage TikTok Lite)
  const cleanedUrl = cleanVideoUrl(url)
  const platform = detectVideoPlatform(cleanedUrl)
  const originalUrl = cleanedUrl

  switch (platform) {
    case 'youtube': {
      const videoId = extractYouTubeId(originalUrl)
      if (videoId) {
        return {
          platform: 'youtube',
          embedUrl: `https://www.youtube.com/embed/${videoId}`,
          originalUrl,
          videoId
        }
      }
      return { platform: 'youtube', embedUrl: originalUrl, originalUrl }
    }

    case 'tiktok': {
      const videoId = extractTikTokId(originalUrl)
      return {
        platform: 'tiktok',
        embedUrl: originalUrl,
        originalUrl,
        videoId: videoId || undefined
      }
    }

    case 'vimeo': {
      const videoId = extractVimeoId(originalUrl)
      if (videoId) {
        return {
          platform: 'vimeo',
          embedUrl: `https://player.vimeo.com/video/${videoId}`,
          originalUrl,
          videoId
        }
      }
      return { platform: 'vimeo', embedUrl: originalUrl, originalUrl }
    }

    case 'facebook': {
      const videoId = extractFacebookId(originalUrl)
      return {
        platform: 'facebook',
        embedUrl: `https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(originalUrl)}&show_text=false`,
        originalUrl,
        videoId: videoId || undefined
      }
    }

    case 'direct': {
      return { platform: 'direct', embedUrl: originalUrl, originalUrl }
    }
  }

  return { platform: 'unknown', embedUrl: originalUrl, originalUrl }
}

/**
 * Vérifie si une URL est un YouTube Short
 */
export function isYouTubeShort(url: string | null | undefined): boolean {
  if (!url || typeof url !== 'string') return false
  return /youtube\.com\/shorts\//i.test(url)
}

/**
 * Vérifie si une URL est une URL de plateforme vidéo valide (autorisée)
 * YouTube, TikTok, Vimeo et Facebook sont acceptés
 */
export function isValidVideoUrl(url: string | null | undefined): boolean {
  if (!url || typeof url !== 'string') return false
  const platform = detectVideoPlatform(url)
  return platform === 'youtube' || platform === 'tiktok' || platform === 'vimeo' || platform === 'facebook'
}
