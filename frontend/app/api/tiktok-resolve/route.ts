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

export async function GET(request: NextRequest) {
  const url = request.nextUrl.searchParams.get('url')

  if (!url) {
    return NextResponse.json({ error: 'Missing url parameter' }, { status: 400 })
  }

  try {
    // Resolve short URL to full URL first if needed
    let resolvedUrl = url
    const directId = extractVideoId(url)
    if (!directId) {
      resolvedUrl = await followRedirects(url)
    }

    // Build a clean full TikTok URL for oEmbed
    const videoId = directId || extractVideoId(resolvedUrl)
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
        const resolvedId = data.embed_product_id || videoId || null
        return NextResponse.json({
          videoId: resolvedId,
          thumbnailUrl: data.thumbnail_url || null,
          authorName: data.author_name || null,
          title: data.title || null,
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
