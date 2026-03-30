import { NextRequest, NextResponse } from 'next/server'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ username: string }> }
) {
  const { username } = await params
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || request.nextUrl.origin || 'https://myhigh5.com'
  const redirectUrl = new URL(`/s/u/${encodeURIComponent(username)}`, appUrl)
  request.nextUrl.searchParams.forEach((value, key) => {
    redirectUrl.searchParams.set(key, value)
  })

  return NextResponse.redirect(redirectUrl)
}
