import { NextRequest } from 'next/server'
import { resolveShortLink } from '@/lib/short-link-proxy'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/** Earlier short links (/l/{code}) keep working; new links use /s/{code}. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  return resolveShortLink(request, code)
}
