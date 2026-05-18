import { NextResponse } from 'next/server'
import { fetchPostSharePreview, SITE_ORIGIN, DEFAULT_OG_IMAGE, getServerApiBase } from '@/lib/share-preview-server'

export const dynamic = 'force-dynamic'

/**
 * VPS diagnostic (hits Next.js, not FastAPI): GET https://myhigh5.com/share-debug?id=24
 */
export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get('id') || '24'
  const apiBase = getServerApiBase()
  let previewApiStatus: number | string = 'skipped'
  try {
    const r = await fetch(`${apiBase}/api/v1/share/preview/post/${id}`, { cache: 'no-store' })
    previewApiStatus = r.status
  } catch (e) {
    previewApiStatus = String(e)
  }
  const preview = await fetchPostSharePreview(id)
  return NextResponse.json({
    siteOrigin: SITE_ORIGIN,
    apiBaseUsed: apiBase,
    internalApiUrl: process.env.INTERNAL_API_URL || '(not set — using loopback in production)',
    previewApiStatus,
    defaultOgImage: DEFAULT_OG_IMAGE,
    preview,
  })
}
