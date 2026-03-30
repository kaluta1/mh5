import { NextRequest, NextResponse } from 'next/server'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ contestantId: string }> }
) {
  const { contestantId } = await params
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || request.nextUrl.origin || 'https://myhigh5.com'
  const redirectUrl = new URL(`/s/c/${encodeURIComponent(contestantId)}`, appUrl)
  const ref = request.nextUrl.searchParams.get('ref')

  if (ref) {
    redirectUrl.searchParams.set('ref', ref)
  }

  return NextResponse.redirect(redirectUrl)
}
