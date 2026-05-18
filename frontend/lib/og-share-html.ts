/**
 * Build a minimal HTML document with Open Graph tags for social crawlers (Facebook, etc.).
 */

export type OgSharePageInput = {
  title: string
  description: string
  imageUrl: string
  /** Canonical URL being shared (must match what users paste). */
  shareUrl: string
  /** Where browsers land after the preview is read. */
  redirectUrl: string
  siteName?: string
  /** When false, crawlers keep this HTML (no meta refresh). */
  includeRedirect?: boolean
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function absolutizeOgImage(url: string, siteOrigin: string): string {
  const trimmed = (url || '').trim()
  if (!trimmed) return `${siteOrigin}/logo.png`
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return trimmed.replace(/^http:\/\//i, 'https://')
  }
  if (trimmed.startsWith('/')) return `${siteOrigin.replace(/\/+$/, '')}${trimmed}`
  return `${siteOrigin.replace(/\/+$/, '')}/${trimmed.replace(/^\/+/, '')}`
}

export function buildOgShareHtml(input: OgSharePageInput): string {
  const title = escapeHtml(input.title)
  const description = escapeHtml(input.description)
  const image = escapeHtml(input.imageUrl)
  const shareUrl = escapeHtml(input.shareUrl)
  const redirectUrl = escapeHtml(input.redirectUrl)
  const siteName = escapeHtml(input.siteName || 'MyHigh5')
  const includeRedirect = input.includeRedirect !== false
  const refreshTag = includeRedirect
    ? `<meta http-equiv="refresh" content="2;url=${redirectUrl}">`
    : ''

  return `<!DOCTYPE html>
<html lang="en" prefix="og: https://ogp.me/ns#">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  <meta name="description" content="${description}">
  <meta property="og:type" content="article">
  <meta property="og:locale" content="en_US">
  <meta property="og:site_name" content="${siteName}">
  <meta property="og:url" content="${shareUrl}">
  <meta property="og:title" content="${title}">
  <meta property="og:description" content="${description}">
  <meta property="og:image" content="${image}">
  <meta property="og:image:secure_url" content="${image}">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:url" content="${shareUrl}">
  <meta name="twitter:title" content="${title}">
  <meta name="twitter:description" content="${description}">
  <meta name="twitter:image" content="${image}">
  <link rel="canonical" href="${shareUrl}">
  ${refreshTag}
</head>
<body>
  <article>
    <h1>${title}</h1>
    <p>${description}</p>
    <p><a href="${redirectUrl}">Continue to ${siteName}</a></p>
  </article>
</body>
</html>`
}
