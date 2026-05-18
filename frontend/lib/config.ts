/**
 * Frontend configuration.
 * On your VPS (or any host), set NEXT_PUBLIC_API_URL to the public API origin
 * (e.g. https://myhigh5.com or https://api.myhigh5.com — match nginx / reverse proxy).
 */

/** Default API origin when NEXT_PUBLIC_* is unset at build time (production self-hosted). */
export const DEFAULT_PUBLIC_API_URL = 'https://myhigh5.com'

const normalizeApiUrl = (url: string): string => {
  if (!url) return ''
  let normalized = url.replace(/\/+$/, '')
  if (typeof window !== 'undefined' && window.location.protocol === 'https:' && normalized.startsWith('http://')) {
    normalized = normalized.replace('http://', 'https://')
  }
  return normalized
}

/**
 * Some .env files mistakenly list two origins separated by a comma.
 * `new URL("http://localhost:8000,https://myhigh5.com")` throws — pick one explicit origin.
 */
function parseNextPublicApiUrl(raw: string, nodeEnv: string | undefined): string {
  const trimmed = (raw || '').trim()
  if (!trimmed) return ''
  const parts = trimmed
    .split(',')
    .map((s) => s.trim().replace(/\/+$/, ''))
    .filter(Boolean)
  if (parts.length === 1) return parts[0]
  const prod = nodeEnv === 'production'
  if (prod) {
    const httpsPublic = parts.find(
      (p) => p.startsWith('https://') && !/(localhost|127\.0\.0\.1)/i.test(p)
    )
    if (httpsPublic) return httpsPublic
  }
  const local = parts.find((p) => /localhost|127\.0\.0\.1/i.test(p))
  return local ?? parts[0]
}

const rawApiUrl = parseNextPublicApiUrl(
  process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || '',
  process.env.NODE_ENV
)
const isProduction = process.env.NODE_ENV === 'production'
/**
 * Local UI default port 3001 (`npm run dev`); API default 8001. Set NEXT_PUBLIC_API_URL=http://localhost:8001 in
 * frontend/.env so login uses your local backend. Without it, `next start` defaults to the
 * public site URL and hits a different database.
 * build (`next start`) defaults to DEFAULT_PUBLIC_API_URL and hits a different database.
 */
const fallbackUrl = isProduction ? DEFAULT_PUBLIC_API_URL : 'http://localhost:8001'

export const API_URL = normalizeApiUrl(rawApiUrl || fallbackUrl)

