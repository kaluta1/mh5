import { API_URL } from "@/lib/config"

/**
 * Normalize legacy media paths to a publicly reachable API file endpoint.
 * Example: /media/159/file.png -> https://myhigh5.com/api/v1/media/file/159/file.png
 */
export function normalizeMediaUrl(url?: string | null): string {
  const raw = String(url || "").trim()
  if (!raw) return ""

  if (raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("data:")) {
    return raw
  }

  if (raw.startsWith("/api/v1/media/file/")) {
    return `${API_URL}${raw}`
  }

  const legacyMatch = raw.match(/^\/media\/([^/]+)\/(.+)$/)
  if (legacyMatch) {
    const [, userId, filename] = legacyMatch
    return `${API_URL}/api/v1/media/file/${encodeURIComponent(userId)}/${encodeURIComponent(filename)}`
  }

  if (raw.startsWith("/")) {
    return `${API_URL}${raw}`
  }

  return raw
}
