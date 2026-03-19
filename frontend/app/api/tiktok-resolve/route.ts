import { NextRequest, NextResponse } from 'next/server'

/**
 * API route pour résoudre les URLs courtes TikTok
 * GET /api/tiktok-resolve?url=https://vm.tiktok.com/xxx
 *
 * Suit la première redirection pour extraire l'ID vidéo de l'URL complète
 */
export async function GET(request: NextRequest) {
  const url = request.nextUrl.searchParams.get('url')

  if (!url) {
    return NextResponse.json({ error: 'Missing url parameter' }, { status: 400 })
  }

  try {
    // Extraire directement l'ID si l'URL est déjà complète
    const directMatch = url.match(/\/video\/(\d+)/)
    if (directMatch && directMatch[1]) {
      return NextResponse.json({ videoId: directMatch[1], source: 'direct' })
    }

    // Suivre la redirection SANS follow (juste lire le Location header)
    const res = await fetch(url, {
      method: 'HEAD',
      redirect: 'manual',
      signal: AbortSignal.timeout(10000),
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; MyHigh5Bot/1.0)'
      }
    })

    const location = res.headers.get('location')

    if (location) {
      // Extraire l'ID vidéo de l'URL de redirection
      const videoIdMatch = location.match(/\/video\/(\d+)/)
      if (videoIdMatch && videoIdMatch[1]) {
        return NextResponse.json({ videoId: videoIdMatch[1], fullUrl: location, source: 'redirect' })
      }

      // Si la première redirection ne contient pas l'ID, suivre une fois de plus
      if (location.includes('tiktok.com')) {
        const res2 = await fetch(location, {
          method: 'HEAD',
          redirect: 'manual',
          signal: AbortSignal.timeout(10000),
          headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; MyHigh5Bot/1.0)'
          }
        })

        const location2 = res2.headers.get('location')
        if (location2) {
          const videoIdMatch2 = location2.match(/\/video\/(\d+)/)
          if (videoIdMatch2 && videoIdMatch2[1]) {
            return NextResponse.json({ videoId: videoIdMatch2[1], fullUrl: location2, source: 'redirect2' })
          }
        }
      }
    }

    return NextResponse.json({ error: 'Could not resolve TikTok video ID' }, { status: 404 })
  } catch (err: any) {
    console.error('TikTok resolve error:', err.message)
    return NextResponse.json({ error: err.message || 'Resolution failed' }, { status: 500 })
  }
}
