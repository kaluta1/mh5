import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Share links (/s/f, /s/c) are handled by route.ts handlers that return raw OG HTML.
 * Do not redirect crawlers away from these paths.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (pathname === '/maintenance' || pathname.startsWith('/maintenance/')) {
    return NextResponse.redirect(new URL('/', request.url))
  }

  if (pathname.startsWith('/s/f/') || pathname.startsWith('/s/c/')) {
    const response = NextResponse.next()
    response.headers.set('x-myhigh5-share-route', '1')
    return response
  }

  // Next.js redirect sources are case-insensitive — do NOT use next.config redirects for
  // /dashboard/myHigh5 → /dashboard/myhigh5 (that loops on the canonical lowercase URL).
  if (/^\/dashboard\/myhigh5/i.test(pathname)) {
    const suffix = pathname.replace(/^\/dashboard\/myhigh5/i, '')
    const canonical = `/dashboard/myhigh5${suffix}`
    if (canonical !== pathname) {
      return NextResponse.redirect(new URL(`${canonical}${request.nextUrl.search}`, request.url))
    }
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image).*)'],
}
