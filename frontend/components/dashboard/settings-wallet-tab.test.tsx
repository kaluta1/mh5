import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: () => '' }) }))
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ addToast: vi.fn() }) }))
vi.mock('@/lib/config', () => ({ getEffectiveApiUrl: () => 'https://api.example.test' }))

import { SettingsWalletTab } from './settings-wallet-tab'

// Synthetic values only.
const wallet = (over: Record<string, unknown> = {}) => ({
  usdt_wallet_address: '0x' + 'a'.repeat(40), payout_currency: 'usdtbsc', wallet_configured: true,
  wallet_status: 'UNVERIFIED', supported_currencies: ['usdtbsc'], hold_hours: 72,
  pending_wallet: { wallet: '0xbbbb...bbbb', payout_currency: 'usdtbsc', network: 'USDT BSC (BEP20)',
    expires_at: '2026-10-19T12:00:00' },
  ...over,
})

describe('SettingsWalletTab: a wallet change waiting for its email confirmation', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => wallet() })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('says payouts are paused, then reviewed, and that the hold starts at the confirmation', async () => {
    render(<SettingsWalletTab />)
    expect(await screen.findByTestId('pending-wallet')).toHaveTextContent('0xbbbb...bbbb')
    const paused = screen.getByTestId('pending-wallet-paused')
    expect(paused).toHaveTextContent('Payouts are paused: nothing is paid to your previous wallet.')
    expect(paused).toHaveTextContent('an administrator reviews the new wallet')
    expect(paused).toHaveTextContent('72-hour security hold starts from your confirmation')
  })
})
