import { NextResponse } from 'next/server'
import { fetchPostSharePreview, SITE_ORIGIN, DEFAULT_OG_IMAGE } from '@/lib/share-preview-server'
import { API_URL } from '@/lib/config'

/**
 * VPS diagnostic: GET /api/share-debug?id=24
 * Remove or protect in production if you prefer.
 */
export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get('id') || '24'
  const preview = await fetchPostSharePreview(id)
  return NextResponse.json({
    siteOrigin: SITE_ORIGIN,
    apiUrlBuildTime: API_URL,
    internalApiUrl: process.env.INTERNAL_API_URL || '(not set)',
    defaultOgImage: DEFAULT_OG_IMAGE,
    preview,
    hint: 'Share page: /s/f/' + id + ' — must return HTML with og:image in View Source',
  })
}
