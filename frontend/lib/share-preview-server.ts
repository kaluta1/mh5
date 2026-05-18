import { API_URL, DEFAULT_PUBLIC_API_URL } from '@/lib/config'

export const SITE_ORIGIN = (
  process.env.NEXT_PUBLIC_APP_URL || DEFAULT_PUBLIC_API_URL
).replace(/\/+$/, '')

export const DEFAULT_OG_IMAGE = `${SITE_ORIGIN}/opengraph-image`

export type SharePostPreview = {
  title: string
  description: string
  imageUrl: string
}

export type ShareContestantPreview = {
  title: string
  description: string
  imageUrl: string
}

function serverApiBase(): string {
  const internal = (process.env.INTERNAL_API_URL || '').trim().replace(/\/+$/, '')
  if (internal) return internal
  return API_URL.replace(/\/+$/, '')
}

export function absolutizeShareImage(url: string | null | undefined): string {
  const trimmed = (url || '').trim()
  if (!trimmed) return DEFAULT_OG_IMAGE
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return trimmed.replace(/^http:\/\//i, 'https://')
  }
  if (trimmed.startsWith('/')) {
    return `${SITE_ORIGIN}${trimmed}`
  }
  const apiBase = serverApiBase()
  return `${apiBase}/${trimmed.replace(/^\/+/, '')}`
}

type ApiPost = {
  content?: string | null
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

type ApiPreviewPost = {
  title?: string
  description?: string
  image_url?: string
}

export async function fetchPostSharePreview(postId: string): Promise<SharePostPreview> {
  const apiBase = serverApiBase()
  const fallback: SharePostPreview = {
    title: 'Post on MyHigh5',
    description: 'See this post on MyHigh5.',
    imageUrl: DEFAULT_OG_IMAGE,
  }

  try {
    const previewRes = await fetch(`${apiBase}/api/v1/share/preview/post/${postId}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (previewRes.ok) {
      const data = (await previewRes.json()) as ApiPreviewPost
      return {
        title: data.title || fallback.title,
        description: data.description || fallback.description,
        imageUrl: data.image_url ? absolutizeShareImage(data.image_url) : DEFAULT_OG_IMAGE,
      }
    }
  } catch {
    /* fall through */
  }

  try {
    const res = await fetch(`${apiBase}/api/v1/social/posts/${postId}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!res.ok) return fallback
    const post = (await res.json()) as ApiPost
    const authorName =
      post.author?.full_name?.trim() ||
      post.author?.username?.trim() ||
      'MyHigh5 user'
    const content = (post.content || '').trim()
    let imageUrl = DEFAULT_OG_IMAGE
    for (const item of post.media || []) {
      const url = item.url || item.thumbnail_url
      if (!url) continue
      const type = (item.media_type || '').toLowerCase()
      if (!type || type === 'image') {
        imageUrl = absolutizeShareImage(url)
        break
      }
    }
    if (imageUrl === DEFAULT_OG_IMAGE && post.author?.avatar_url) {
      imageUrl = absolutizeShareImage(post.author.avatar_url)
    }
    return {
      title: content ? `${authorName} on MyHigh5` : `${authorName} shared on MyHigh5`,
      description: content.slice(0, 200) || `Discover what ${authorName} shared on MyHigh5.`,
      imageUrl,
    }
  } catch {
    return fallback
  }
}

type ApiContestant = {
  title?: string | null
  description?: string | null
  author_name?: string | null
  contestant_image_url?: string | null
  contest_image_url?: string | null
  author_avatar_url?: string | null
}

export async function fetchContestantSharePreview(
  contestantId: string
): Promise<ShareContestantPreview> {
  const apiBase = serverApiBase()
  const fallback: ShareContestantPreview = {
    title: 'Contestant on MyHigh5',
    description: 'Vote and support on MyHigh5.',
    imageUrl: DEFAULT_OG_IMAGE,
  }

  try {
    const previewRes = await fetch(`${apiBase}/api/v1/share/preview/contestant/${contestantId}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (previewRes.ok) {
      const data = (await previewRes.json()) as ApiPreviewPost
      return {
        title: data.title || fallback.title,
        description: data.description || fallback.description,
        imageUrl: data.image_url ? absolutizeShareImage(data.image_url) : DEFAULT_OG_IMAGE,
      }
    }
  } catch {
    /* fall through */
  }

  try {
    const res = await fetch(`${apiBase}/api/v1/contestants/${contestantId}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!res.ok) return fallback
    const c = (await res.json()) as ApiContestant
    const authorName = c.author_name?.trim() || 'Contestant'
    const entryTitle = c.title?.trim()
    const rawImage =
      c.contestant_image_url || c.contest_image_url || c.author_avatar_url
    return {
      title: entryTitle ? `${entryTitle} — ${authorName}` : `${authorName} on MyHigh5`,
      description:
        (c.description || '').trim().slice(0, 200) ||
        `Vote for ${authorName} on MyHigh5.`,
      imageUrl: rawImage ? absolutizeShareImage(rawImage) : DEFAULT_OG_IMAGE,
    }
  } catch {
    return fallback
  }
}

export function isSocialCrawler(userAgent: string | null): boolean {
  if (!userAgent) return false
  return /facebookexternalhit|Facebot|Twitterbot|LinkedInBot|WhatsApp|TelegramBot|Slackbot|Discordbot|Googlebot|bingbot|Pinterestbot/i.test(
    userAgent
  )
}
