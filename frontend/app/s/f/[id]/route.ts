import { NextRequest, NextResponse } from 'next/server'
import { API_URL } from '@/lib/config'
import { absolutizeOgImage, buildOgShareHtml } from '@/lib/og-share-html'

const SITE_ORIGIN = (process.env.NEXT_PUBLIC_APP_URL || 'https://myhigh5.com').replace(/\/+$/, '')
const DEFAULT_IMAGE = `${SITE_ORIGIN}/logo.png`

type SharePostPayload = {
  content?: string | null
  visibility?: string
  author?: {
    full_name?: string | null
    username?: string | null
    avatar_url?: string | null
  } | null
  media?: Array<{
    url?: string | null
    media_type?: string | null
    thumbnail_url?: string | null
  }> | null
}

function pickPostImage(post: SharePostPayload): string {
  for (const item of post.media || []) {
    const url = item.url || item.thumbnail_url
    if (!url) continue
    const type = (item.media_type || '').toLowerCase()
    if (!type || type === 'image') {
      return absolutizeOgImage(url, SITE_ORIGIN)
    }
  }
  if (post.author?.avatar_url) {
    return absolutizeOgImage(post.author.avatar_url, SITE_ORIGIN)
  }
  return DEFAULT_IMAGE
}

async function fetchPostForShare(postId: string): Promise<SharePostPayload | null> {
  const apiBase = API_URL.replace(/\/+$/, '')
  const endpoints = [
    `${apiBase}/api/v1/social/posts/${postId}`,
    `${apiBase}/api/v1/share/f/${postId}`,
  ]

  for (const url of endpoints) {
    try {
      const res = await fetch(url, {
        headers: { Accept: 'application/json, text/html' },
        cache: 'no-store',
      })
      if (!res.ok) continue
      const contentType = res.headers.get('content-type') || ''
      if (contentType.includes('application/json')) {
        return (await res.json()) as SharePostPayload
      }
    } catch {
      /* try next */
    }
  }
  return null
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const ref = request.nextUrl.searchParams.get('ref')
  const shareUrl = ref
    ? `${SITE_ORIGIN}/s/f/${id}?ref=${encodeURIComponent(ref)}`
    : `${SITE_ORIGIN}/s/f/${id}`
  const redirectUrl = ref
    ? `${SITE_ORIGIN}/dashboard/feed/${id}?ref=${encodeURIComponent(ref)}`
    : `${SITE_ORIGIN}/dashboard/feed/${id}`

  let title = 'Post on MyHigh5'
  let description = 'See this post on MyHigh5.'
  let imageUrl = DEFAULT_IMAGE

  const post = await fetchPostForShare(id)
  if (post) {
    const authorName =
      post.author?.full_name?.trim() ||
      post.author?.username?.trim() ||
      'MyHigh5 user'
    const content = (post.content || '').trim()
    title = content ? `${authorName} on MyHigh5` : `${authorName} shared on MyHigh5`
    description = content.slice(0, 200) || `Discover what ${authorName} shared on MyHigh5.`
    imageUrl = pickPostImage(post)
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
