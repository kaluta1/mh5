import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Share links (/s/f, /s/c) are handled by route.ts handlers that return raw OG HTML.
 * Do not redirect crawlers away from these paths.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  if (pathname.startsWith('/s/f/') || pathname.startsWith('/s/c/')) {
    const response = NextResponse.next()
    response.headers.set('x-myhigh5-share-route', '1')
    return response
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/s/f/:path*', '/s/c/:path*'],
}
