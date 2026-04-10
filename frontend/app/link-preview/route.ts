import { NextRequest, NextResponse } from 'next/server'

function cleanUrl(rawUrl: string): string {
  const trimmed = rawUrl.trim()
  const match = trimmed.match(/https?:\/\/[^\s"'<>\[\]]+/i)
  return match ? match[0].replace(/\/+$/, '') : trimmed
}

function extractMetaTag(html: string, patterns: RegExp[]): string | undefined {
  for (const pattern of patterns) {
    const match = html.match(pattern)
    if (match?.[1]) {
      return decodeHtmlEntities(match[1].trim())
    }
  }
  return undefined
}

function decodeHtmlEntities(value: string): string {
  return value
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
}

function decodeEscapedString(value: string): string {
  return decodeHtmlEntities(value)
    .replace(/\\u0026/g, '&')
    .replace(/\\u003d/g, '=')
    .replace(/\\u002F/g, '/')
    .replace(/\\\//g, '/')
}

function getYouTubeVideoId(url: string): string | undefined {
  const patterns = [
    /youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})/i,
    /youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})/i,
    /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/i,
    /youtube\.com\/live\/([a-zA-Z0-9_-]{11})/i,
    /youtu\.be\/([a-zA-Z0-9_-]{11})/i,
    /m\.youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})/i,
  ]

  for (const pattern of patterns) {
    const match = url.match(pattern)
    if (match?.[1]) return match[1]
  }

  return undefined
}

function isPrivateHost(hostname: string): boolean {
  const lower = hostname.toLowerCase()
  return (
    lower === 'localhost' ||
    lower === '127.0.0.1' ||
    lower === '0.0.0.0' ||
    lower.endsWith('.local')
  )
}

function buildJsonResponse(payload: Record<string, unknown>, maxAgeSeconds: number = 3600) {
  return NextResponse.json(payload, {
    headers: {
      'Cache-Control': `public, s-maxage=${maxAgeSeconds}, stale-while-revalidate=86400`,
    },
  })
}

function getSiteNameFromHost(hostname: string): string {
  return hostname.replace(/^www\./, '')
}

function isTikTokHost(hostname: string): boolean {
  return /(^|\.)tiktok\.com$/i.test(hostname)
}

function isInstagramHost(hostname: string): boolean {
  return /(^|\.)instagram\.com$/i.test(hostname) || /(^|\.)instagr\.am$/i.test(hostname)
}

function isFacebookHost(hostname: string): boolean {
  return /(^|\.)facebook\.com$/i.test(hostname) || /(^|\.)fb\.com$/i.test(hostname) || /(^|\.)fb\.watch$/i.test(hostname)
}

async function fetchRemote(url: string) {
  return fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (compatible; MyHigh5LinkPreview/1.0)',
      Accept: 'text/html,application/xhtml+xml,application/json',
      'Accept-Language': 'en-US,en;q=0.9',
      'Cache-Control': 'no-cache',
      Pragma: 'no-cache',
    },
    redirect: 'follow',
    next: { revalidate: 3600 },
  })
}

