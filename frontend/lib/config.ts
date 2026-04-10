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

const rawApiUrl = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || ''
const isProduction = process.env.NODE_ENV === 'production'
const fallbackUrl = isProduction ? DEFAULT_PUBLIC_API_URL : 'http://localhost:8000'

export const API_URL = normalizeApiUrl(rawApiUrl || fallbackUrl)

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
