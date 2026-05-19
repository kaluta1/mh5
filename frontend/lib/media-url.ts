import { API_URL, getEffectiveApiUrl } from "@/lib/config"

function mediaApiOrigin(): string {
  const base =
    typeof window !== "undefined" ? getEffectiveApiUrl() : API_URL
  return String(base || "").replace(/\/+$/, "")
}

/** Extract portable path stored in DB (host-agnostic). */
export function toStoredMediaUrl(url?: string | null): string {
  const raw = String(url || "").trim()
  if (!raw) return ""

  const apiFile = raw.match(/\/api\/v1\/media\/file\/\d+\/[^?#]+/)
  if (apiFile) return apiFile[0]

  const legacy = raw.match(/^\/media\/([^/]+)\/(.+)$/)
  if (legacy) {
    return `/api/v1/media/file/${legacy[1]}/${legacy[2]}`
  }

  const s3 = raw.match(/\/uploads\/(\d+)\/([^/?#]+)$/)
  if (s3) {
    return `/api/v1/media/file/${s3[1]}/${s3[2]}`
  }

  return raw
}

/**
 * Normalize legacy media paths to a publicly reachable API file endpoint.
 * Always uses the same API origin as login/upload (myhigh5.com or api.myhigh5.com).
 */
export function normalizeMediaUrl(url?: string | null): string {
  const raw = String(url || "").trim()
  if (!raw) return ""

  const origin = mediaApiOrigin()
  const stored = toStoredMediaUrl(raw)
  if (stored.startsWith("/api/v1/media/file/")) {
    return `${origin}${stored}`
  }

  if (raw.startsWith("data:")) {
    return raw
  }

  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    const apiFileAbs = raw.match(/^https?:\/\/[^/]+(\/api\/v1\/media\/file\/\d+\/[^?#]+)/i)
    if (apiFileAbs) {
      return `${origin}${apiFileAbs[1]}`
    }
    const s3Match = raw.match(/\/uploads\/([^/]+)\/([^/?#]+)$/)
    if (s3Match) {
      const [, userId, filename] = s3Match
      return `${origin}/api/v1/media/file/${encodeURIComponent(userId)}/${encodeURIComponent(filename)}`
    }
    return raw
  }

  if (raw.startsWith("/api/v1/media/file/")) {
    return `${origin}${raw}`
  }

  const legacyMatch = raw.match(/^\/media\/([^/]+)\/(.+)$/)
  if (legacyMatch) {
    const [, userId, filename] = legacyMatch
    return `${origin}/api/v1/media/file/${encodeURIComponent(userId)}/${encodeURIComponent(filename)}`
  }

  if (raw.startsWith("/")) {
    return `${origin}${raw}`
  }

  return raw
}

export function withMediaCacheBust(url: string, token?: string | number): string {
  if (!url || url.startsWith("data:") || url.startsWith("blob:")) return url
  const sep = url.includes("?") ? "&" : "?"
  return `${url}${sep}v=${token ?? Date.now()}`
}
