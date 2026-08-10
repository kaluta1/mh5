import { NextRequest, NextResponse } from 'next/server'

/** Reserved paths that must not be treated as public profile usernames. */
const RESERVED_USERNAMES = new Set([
  'favicon.ico',
  'robots.txt',
  'sitemap.xml',
  'manifest.json',
  'apple-touch-icon.png',
  'register',
  'login',
  'dashboard',
  'maintenance',
  'contests',
  'contact',
  'about',
  'api',
  'feed',
  'contestants',
  'profile',
  'faq',
  'privacy',
  'terms',
  'cookies',
  'clubs',
  'pitching',
  'verify-email',
  'reset-password',
  'forgot-password',
  'pages_mobile',
  'link-preview',
  'tiktok-resolve',
  'c',
  's',
  'l',
  'r',
  'f',
  'p',
  'u',
])

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ username: string }> }
) {
  const { username } = await params
  const normalized = username.toLowerCase()
  if (
    RESERVED_USERNAMES.has(normalized) ||
    normalized.includes('.') ||
    normalized.startsWith('_next')
  ) {
    return new NextResponse('Not Found', { status: 404 })
  }

  const appUrl = process.env.NEXT_PUBLIC_APP_URL || request.nextUrl.origin || 'https://myhigh5.com'
  const redirectUrl = new URL(`/s/u/${encodeURIComponent(username)}`, appUrl)
  request.nextUrl.searchParams.forEach((value, key) => {
    redirectUrl.searchParams.set(key, value)
  })

  return NextResponse.redirect(redirectUrl)
}
