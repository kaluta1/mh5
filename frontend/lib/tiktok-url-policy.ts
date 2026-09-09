export function assertSafeTikTokUrl(raw: string): URL {
  const url = new URL(raw)
  const host = url.hostname.toLowerCase()
  if (
    url.protocol !== 'https:' || url.username || url.password ||
    !(host === 'tiktok.com' || host.endsWith('.tiktok.com'))
  ) {
    throw new Error('Only HTTPS TikTok URLs are allowed')
  }
  return url
}
