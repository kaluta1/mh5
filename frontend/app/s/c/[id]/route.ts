import { NextRequest, NextResponse } from 'next/server'
import { API_URL } from '@/lib/config'
import { absolutizeOgImage, buildOgShareHtml } from '@/lib/og-share-html'

const SITE_ORIGIN = (process.env.NEXT_PUBLIC_APP_URL || 'https://myhigh5.com').replace(/\/+$/, '')
const DEFAULT_IMAGE = `${SITE_ORIGIN}/logo.png`

type ShareContestantPayload = {
  title?: string | null
  description?: string | null
  author_name?: string | null
  contestant_image_url?: string | null
  contest_image_url?: string | null
  author_avatar_url?: string | null
}

async function fetchContestantForShare(contestantId: string): Promise<ShareContestantPayload | null> {
  const apiBase = API_URL.replace(/\/+$/, '')
  try {
    const res = await fetch(`${apiBase}/api/v1/contestants/${contestantId}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!res.ok) return null
    return (await res.json()) as ShareContestantPayload
  } catch {
    return null
  }
}

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

  let title = 'Contestant on MyHigh5'
  let description = 'Vote and support on MyHigh5.'
  let imageUrl = DEFAULT_IMAGE

  const contestant = await fetchContestantForShare(id)
  if (contestant) {
    const authorName = contestant.author_name?.trim() || 'Contestant'
    const entryTitle = contestant.title?.trim()
    title = entryTitle ? `${entryTitle} — ${authorName}` : `${authorName} on MyHigh5`
    description =
      (contestant.description || '').trim().slice(0, 200) ||
      `Vote for ${authorName} on MyHigh5.`
    const rawImage =
      contestant.contestant_image_url ||
      contestant.contest_image_url ||
      contestant.author_avatar_url
    if (rawImage) imageUrl = absolutizeOgImage(rawImage, SITE_ORIGIN)
  }

  const html = buildOgShareHtml({
    title,
    description,
    imageUrl,
    shareUrl,
    redirectUrl,
    siteName: 'MyHigh5',
  })

  return new NextResponse(html, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=600',
    },
  })
}
