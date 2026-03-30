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
        return NextResponse.json(
          {
            title: data.title || 'YouTube',
            description: data.author_name ? `By ${data.author_name}` : normalizedUrl,
            image: data.thumbnail_url || `https://img.youtube.com/vi/${youtubeVideoId}/hqdefault.jpg`,
            siteName: 'YouTube',
            url: normalizedUrl,
          },
          {
            headers: {
              'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400',
            },
          }
        )
      }
    } catch {
      // Fall through to static YouTube preview fallback below.
    }

    return NextResponse.json(
      {
        title: 'YouTube',
        description: normalizedUrl,
        image: `https://img.youtube.com/vi/${youtubeVideoId}/hqdefault.jpg`,
        siteName: 'YouTube',
        url: normalizedUrl,
      },
      {
        headers: {
          'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400',
        },
      }
    )
  }

  try {
    const response = await fetch(normalizedUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; MyHigh5LinkPreview/1.0)',
        Accept: 'text/html,application/xhtml+xml',
      },
      redirect: 'follow',
      next: { revalidate: 3600 },
    })

    if (!response.ok) {
      return NextResponse.json({ detail: 'Failed to fetch target URL' }, { status: 502 })
    }

    const contentType = response.headers.get('content-type') || ''
    if (!contentType.includes('text/html')) {
      return NextResponse.json(
        {
          title: targetUrl.hostname.replace(/^www\./, ''),
          description: normalizedUrl,
          siteName: targetUrl.hostname.replace(/^www\./, ''),
          url: normalizedUrl,
        },
        {
          headers: {
            'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400',
          },
        }
      )
    }

    const html = await response.text()
    const title =
      extractMetaTag(html, [
        /<meta[^>]+property=["']og:title["'][^>]+content=["']([^"]+)["']/i,
        /<meta[^>]+content=["']([^"]+)["'][^>]+property=["']og:title["']/i,
        /<title[^>]*>([^<]+)<\/title>/i,
      ]) || targetUrl.hostname.replace(/^www\./, '')
    const description =
      extractMetaTag(html, [
        /<meta[^>]+property=["']og:description["'][^>]+content=["']([^"]+)["']/i,
        /<meta[^>]+content=["']([^"]+)["'][^>]+property=["']og:description["']/i,
        /<meta[^>]+name=["']description["'][^>]+content=["']([^"]+)["']/i,
        /<meta[^>]+content=["']([^"]+)["'][^>]+name=["']description["']/i,
      ]) || normalizedUrl
    const image = extractMetaTag(html, [
      /<meta[^>]+property=["']og:image["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+property=["']og:image["']/i,
      /<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"]+)["']/i,
      /<meta[^>]+content=["']([^"]+)["'][^>]+name=["']twitter:image["']/i,
    ])
    const siteName =
      extractMetaTag(html, [
        /<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"]+)["']/i,
        /<meta[^>]+content=["']([^"]+)["'][^>]+property=["']og:site_name["']/i,
      ]) || targetUrl.hostname.replace(/^www\./, '')

    const imageUrl = image
      ? new URL(image, normalizedUrl).toString()
      : undefined

    return NextResponse.json(
      {
        title,
        description,
        image: imageUrl,
        siteName,
        url: normalizedUrl,
      },
      {
        headers: {
          'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400',
        },
      }
    )
  } catch {
    return NextResponse.json(
      {
        title: targetUrl.hostname.replace(/^www\./, ''),
        description: normalizedUrl,
        siteName: targetUrl.hostname.replace(/^www\./, ''),
        url: normalizedUrl,
      },
      {
        headers: {
          'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=3600',
        },
      }
    )
  }
}
