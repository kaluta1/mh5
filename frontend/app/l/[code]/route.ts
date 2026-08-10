import { NextRequest, NextResponse } from 'next/server'
import { getServerApiBase } from '@/lib/share-preview-server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy short-link redirects to FastAPI. Next.js external rewrites return 500 for 302
 * responses, so this route handler forwards Location + Set-Cookie explicitly.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ code: string }> }
) {
  const { code } = await params
  if (!code || !/^[0-9A-Za-z]+$/.test(code)) {
    return new NextResponse('This share link is invalid or no longer available.', {
      status: 404,
    })
  }

  const apiBase = getServerApiBase()
  const forwardedFor =
    request.headers.get('x-forwarded-for') ||
    request.headers.get('x-real-ip') ||
    ''
  const ua = request.headers.get('user-agent') || ''
  const referer = request.headers.get('referer') || ''

  const fetchUpstream = () =>
    fetch(`${apiBase}/api/v1/l/${encodeURIComponent(code)}`, {
      method: 'GET',
      redirect: 'manual',
      cache: 'no-store',
      signal: AbortSignal.timeout(8000),
      headers: {
        'x-forwarded-for': forwardedFor,
        'user-agent': ua,
        referer,
      },
    })

  try {
    let upstream: Response | null = null
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        upstream = await fetchUpstream()
        break
      } catch (err) {
        if (attempt === 2) throw err
        await new Promise((r) => setTimeout(r, 400 * (attempt + 1)))
      }
    }
    if (!upstream) {
      return NextResponse.json({ error: 'Unable to resolve share link' }, { status: 502 })
    }

    if (upstream.status >= 300 && upstream.status < 400) {
      const location = upstream.headers.get('location')
      if (!location) {
        return NextResponse.json({ error: 'Redirect missing location' }, { status: 502 })
      }

      const response = NextResponse.redirect(location, upstream.status)
      const cookies =
        typeof upstream.headers.getSetCookie === 'function'
          ? upstream.headers.getSetCookie()
          : []
      if (cookies.length > 0) {
        for (const cookie of cookies) {
          response.headers.append('set-cookie', cookie)
        }
      } else {
        const single = upstream.headers.get('set-cookie')
        if (single) {
          response.headers.set('set-cookie', single)
        }
      }
      response.headers.set('cache-control', 'no-store')
      return response
    }

    if (upstream.status === 404) {
      return new NextResponse('This share link is invalid or no longer available.', {
        status: 404,
      })
    }

    const body = await upstream.text()
    return new NextResponse(body || 'Unable to resolve share link.', {
      status: upstream.status,
    })
  } catch (error) {
    console.error('Short link proxy error:', error)
    return NextResponse.json({ error: 'Unable to resolve share link' }, { status: 502 })
  }
}
