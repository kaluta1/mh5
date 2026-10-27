import { NextRequest, NextResponse } from 'next/server'
import { getServerApiBase } from '@/lib/share-preview-server'

const CODE_RE = /^[0-9A-Za-z]{4,16}$/

/** Branded page for a short link that is unknown, disabled or no longer allowed (never a silent
 * redirect to the home page). Self-contained HTML: route handlers bypass the app layout. */
export function shortLinkUnavailablePage(status = 404): NextResponse {
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Link unavailable · MyHigh5</title>
<style>
  :root { color-scheme: light dark; --bg:#f8fafc; --card:#ffffff; --text:#111827; --muted:#4b5563; --brand:#4f46e5; --border:#e5e7eb; }
  @media (prefers-color-scheme: dark) { :root { --bg:#0b1120; --card:#111827; --text:#f9fafb; --muted:#9ca3af; --brand:#818cf8; --border:#1f2937; } }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:16px;
         background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  main { width:100%; max-width:440px; background:var(--card); border:1px solid var(--border); border-radius:16px;
         padding:32px 24px; text-align:center; }
  .brand { font-weight:800; font-size:20px; color:var(--brand); margin-bottom:16px; }
  h1 { font-size:22px; margin:0 0 8px; }
  p { color:var(--muted); line-height:1.5; margin:0 0 24px; }
  a.button { display:inline-block; background:var(--brand); color:#fff; text-decoration:none; padding:10px 20px;
             border-radius:10px; font-weight:600; }
</style>
</head>
<body>
<main>
  <div class="brand">MyHigh5</div>
  <h1>This link is not available</h1>
  <p>The short link you opened is invalid, has been disabled by its owner, or no longer leads to a page that can be shared. Ask the person who sent it for a new link.</p>
  <a class="button" href="/">Go to MyHigh5</a>
</main>
</body>
</html>`
  return new NextResponse(html, {
    status,
    headers: {
      'content-type': 'text/html; charset=utf-8',
      'cache-control': 'no-store',
      'x-robots-tag': 'noindex',
    },
  })
}

/**
 * Resolve a short link through FastAPI (/api/v1/l/{code}). Next.js external rewrites return 500
 * for 302 responses, so Location and Set-Cookie are forwarded explicitly. The answer is per visitor
 * (an invitation link sets a cookie): never cached.
 */
export async function resolveShortLink(request: NextRequest, code: string): Promise<NextResponse> {
  if (!code || !CODE_RE.test(code)) return shortLinkUnavailablePage()

  const apiBase = getServerApiBase()
  const forwardedFor = request.headers.get('x-forwarded-for') || request.headers.get('x-real-ip') || ''
  const fetchUpstream = () =>
    fetch(`${apiBase}/api/v1/l/${encodeURIComponent(code)}`, {
      method: 'GET',
      redirect: 'manual',
      cache: 'no-store',
      signal: AbortSignal.timeout(8000),
      headers: {
        'x-forwarded-for': forwardedFor,
        'user-agent': request.headers.get('user-agent') || '',
        referer: request.headers.get('referer') || '',
      },
    })

  try {
    let upstream: Response | null = null
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        upstream = await fetchUpstream()
        break
      } catch (err) {
        if (attempt === 2) throw err
        await new Promise((r) => setTimeout(r, 400 * (attempt + 1)))
      }
    }
    if (!upstream) return shortLinkUnavailablePage(502)

    if (upstream.status >= 300 && upstream.status < 400) {
      const location = upstream.headers.get('location')
      if (!location) return shortLinkUnavailablePage(502)
      const response = NextResponse.redirect(location, upstream.status)
      const cookies = typeof upstream.headers.getSetCookie === 'function' ? upstream.headers.getSetCookie() : []
      if (cookies.length > 0) {
        for (const cookie of cookies) response.headers.append('set-cookie', cookie)
      } else {
        const single = upstream.headers.get('set-cookie')
        if (single) response.headers.set('set-cookie', single)
      }
      response.headers.set('cache-control', 'no-store, private')
      response.headers.set('x-robots-tag', 'noindex')
      return response
    }
    if (upstream.status === 429) {
      return new NextResponse('Too many requests. Please try again shortly.', {
        status: 429,
        headers: { 'cache-control': 'no-store' },
      })
    }
    return shortLinkUnavailablePage(upstream.status === 404 ? 404 : 502)
  } catch (error) {
    console.error('Short link proxy error:', error)
    return shortLinkUnavailablePage(502)
  }
}
