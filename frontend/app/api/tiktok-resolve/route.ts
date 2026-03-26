import { NextRequest, NextResponse } from 'next/server'

/**
 * API route to resolve short TikTok URLs into a numeric video ID.
 * Handles all TikTok short-link domains: vt / vm / t / v.tiktok.com
 * GET /api/tiktok-resolve?url=https://vt.tiktok.com/ZSuwmaM8B/
 */

const BROWSER_HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
  'Accept-Language': 'en-US,en;q=0.9',
  'Accept-Encoding': 'gzip, deflate, br',
  'Cache-Control': 'no-cache',
  'Pragma': 'no-cache',
  'Sec-Fetch-Dest': 'document',
  'Sec-Fetch-Mode': 'navigate',
  'Sec-Fetch-Site': 'none',
  'Upgrade-Insecure-Requests': '1',
}

/** Extract numeric video ID from any TikTok URL */
function extractVideoId(url: string): string | null {
  const m = url.match(/\/video\/(\d{10,25})/)
  return m ? m[1] : null
}

/** Follow redirects manually up to maxHops, returning the final URL */
async function followRedirects(startUrl: string, maxHops = 6): Promise<string> {
  let current = startUrl

  for (let i = 0; i < maxHops; i++) {
    // Try HEAD first (lighter)
    let location: string | null = null
    try {
      const res = await fetch(current, {
        method: 'HEAD',
        redirect: 'manual',
        signal: AbortSignal.timeout(8000),
        headers: BROWSER_HEADERS,
      })
      location = res.headers.get('location')
    } catch {
      // HEAD failed, try GET
    }

    // If HEAD gave no Location, try GET (some servers ignore HEAD)
    if (!location) {
      try {
        const res = await fetch(current, {
          method: 'GET',
          redirect: 'manual',
          signal: AbortSignal.timeout(8000),
          headers: BROWSER_HEADERS,
        })
        location = res.headers.get('location')

        // If still no Location, we've reached the final page
        if (!location) {
          // Check if the final URL itself contains a video ID
          const finalId = extractVideoId(res.url || current)
          if (finalId) return `https://www.tiktok.com/video/${finalId}`
          break
        }
      } catch {
        break
      }
    }

    // Resolve relative redirects
    if (location.startsWith('/')) {
      const base = new URL(current)
      location = `${base.protocol}//${base.host}${location}`
    }

    // If the redirect URL already has a video ID, we're done
    const id = extractVideoId(location)
    if (id) return location

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
    // Fast path: URL already contains a numeric video ID
    const directId = extractVideoId(url)
    if (directId) {
      return NextResponse.json({ videoId: directId, source: 'direct' })
    }

    // Follow the redirect chain to find the full TikTok URL
    const finalUrl = await followRedirects(url)
    const videoId = extractVideoId(finalUrl)

    if (videoId) {
      return NextResponse.json({ videoId, fullUrl: finalUrl, source: 'resolved' })
    }

    return NextResponse.json(
      { error: 'Could not resolve TikTok video ID', finalUrl },
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