/** Port where FastAPI listens on the same machine as Next (browser uses this hostname + port during VPS dev). */
export const BACKEND_PUBLIC_PORT =
  process.env.NEXT_PUBLIC_BACKEND_PUBLIC_PORT?.trim()?.replace(/^["']|["']$/g, '') || '8001'

/**
 * Effective API origin for browser requests.
 * When the UI is opened via a public hostname/IP but NEXT_PUBLIC_API_URL still points at
 * localhost (common on VPS mistakes), callers must use same host + BACKEND_PUBLIC_PORT or
 * login hits the user's own PC and axios reports "Network Error".
 */
export function getEffectiveApiUrl(): string {
  let base = API_URL.replace(/\/+$/, '')
  if (typeof window === 'undefined') {
    return base
  }
  const pageHost = window.location.hostname
  const pageIsLocal = pageHost === 'localhost' || pageHost === '127.0.0.1'

  try {
    const parsed = new URL(base)
    const apiLoopback = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1'
    // Remote browser accessing UI on LAN/VPS URL while env still says localhost → fix server target
    if (!pageIsLocal && apiLoopback) {
      const port = window.location.port
      const defaultWebPort = port === '' || port === '443' || port === '80'
      // Production behind nginx on 443/80: API is same host (e.g. /api/v1 → uvicorn), not :8001 in the browser
      if (defaultWebPort) {
        base = normalizeApiUrl(window.location.origin).replace(/\/+$/, '')
      } else {
        base = normalizeApiUrl(
          `${window.location.protocol}//${pageHost}:${BACKEND_PUBLIC_PORT}`
        ).replace(/\/+$/, '')
      }
    }
  } catch {
    /* keep base */
  }
  return base
}

/**
 * Annual Ads embed iframe `src` (full URL with query key). Next.js inlines this at build time
 * for client bundles — it must be set in the same env you use for `next build` (Vercel / VPS
 * / Docker), not only on your laptop, or production will show "Set the embed URL".
 */
function stripEnvQuotes(s: string): string {
  const t = s.trim()
  if (t.length >= 2 && ((t[0] === '"' && t[t.length - 1] === '"') || (t[0] === "'" && t[t.length - 1] === "'"))) {
    return t.slice(1, -1).trim()
  }
  return t
}

const annualAdsEmbedBase = stripEnvQuotes(process.env.NEXT_PUBLIC_ANNUALADS_EMBED_BASE || '')
const annualAdsApiKey = stripEnvQuotes(
  process.env.NEXT_PUBLIC_ANNUALADS_API_KEY || process.env.NEXT_PUBLIC_ANNUALADS_TENANT_API_KEY || ''
)

const annualAdsEmbedUrlFromBase = (() => {
  if (!annualAdsEmbedBase || !annualAdsApiKey) return ''
  try {
    const url = new URL(annualAdsEmbedBase)
    url.searchParams.set('key', annualAdsApiKey)
    return url.toString()
  } catch {
    return ''
  }
})()

export const ANNUALADS_EMBED_URL =
  stripEnvQuotes(process.env.NEXT_PUBLIC_ANNUALADS_EMBED_URL || '') || annualAdsEmbedUrlFromBase

export const ANNUALADS_SSO_TARGET_ORIGIN = stripEnvQuotes(
  process.env.NEXT_PUBLIC_ANNUALADS_SSO_TARGET_ORIGIN || 'https://www.annualads.com'
)

/** Partner id for Annual Ads rotator.js (`data-partner-id`). */
const annualAdsPartnerIdFromEmbedBase = (() => {
  if (!annualAdsEmbedBase) return ''
  try {
    const segments = new URL(annualAdsEmbedBase).pathname.split('/').filter(Boolean)
    return segments[segments.length - 1] || ''
  } catch {
    return ''
  }
})()

export const ANNUALADS_PARTNER_ID =
  stripEnvQuotes(process.env.NEXT_PUBLIC_ANNUALADS_PARTNER_ID || '') ||
  annualAdsPartnerIdFromEmbedBase

export const ANNUALADS_ROTATOR_SCRIPT_URL = stripEnvQuotes(
  process.env.NEXT_PUBLIC_ANNUALADS_ROTATOR_SCRIPT_URL || 'https://www.annualads.com/rotator.js'
)

/** Origin only (for preconnect / dns-prefetch); works when API_URL includes /api/v1. */
export const API_ORIGIN = (() => {
  try {
    return new URL(API_URL).origin
  } catch {
    return 'https://myhigh5.com'
  }
})()

// ============================================
// Reown/WalletConnect Project ID
// ============================================
// REQUIRED: Get from https://cloud.reown.com
export const REOWN_PROJECT_ID = process.env.NEXT_PUBLIC_REOWN_PROJECT_ID || ''

// ============================================
// BSC — MyHigh5PaymentHub + USDT (must match backend BSC_* and deployed contract)
// ============================================
const BSC_DEFAULTS = {
  PAYMENT_CONTRACT: '0x12Ccb74E7A8B8f0fDc14e55A82C8693145e36EdA',
  USDT_ADDRESS: '0x55d398326f99059fF775485246999027B3197955',
  CHAIN_ID: 56,
  RPC_URL: 'https://bsc-dataseed.binance.org',
  EXPLORER_URL: 'https://bscscan.com',
  USDT_DECIMALS: 18
} as const

export const CONTRACTS = {
  PAYMENT_CONTRACT: process.env.NEXT_PUBLIC_BSC_PAYMENT_CONTRACT || BSC_DEFAULTS.PAYMENT_CONTRACT,
  USDT_ADDRESS: process.env.NEXT_PUBLIC_BSC_USDT_ADDRESS || BSC_DEFAULTS.USDT_ADDRESS,
  CHAIN_ID: Number(process.env.NEXT_PUBLIC_BSC_CHAIN_ID ?? BSC_DEFAULTS.CHAIN_ID),
  RPC_URL: process.env.NEXT_PUBLIC_BSC_RPC_URL || BSC_DEFAULTS.RPC_URL,
  EXPLORER_URL: process.env.NEXT_PUBLIC_BSC_EXPLORER_URL || BSC_DEFAULTS.EXPLORER_URL,
  USDT_DECIMALS: Number(process.env.NEXT_PUBLIC_BSC_USDT_DECIMALS ?? BSC_DEFAULTS.USDT_DECIMALS)
}

export const assertApiUrl = (): void => {
  if (!API_URL && typeof window !== 'undefined') {
    console.error('NEXT_PUBLIC_API_URL is not set. API calls will fail in production.')
  }
}

export const config = {
  api: {
    url: API_URL,
    timeout: 0,
    retries: 3
  },
  app: {
    name: 'MyHigh5',
    version: '1.0.0'
  }
}
