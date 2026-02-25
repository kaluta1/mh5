import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
    // Check if maintenance mode is enabled
    const isMaintenanceMode = process.env.IS_MAINTENANCE_MODE?.trim() === 'true'

    // If maintenance mode is active
    if (isMaintenanceMode) {
        // List of paths that should remain accessible
        const allowedPaths = [
            '/maintenance',
            '/_next',
            '/static',
            '/favicon.ico',
            '/thumbnails.png',
            '/images', // Assuming there might be an images folder
            '/reset-password', // Allow password reset even during maintenance
            '/forgot-password', // Allow password reset request even during maintenance
            '/login', // Allow login even during maintenance
        ]

        const { pathname } = request.nextUrl

        // Allow static assets and the maintenance page
        if (allowedPaths.some(path => pathname.startsWith(path)) || pathname.match(/\.(png|jpg|jpeg|svg|css|js|json)$/)) {
            return NextResponse.next()
        }

        // Redirect everything else to maintenance page
        return NextResponse.redirect(new URL('/maintenance', request.url))
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
