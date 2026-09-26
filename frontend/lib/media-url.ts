import { API_URL, getEffectiveApiUrl } from "@/lib/config"

export function mediaApiOrigin(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname
    if (host !== "localhost" && host !== "127.0.0.1") {
      return window.location.origin.replace(/\/+$/, "")
    }
    return getEffectiveApiUrl().replace(/\/+$/, "")
  }
  return String(API_URL || "").replace(/\/+$/, "")
}

function safeSegment(value: string): string | null {
  try {
    const decoded = decodeURIComponent(value)
    if (!decoded || decoded.includes("/") || decoded.includes("\\") || decoded.includes("\0")) return null
    return encodeURIComponent(decoded)
  } catch {
    return null
  }
}

function canonicalFilePath(raw: string): string | null {
  const apiFile = raw.match(/\/api\/v1\/media\/file\/(\d+)\/([^/?#\\]+)/i)
  if (apiFile) {
    const filename = safeSegment(apiFile[2])
    return filename ? `/api/v1/media/file/${apiFile[1]}/${filename}` : null
  }
  const legacy = raw.match(/^\/media\/(\d+)\/([^/?#\\]+)(?:[?#].*)?$/i)
  if (legacy) {
    const filename = safeSegment(legacy[2])
    return filename ? `/api/v1/media/file/${legacy[1]}/${filename}` : null
  }
  const uploaded = raw.match(/\/uploads\/(\d+)\/([^/?#\\]+)(?:[?#].*)?$/i)
  if (uploaded) {
    const filename = safeSegment(uploaded[2])
    return filename ? `/api/v1/media/file/${uploaded[1]}/${filename}` : null
  }
  return null
}

/**
 * Child/Teen Safety Phase 7: protected entry media URLs carry a short-lived,
 * viewer-bound grant (`/api/v1/media/file/{uid}/{name}?g=...`). The grant is not a
 * credential on its own (the server also requires this viewer's media session);
 * it is kept for display only and is never part of a stored value.
 */
function mediaToken(raw: string): string | null {
  const m = raw.match(/\/api\/v1\/media\/file\/\d+\/[^/?#\\]+\?(?:[^#]*&)?g=([A-Za-z0-9_\-.]{1,1024})(?:[&#]|$)/i)
  return m ? m[1] : null
}

/** Extract a portable, host-agnostic value suitable for database storage. */
export function toStoredMediaUrl(url?: string | null): string {
  const raw = String(url || "").trim()
  if (!raw) return ""
  const canonical = canonicalFilePath(raw)
  if (/\/api\/v1\/media\/file\//i.test(raw) && !canonical) return ""
  return canonical || raw
}

/**
 * Resolve current and historical media references without rewriting stored data.
 * Unsafe schemes and host filesystem paths fail closed. Legacy localhost URLs are
 * rebound to the current public origin so old seed/demo references never target a
 * visitor's own machine.
 */
export function normalizeMediaUrl(url?: string | null): string {
  const raw = String(url || "").trim()
  if (!raw || /[\u0000-\u001f]/.test(raw)) return ""
  if (/^(javascript|vbscript|file):/i.test(raw) || /^[a-z]:[\\/]/i.test(raw)) return ""

  const origin = mediaApiOrigin()
  const canonical = canonicalFilePath(raw)
  if (canonical) {
    const token = mediaToken(raw)
    return `${origin}${canonical}${token ? `?g=${token}` : ""}`
  }
  if (/\/api\/v1\/media\/file\//i.test(raw)) return ""

  if (/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(raw)) return raw
  if (raw.startsWith("blob:") && typeof window !== "undefined") return raw
  if (/^data:/i.test(raw)) return ""

  if (raw.startsWith("/")) {
    if (raw.startsWith("//")) return ""
    return `${origin}${raw}`
  }

  if (/^(?:storage|uploads|media)\//i.test(raw)) {
    return `${origin}/${raw}`
  }

  try {
    const parsed = new URL(raw)
    if (parsed.username || parsed.password) return ""
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return ""
    const localhost = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1" || parsed.hostname === "::1"
    if (localhost) return `${origin}${parsed.pathname}${parsed.search}`
    if (parsed.protocol === "http:") parsed.protocol = "https:"
    return parsed.toString()
  } catch {
    return ""
  }
}

export function withMediaCacheBust(url: string, token?: string | number): string {
  if (!url || url.startsWith("data:") || url.startsWith("blob:")) return url
  const sep = url.includes("?") ? "&" : "?"
  return `${url}${sep}v=${token ?? Date.now()}`
}