function extractPreviewFromHtml(html: string, normalizedUrl: string, fallbackSiteName: string) {
  const title =
    extractMetaTag(html, [
      /<meta[^>]+property=["']og:title["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+property=["']og:title["']/i,
      /<meta[^>]+name=["']twitter:title["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+name=["']twitter:title["']/i,
      /<title[^>]*>([^<]+)<\/title>/i,
    ]) || fallbackSiteName

  const description =
    extractMetaTag(html, [
      /<meta[^>]+property=["']og:description["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+property=["']og:description["']/i,
      /<meta[^>]+name=["']twitter:description["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+name=["']twitter:description["']/i,
      /<meta[^>]+name=["']description["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+name=["']description["']/i,
    ]) || normalizedUrl

  const image =
    extractMetaTag(html, [
      /<meta[^>]+property=["']og:image["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+property=["']og:image["']/i,
      /<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+name=["']twitter:image["']/i,
      /"thumbnailUrl":"([^"]+)"/i,
      /"display_url":"([^"]+)"/i,
    ])

  const siteName =
    extractMetaTag(html, [
      /<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+property=["']og:site_name["']/i,
    ]) || fallbackSiteName

  return {
    title,
    description,
    image: image ? decodeEscapedString(image) : undefined,
    siteName,
    url: normalizedUrl,
  }
}

async function fetchHtmlPreview(normalizedUrl: string, targetUrl: URL, fallbackSiteName: string) {
  const response = await fetchRemote(normalizedUrl)

  if (!response.ok) {
    throw new Error('Failed to fetch target URL')
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('text/html')) {
    return {
      title: fallbackSiteName,
      description: normalizedUrl,
      siteName: fallbackSiteName,
      url: normalizedUrl,
    }
  }

  const html = await response.text()
  const preview = extractPreviewFromHtml(html, normalizedUrl, fallbackSiteName)

  return {
    ...preview,
    image: preview.image ? new URL(preview.image, normalizedUrl).toString() : undefined,
    siteName: preview.siteName || getSiteNameFromHost(targetUrl.hostname),
  }
}

export async function GET(request: NextRequest) {
  const rawUrl = request.nextUrl.searchParams.get('url')
  if (!rawUrl) {
    return NextResponse.json({ detail: 'Missing url parameter' }, { status: 400 })
  }

  let targetUrl: URL
  try {
    targetUrl = new URL(cleanUrl(rawUrl))
  } catch {
    return NextResponse.json({ detail: 'Invalid URL' }, { status: 400 })
  }

  if (!['http:', 'https:'].includes(targetUrl.protocol) || isPrivateHost(targetUrl.hostname)) {
    return NextResponse.json({ detail: 'URL not allowed' }, { status: 400 })
  }

  const normalizedUrl = targetUrl.toString()
  const youtubeVideoId = getYouTubeVideoId(normalizedUrl)
  const hostnameLabel = getSiteNameFromHost(targetUrl.hostname)

  if (youtubeVideoId) {
    try {
      const oembedResponse = await fetch(
        `https://www.youtube.com/oembed?url=${encodeURIComponent(normalizedUrl)}&format=json`,
        {
          headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; MyHigh5LinkPreview/1.0)',
          },
          next: { revalidate: 3600 },
        }
      )

      if (oembedResponse.ok) {
        const data = await oembedResponse.json()
        const thumb: string | undefined = data.thumbnail_url
        const hiRes =
          typeof thumb === 'string' && thumb.includes('hqdefault')
            ? thumb.replace('hqdefault', 'maxresdefault')
            : `https://img.youtube.com/vi/${youtubeVideoId}/maxresdefault.jpg`
        return buildJsonResponse({
          title: data.title || 'YouTube',
          description: '',
          image: hiRes,
          siteName: 'YouTube',
          url: normalizedUrl,
        })
      }
    } catch {
      // Fall through to static YouTube preview fallback below.
    }

    return buildJsonResponse({
      title: 'YouTube',
      description: '',
      image: `https://img.youtube.com/vi/${youtubeVideoId}/maxresdefault.jpg`,
      siteName: 'YouTube',
      url: normalizedUrl,
    })
  }

  if (isTikTokHost(targetUrl.hostname)) {
    try {
      const oembedResponse = await fetch(
        `https://www.tiktok.com/oembed?url=${encodeURIComponent(normalizedUrl)}`,
        {
          headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; MyHigh5LinkPreview/1.0)',
            Accept: 'application/json',
          },
          next: { revalidate: 3600 },
        }
      )

      if (oembedResponse.ok) {
        const data = await oembedResponse.json()
        return buildJsonResponse({
          title: data.title || 'TikTok',
          description: data.author_name ? `By ${data.author_name}` : normalizedUrl,
          image: data.thumbnail_url,
          siteName: data.provider_name || 'TikTok',
          url: normalizedUrl,
        })
      }
    } catch {
      // Fallback to HTML scraping below.
    }
  }

  if (isInstagramHost(targetUrl.hostname)) {
    try {
      const preview = await fetchHtmlPreview(normalizedUrl, targetUrl, 'Instagram')
      return buildJsonResponse({
        ...preview,
        siteName: 'Instagram',
      })
    } catch {
      // Fall through to generic handling.
    }
  }

  if (isFacebookHost(targetUrl.hostname)) {
    try {
      const preview = await fetchHtmlPreview(normalizedUrl, targetUrl, 'Facebook')
      return buildJsonResponse({
        ...preview,
        siteName: 'Facebook',
      })
    } catch {
      // Fall through to generic handling.
    }
  }

  try {
    const preview = await fetchHtmlPreview(normalizedUrl, targetUrl, hostnameLabel)
    return buildJsonResponse(preview)
  } catch {
    return buildJsonResponse(
      {
        title: hostnameLabel,
        description: normalizedUrl,
        siteName: hostnameLabel,
        url: normalizedUrl,
      },
      300
    )
  }
}
