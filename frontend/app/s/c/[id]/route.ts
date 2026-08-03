import { NextRequest, NextResponse } from 'next/server'
import { buildOgShareHtml } from '@/lib/og-share-html'
import {
  SITE_ORIGIN,
  fetchBackendShareHtml,
  fetchContestantSharePreview,
  fetchContestantContestId,
  isSocialCrawler,
} from '@/lib/share-preview-server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

type RouteContext = {
  params: { id: string } | Promise<{ id: string }>
}

async function resolveContestantId(context: RouteContext): Promise<string | null> {
  try {
    const params = await Promise.resolve(context.params)
    const id = params?.id?.trim()
    return id || null
  } catch {
    return null
  }
}

function buildRedirectUrl(contestId: number | null, contestantId: string, ref: string | null): string {
  const entryBase = contestId
    ? `${SITE_ORIGIN}/contests/${contestId}/entry/${contestantId}`
    : `${SITE_ORIGIN}/contestants/${contestantId}`
  return ref ? `${entryBase}?ref=${encodeURIComponent(ref)}` : entryBase
}

/**
 * Contestant share page — prefer backend OG HTML (same as /api/v1/share/c/{id}),
 * fall back to locally built preview, then a plain redirect.
 */
export async function GET(request: NextRequest, context: RouteContext) {
  const contestantId = await resolveContestantId(context)
  if (!contestantId) {
    return NextResponse.redirect(`${SITE_ORIGIN}/contests`, 302)
  }

  const ref = request.nextUrl.searchParams.get('ref')
  const shareUrl = ref
    ? `${SITE_ORIGIN}/s/c/${contestantId}?ref=${encodeURIComponent(ref)}`
    : `${SITE_ORIGIN}/s/c/${contestantId}`

  try {
    const backendHtml = await fetchBackendShareHtml('c', contestantId, ref)
    if (backendHtml) {
      return new NextResponse(backendHtml, {
        status: 200,
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
          'Cache-Control': 'public, max-age=60, s-maxage=300',
          'X-Robots-Tag': 'noindex, nofollow',
        },
      })
    }
  } catch (err) {
    console.error('[s/c] backend proxy failed:', err)
  }

  try {
    const contestId = await fetchContestantContestId(contestantId)
    const redirectUrl = buildRedirectUrl(contestId, contestantId, ref)
    const ua = request.headers.get('user-agent') || ''
    const crawler = isSocialCrawler(ua)

    if (crawler) {
      const preview = await fetchContestantSharePreview(contestantId)
      const html = buildOgShareHtml({
        title: preview.title || 'Contestant on MyHigh5',
        description: preview.description || 'Vote and support on MyHigh5.',
        imageUrl: preview.imageUrl || `${SITE_ORIGIN}/logo.png`,
        shareUrl,
        redirectUrl,
        siteName: 'MyHigh5',
        includeRedirect: false,
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

    const preview = await fetchContestantSharePreview(contestantId)
    const html = buildOgShareHtml({
      title: preview.title || 'Contestant on MyHigh5',
      description: preview.description || 'Vote and support on MyHigh5.',
      imageUrl: preview.imageUrl || `${SITE_ORIGIN}/logo.png`,
      shareUrl,
      redirectUrl,
      siteName: 'MyHigh5',
      includeRedirect: true,
    })

    return new NextResponse(html, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'public, max-age=60, s-maxage=300',
        'X-Robots-Tag': 'noindex, nofollow',
      },
    })
  } catch (err) {
    console.error('[s/c] local preview failed:', err)
    const redirectUrl = buildRedirectUrl(null, contestantId, ref)
    return NextResponse.redirect(redirectUrl, 302)
  }
}
