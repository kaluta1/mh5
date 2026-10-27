import { NextRequest } from 'next/server'
import { resolveShortLink } from '@/lib/short-link-proxy'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/** Member short links: https://myhigh5.com/s/{code}. (/s/c/{id} and /s/f/{id} are the share
 * preview routes; their static segments take precedence over this one.) */
export async function GET(request: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  return resolveShortLink(request, code)
}
