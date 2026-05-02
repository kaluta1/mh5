import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Forces the maintenance experience for everyone (logged out or logged in — no bypass).
 *
 * Defaults to ON when IS_MAINTENANCE_MODE is unset/empty → redirect users to `/maintenance`.
 * Set IS_MAINTENANCE_MODE=false | 0 | off | no on the deployment to serve the full app again.
 */
function isMaintenanceModeEnabled(): boolean {
    const v = process.env.IS_MAINTENANCE_MODE?.trim().toLowerCase()
    if (v === undefined || v === '') {
        return true
    }
    if (['false', '0', 'off', 'no'].includes(v)) {
        return false
    }
    if (['true', '1', 'on', 'yes'].includes(v)) {
        return true
    }
    return true
}

export function middleware(request: NextRequest) {
    const isMaintenanceMode = isMaintenanceModeEnabled()

    // If maintenance mode is active — only the maintenance shell + assets needed to render it.
    // No dashboards, login, API, etc. Everything else serves the maintenance UI.
    if (isMaintenanceMode) {
        const { pathname } = request.nextUrl

        const allowedPrefixes = [
            '/maintenance',
            '/_next',
            '/static',
            '/images',
        ]
        const allowedExact = new Set([
            '/favicon.ico',
            '/thumbnails.png',
            '/robots.txt',
        ])

        const isAllowedAsset =
            allowedExact.has(pathname) ||
            allowedPrefixes.some((prefix) => pathname.startsWith(`${prefix}/`) || pathname === prefix)

        if (isAllowedAsset) {
            return NextResponse.next()
        }

        // Temporary redirect so the browser URL shows /maintenance (works with auth cookies; no SPA escape).
        const response = NextResponse.redirect(new URL('/maintenance', request.url), 307)
        response.headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive')
        response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate')
        response.headers.set('Pragma', 'no-cache')
        response.headers.set('Expires', '0')
        response.headers.set('Retry-After', '3600')
        return response
    }

    // If NOT in maintenance mode
    // Optional: Redirect /maintenance to / if accessed directly?
    // For now, we just proceed.

    return NextResponse.next()
}

export const config = {
    matcher: [
        /*
         * Match all request paths except for the ones starting with:
         * - _next/static (static files)
         * - _next/image (image optimization files)
         */
        '/((?!_next/static|_next/image).*)',
    ],
}
