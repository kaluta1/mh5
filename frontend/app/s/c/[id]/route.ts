import { NextRequest, NextResponse } from 'next/server'
import { buildOgShareHtml } from '@/lib/og-share-html'
import {
  SITE_ORIGIN,
  fetchBackendShareHtml,
  fetchContestantSharePreview,
  isSocialCrawler,
} from '@/lib/share-preview-server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const ref = request.nextUrl.searchParams.get('ref')
  const shareUrl = ref
    ? `${SITE_ORIGIN}/s/c/${id}?ref=${encodeURIComponent(ref)}`
    : `${SITE_ORIGIN}/s/c/${id}`
  const redirectUrl = ref
    ? `${SITE_ORIGIN}/contestants/${id}?ref=${encodeURIComponent(ref)}`
    : `${SITE_ORIGIN}/contestants/${id}`

  const ua = request.headers.get('user-agent') || ''
  const crawler = isSocialCrawler(ua)

  const backendHtml = await fetchBackendShareHtml('c', id, ref)
  if (backendHtml && /og:image/i.test(backendHtml)) {
    return new NextResponse(backendHtml, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'public, max-age=60, s-maxage=300',
        'X-Robots-Tag': 'noindex, nofollow',
      },
    })
  }

  const preview = await fetchContestantSharePreview(id)

  const html = buildOgShareHtml({
    title: preview.title,
    description: preview.description,
    imageUrl: preview.imageUrl,
    shareUrl,
    redirectUrl,
    siteName: 'MyHigh5',
    includeRedirect: !crawler,
  })

  return new NextResponse(html, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'public, max-age=60, s-maxage=300',
      'X-Robots-Tag': 'noindex, nofollow',
    },
  })
}
