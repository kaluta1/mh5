/**
 * Utilitaires pour gérer les URLs de plateformes vidéo (YouTube, Vimeo, TikTok, Facebook)
 */

export type VideoPlatform = 'youtube' | 'vimeo' | 'tiktok' | 'facebook' | 'direct' | 'unknown'

export interface VideoInfo {
  platform: VideoPlatform
  embedUrl: string
  originalUrl: string
  videoId?: string
}

/**
 * Détecte si une URL est une URL de plateforme vidéo supportée
 */
export function detectVideoPlatform(url: string | null | undefined): VideoPlatform {
  if (!url || typeof url !== 'string') return 'unknown'
  
  const lowerUrl = url.toLowerCase().trim()
  
  // YouTube (incluant YouTube Shorts)
  if (lowerUrl.includes('youtube.com') || lowerUrl.includes('youtu.be') || lowerUrl.includes('youtube.com/shorts')) {
    return 'youtube'
  }
  
  // Vimeo
  if (lowerUrl.includes('vimeo.com')) {
    return 'vimeo'
  }
  
  // TikTok
  if (lowerUrl.includes('tiktok.com')) {
    return 'tiktok'
  }
  
  // Facebook
  if (lowerUrl.includes('facebook.com') || lowerUrl.includes('fb.com') || lowerUrl.includes('fb.watch')) {
    return 'facebook'
  }
  
  // Vidéo directe (fichier vidéo)
  const videoExtensions = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v']
  if (videoExtensions.some(ext => lowerUrl.includes(ext))) {
    return 'direct'
  }
  
  return 'unknown'
}

/**
 * Extrait l'ID vidéo d'une URL YouTube
 */
function extractYouTubeId(url: string | null | undefined): string | null {
  if (!url || typeof url !== 'string') return null
  
  const lowerUrl = url.toLowerCase()
  
  // YouTube Shorts: youtube.com/shorts/VIDEO_ID
  const shortsMatch = lowerUrl.match(/youtube\.com\/shorts\/([^&\n?#\/]+)/)
  if (shortsMatch && shortsMatch[1]) {
    return shortsMatch[1]
  }
  
  // YouTube standard formats
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/,
    /youtube\.com\/watch\?.*v=([^&\n?#]+)/
  ]
  
  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match && match[1]) {
      return match[1]
    }
  }
  
  return null
}

/**
 * Extrait l'ID vidéo d'une URL Vimeo
 */
function extractVimeoId(url: string | null | undefined): string | null {
  if (!url || typeof url !== 'string') return null
  
  const patterns = [
    /vimeo\.com\/(\d+)/,
    /vimeo\.com\/video\/(\d+)/,
    /player\.vimeo\.com\/video\/(\d+)/
  ]
  
  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match && match[1]) {
      return match[1]
    }
  }
  
  return null
}

/**
 * Extrait l'ID vidéo d'une URL TikTok
 */
function extractTikTokId(url: string | null | undefined): string | null {
  if (!url || typeof url !== 'string') return null
  
  // TikTok URLs: https://www.tiktok.com/@username/video/1234567890
  const pattern = /tiktok\.com\/.*\/video\/(\d+)/
  const match = url.match(pattern)
  return match && match[1] ? match[1] : null
}

/**
 * Extrait l'ID vidéo d'une URL Facebook
 */
function extractFacebookId(url: string | null | undefined): string | null {
  if (!url || typeof url !== 'string') return null
  
  // Facebook URLs peuvent être complexes
  // Format: https://www.facebook.com/watch/?v=1234567890
  // ou: https://www.facebook.com/username/videos/1234567890/
  // ou: https://fb.watch/xxxxx/
  const patterns = [
    /facebook\.com\/watch\/\?v=(\d+)/,
    /facebook\.com\/.*\/videos\/(\d+)/,
    /fb\.watch\/([a-zA-Z0-9]+)/
  ]
  
  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match && match[1]) {
      return match[1]
    }
  }
  
  return null
}

/**
 * Convertit une URL de plateforme vidéo en URL embed
 */
export function convertToEmbedUrl(url: string | null | undefined): VideoInfo {
  if (!url) {
    return {
      platform: 'unknown',
      embedUrl: '',
      originalUrl: ''
    }
  }
  
  const platform = detectVideoPlatform(url)
  const originalUrl = url.trim()
  
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
      break
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
      break
    }
    
    case 'tiktok': {
      const videoId = extractTikTokId(originalUrl)
      if (videoId) {
        // TikTok embed nécessite l'URL complète
        return {
          platform: 'tiktok',
          embedUrl: originalUrl, // TikTok utilise l'URL complète pour l'embed
          originalUrl,
          videoId
        }
      }
      break
    }
    
    case 'facebook': {
      const videoId = extractFacebookId(originalUrl)
      if (videoId) {
        // Facebook embed nécessite l'URL complète avec certains paramètres
        const embedUrl = originalUrl.includes('fb.watch') 
          ? `https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(originalUrl)}`
          : `https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(originalUrl)}&show_text=false&width=500`
        return {
          platform: 'facebook',
          embedUrl,
          originalUrl,
          videoId
        }
      }
      break
    }
    
    case 'direct': {
      return {
        platform: 'direct',
        embedUrl: originalUrl,
        originalUrl
      }
    }
  }
  
  return {
    platform: 'unknown',
    embedUrl: originalUrl,
    originalUrl
  }
}

/**
 * Vérifie si une URL est une URL de plateforme vidéo valide
 */
export function isValidVideoUrl(url: string | null | undefined): boolean {
  if (!url || typeof url !== 'string') return false
  const platform = detectVideoPlatform(url)
  return platform !== 'unknown'
}

