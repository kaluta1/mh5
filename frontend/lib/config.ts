/**
 * Frontend Configuration
 * Single source for backend URL: set NEXT_PUBLIC_API_URL in Vercel to your Render backend URL.
 */

/** Default backend URL when NEXT_PUBLIC_API_URL is not set (e.g. production Render service name) */
export const DEFAULT_PUBLIC_API_URL = 'https://mh5-backend.onrender.com'

const normalizeApiUrl = (url: string): string => {
  if (!url) return ''
  let normalized = url.replace(/\/+$/, '')
  if (typeof window !== 'undefined' && window.location.protocol === 'https:' && normalized.startsWith('http://')) {
    normalized = normalized.replace('http://', 'https://')
  }
  return normalized
}

const rawApiUrl = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || ''
const isProduction = process.env.NODE_ENV === 'production'
const fallbackUrl = isProduction ? DEFAULT_PUBLIC_API_URL : 'http://localhost:8000'

export const API_URL = normalizeApiUrl(rawApiUrl || fallbackUrl)

// ============================================
// Reown/WalletConnect Project ID
// ============================================
// REQUIRED: Get from https://cloud.reown.com
export const REOWN_PROJECT_ID = process.env.NEXT_PUBLIC_REOWN_PROJECT_ID || ''

// ============================================
// Contract Addresses and Configuration
// ============================================
export const CONTRACTS = {
  PAYMENT_CONTRACT: '0xC003750eDf5feEFBf94FB4B754D70f2b73392Ea9',
  USDT_ADDRESS: '0x55d398326f99059fF775485246999027B3197955',
  CHAIN_ID: 56,
  RPC_URL: 'https://bsc-dataseed.binance.org',
  EXPLORER_URL: 'https://bscscan.com',
  USDT_DECIMALS: 18
} as const

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
