import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Forces the maintenance experience by default.
 *
 * Defaults to ON when IS_MAINTENANCE_MODE is unset/empty → redirect users to `/maintenance`.
 * Set IS_MAINTENANCE_MODE=false | 0 | off | no on the deployment to serve the full app again.
 *
 * Optional private bypass (for developers/testers):
 * - Set MAINTENANCE_BYPASS_TOKEN in server env.
 * - Open a secret URL: `/?maintenance_bypass=<token>`
 * - Middleware stores an httpOnly cookie and allows full app for that browser only.
 * - Revoke in that browser: `/?maintenance_lock=1`
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

const MAINT_BYPASS_COOKIE = 'mh5_maintenance_bypass'

function getBypassToken(): string {
    return (process.env.MAINTENANCE_BYPASS_TOKEN || '').trim()
}

function hasValidBypassCookie(request: NextRequest, token: string): boolean {
    if (!token) return false
    return request.cookies.get(MAINT_BYPASS_COOKIE)?.value === token
}

function maintenanceHeaders(response: NextResponse): NextResponse {
    response.headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive')
    response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate')
    response.headers.set('Pragma', 'no-cache')
    response.headers.set('Expires', '0')
    response.headers.set('Retry-After', '3600')
    return response
}

export function middleware(request: NextRequest) {
    const isMaintenanceMode = isMaintenanceModeEnabled()

    // If maintenance mode is active — only the maintenance shell + assets needed to render it.
    // No dashboards, login, API, etc. Everything else serves the maintenance UI.
    if (isMaintenanceMode) {
        const url = request.nextUrl
        const { pathname, searchParams } = url
        const bypassToken = getBypassToken()

        // Allow privileged browser session via one-time secret link.
        const bypassCandidate = searchParams.get('maintenance_bypass') || ''
        if (bypassToken && bypassCandidate === bypassToken) {
            const target = new URL(url.toString())
            target.searchParams.delete('maintenance_bypass')
            const response = NextResponse.redirect(target, 307)
            response.cookies.set(MAINT_BYPASS_COOKIE, bypassToken, {
                httpOnly: true,
                sameSite: 'lax',
                secure: url.protocol === 'https:',
                path: '/',
                maxAge: 60 * 60 * 24 * 7, // 7 days
            })
            return response
        }

        // Explicitly remove bypass cookie in this browser.
        if (searchParams.get('maintenance_lock') === '1') {
            const target = new URL('/maintenance', url)
            const response = NextResponse.redirect(target, 307)
            response.cookies.delete(MAINT_BYPASS_COOKIE)
            return maintenanceHeaders(response)
        }

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

        if (hasValidBypassCookie(request, bypassToken)) {
            return NextResponse.next()
        }

        if (isAllowedAsset) {
            return NextResponse.next()
        }

        // Temporary redirect so the browser URL shows /maintenance (works with auth cookies; no SPA escape).
        const response = NextResponse.redirect(new URL('/maintenance', request.url), 307)
        return maintenanceHeaders(response)
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
