import { NextRequest, NextResponse } from 'next/server'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ contestantId: string }> }
) {
  const { contestantId } = await params
  const redirectUrl = new URL(`/api/v1/share/c/${encodeURIComponent(contestantId)}`, request.url)
  const ref = request.nextUrl.searchParams.get('ref')

  if (ref) {
    redirectUrl.searchParams.set('ref', ref)
  }

  return NextResponse.redirect(redirectUrl)
}
