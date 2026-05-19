import { API_URL, getEffectiveApiUrl } from "@/lib/config"

function mediaApiOrigin(): string {
  const base =
    typeof window !== "undefined" ? getEffectiveApiUrl() : API_URL
  return String(base || "").replace(/\/+$/, "")
}

/**
 * Normalize legacy media paths to a publicly reachable API file endpoint.
 * Example: /media/159/file.png -> https://myhigh5.com/api/v1/media/file/159/file.png
 */
export function normalizeMediaUrl(url?: string | null): string {
  const raw = String(url || "").trim()
  if (!raw) return ""

  const origin = mediaApiOrigin()

  if (raw.startsWith("data:")) {
    return raw
  }

  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    // Legacy direct S3 URLs → API file route (bucket may be private).
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
