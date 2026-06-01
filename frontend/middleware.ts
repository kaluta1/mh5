import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const MAINTENANCE_COOKIE = 'mh5_maintenance_bypass'
const BYPASS_QUERY_PARAM = 'maintenance_bypass'

function envEnabled(value: string | undefined): boolean {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').trim().toLowerCase())
}

function isPublicAsset(pathname: string): boolean {
  return (
    pathname.startsWith('/_next/') ||
    pathname.startsWith('/assets/') ||
    pathname.startsWith('/images/') ||
    pathname.startsWith('/icons/') ||
    pathname === '/favicon.ico' ||
    pathname === '/robots.txt' ||
    pathname === '/sitemap.xml' ||
    /\.[a-zA-Z0-9]+$/.test(pathname)
  )
}

/**
 * Share links (/s/f, /s/c) are handled by route.ts handlers that return raw OG HTML.
 * Do not redirect crawlers away from these paths.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const maintenanceEnabled = envEnabled(process.env.MAINTENANCE_MODE)
  const bypassToken = process.env.MAINTENANCE_BYPASS_TOKEN?.trim()
  const bypassFromQuery = request.nextUrl.searchParams.get(BYPASS_QUERY_PARAM)
  const hasBypassCookie =
    Boolean(bypassToken) && request.cookies.get(MAINTENANCE_COOKIE)?.value === bypassToken

  if (maintenanceEnabled && bypassToken && bypassFromQuery === bypassToken) {
    const redirectUrl = request.nextUrl.clone()
    redirectUrl.searchParams.delete(BYPASS_QUERY_PARAM)
    if (redirectUrl.pathname === '/maintenance') {
      redirectUrl.pathname = '/'
    }

    const response = NextResponse.redirect(redirectUrl)
    response.cookies.set(MAINTENANCE_COOKIE, bypassToken, {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: 60 * 60 * 24 * 7,
    })
    return response
  }

  if (
    maintenanceEnabled &&
    pathname !== '/maintenance' &&
    !pathname.startsWith('/api/') &&
    !isPublicAsset(pathname) &&
    !hasBypassCookie
  ) {
    const maintenanceUrl = request.nextUrl.clone()
    maintenanceUrl.pathname = '/maintenance'
    maintenanceUrl.search = ''
    return NextResponse.redirect(maintenanceUrl)
  }

  if (pathname.startsWith('/s/f/') || pathname.startsWith('/s/c/')) {
    const response = NextResponse.next()
    response.headers.set('x-myhigh5-share-route', '1')
    return response
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image).*)'],
}
