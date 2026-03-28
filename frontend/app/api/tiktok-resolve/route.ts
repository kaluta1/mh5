import { NextRequest, NextResponse } from 'next/server'

/**
 * API route to resolve TikTok URLs and fetch oEmbed metadata (thumbnail, author, title).
 * GET /api/tiktok-resolve?url=https://www.tiktok.com/@user/video/12345
 */

const BROWSER_HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
  'Accept-Language': 'en-US,en;q=0.9',
  'Cache-Control': 'no-cache',
}

/** Extract numeric video ID from any full TikTok URL */
function extractVideoId(url: string): string | null {
  const m = url.match(/\/video\/(\d{10,25})/)
  return m ? m[1] : null
}

function extractVideoIdFromText(value: string | null | undefined): string | null {
  if (!value) return null

  const patterns = [
    /(?:https?:\/\/)?(?:www\.)?tiktok\.com\/@[^"'?\s]+\/video\/(\d{10,25})/i,
    /(?:https?:\/\/)?(?:m\.)?tiktok\.com\/v\/(\d{10,25})/i,
    /"videoId":"(\d{10,25})"/i,
    /"itemId":"(\d{10,25})"/i,
    /"embed_product_id":"(\d{10,25})"/i,
    /property=["']og:url["'][^>]+content=["'][^"']*\/video\/(\d{10,25})/i,
    /rel=["']canonical["'][^>]+href=["'][^"']*\/video\/(\d{10,25})/i,
  ]

  for (const pattern of patterns) {
    const match = value.match(pattern)
    if (match && match[1]) return match[1]
  }

  return null
}

/** Follow redirects manually up to maxHops, returning the final URL */
async function followRedirects(startUrl: string, maxHops = 6): Promise<string> {
  let current = startUrl

  for (let i = 0; i < maxHops; i++) {
    let location: string | null = null

    try {
      const res = await fetch(current, {
        method: 'HEAD',
        redirect: 'manual',
        signal: AbortSignal.timeout(6000),
        headers: BROWSER_HEADERS,
      })
      location = res.headers.get('location')
    } catch { /* ignore */ }

    if (!location) {
      try {
        const res = await fetch(current, {
          method: 'GET',
          redirect: 'manual',
          signal: AbortSignal.timeout(6000),
          headers: BROWSER_HEADERS,
        })
        location = res.headers.get('location')
        if (!location) break
      } catch {
        break
      }
    }

    if (location.startsWith('/')) {
      const base = new URL(current)
      location = `${base.protocol}//${base.host}${location}`
    }

    if (extractVideoId(location)) return location
    current = location
  }

  return current
}

async function resolveTikTokUrl(startUrl: string): Promise<{ resolvedUrl: string; videoId: string | null }> {
  const redirectResolvedUrl = await followRedirects(startUrl)
  const redirectVideoId = extractVideoId(redirectResolvedUrl) || extractVideoIdFromText(redirectResolvedUrl)
  if (redirectVideoId) {
    return { resolvedUrl: redirectResolvedUrl, videoId: redirectVideoId }
  }

  try {
    const response = await fetch(startUrl, {
      method: 'GET',
      redirect: 'follow',
      signal: AbortSignal.timeout(12000),
      headers: BROWSER_HEADERS,
    })

    const finalUrl = response.url || redirectResolvedUrl || startUrl
    const body = await response.text()
    const resolvedVideoId =
      extractVideoId(finalUrl) ||
      extractVideoIdFromText(finalUrl) ||
      extractVideoIdFromText(body)

    return {
      resolvedUrl: finalUrl,
      videoId: resolvedVideoId,
    }
  } catch {
    return {
      resolvedUrl: redirectResolvedUrl,
      videoId: null,
    }
  }
}

export async function GET(request: NextRequest) {
  const url = request.nextUrl.searchParams.get('url')

  if (!url) {
    return NextResponse.json({ error: 'Missing url parameter' }, { status: 400 })
  }

  try {
    // Resolve short URL to full URL first if needed
    let resolvedUrl = url
    const directId = extractVideoId(url)
    let resolvedVideoId = directId

    if (!directId) {
      const resolved = await resolveTikTokUrl(url)
      resolvedUrl = resolved.resolvedUrl
      resolvedVideoId = resolved.videoId
    }

    // Build a clean full TikTok URL for oEmbed
    const videoId = resolvedVideoId || extractVideoId(resolvedUrl) || extractVideoIdFromText(resolvedUrl)
    const oembedTargetUrl = videoId
      ? `https://www.tiktok.com/video/${videoId}`
      : resolvedUrl

    // Call TikTok's official oEmbed endpoint — returns thumbnail, author, title
    try {
      const oembedRes = await fetch(
        `https://www.tiktok.com/oembed?url=${encodeURIComponent(oembedTargetUrl)}`,
        {
          headers: { ...BROWSER_HEADERS, 'Accept': 'application/json' },
          signal: AbortSignal.timeout(8000),
        }
      )

      if (oembedRes.ok) {
        const data = await oembedRes.json()
        const oembedText = JSON.stringify(data)
        const embedHtml = typeof data.html === 'string' ? data.html : null
        const resolvedId =
          data.embed_product_id ||
          videoId ||
          extractVideoIdFromText(embedHtml) ||
          extractVideoIdFromText(oembedText) ||
          null
        return NextResponse.json({
          videoId: resolvedId,
          thumbnailUrl: data.thumbnail_url || null,
          authorName: data.author_name || null,
          title: data.title || null,
          embedHtml,
          source: 'oembed',
        })
      }
    } catch { /* oEmbed failed, return what we have */ }

    // oEmbed failed but we may still have the video ID
    if (videoId) {
      return NextResponse.json({ videoId, source: 'direct' })
    }

    return NextResponse.json(
      { error: 'Could not resolve TikTok video', finalUrl: resolvedUrl },
      { status: 404 }
    )
  } catch (err: any) {
    console.error('TikTok resolve error:', err.message)
    return NextResponse.json(
      { error: err.message || 'Resolution failed' },
      { status: 500 }
    )
  }
}
