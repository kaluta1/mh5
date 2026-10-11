import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CashoutRecord, CashoutSummary } from '@/lib/cashout'

const addToast = vi.fn()
vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: (key: string) => key }) }))
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ addToast }) }))
vi.mock('@/lib/config', () => ({ getEffectiveApiUrl: () => 'https://api.test' }))
vi.mock('next/link', () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }))

import { CashoutPanel } from './cashout-panel'

// Synthetic limits for the test only; they are not a policy.
const terms = (over = {}) => ({ available: true, version: 3, cap_percent: '10', cap_usd: '1', valid_days: 0,
  minimum_received: 0.01, accepted: false, accepted_at: null, expires_at: null, ...over })

function summary(over: Partial<CashoutSummary> = {}, termsOver = {}): CashoutSummary {
  return {
    cashout_method: 'CRYPTO', status: 'FEE_TERMS_REQUIRED',
    balances: { total_earned: 5, pending: 0, available: 5, reserved: 0, paid: 0 },
    payable_amount: 5, minimum: 1, minimums: { CRYPTO: 1, USD: 100 },
    fees: {
      CRYPTO: { platform_fee: 0, network_fee_policy: 'MEMBER_PAYS', terms: terms(termsOver),
        note: 'No MyHigh5 fee. The blockchain network fee is taken out of the amount sent: you receive the payout less that fee.' },
      USD: { rule: '1% of the amount, minimum $20, maximum $1,000', fee: null, net_amount: null },
    },
    destination: { type: 'CRYPTO', wallet: '0xaaaa...aaaa', wallet_status: 'VERIFIED', payout_currency: 'usdtbsc',
      payable_from: null, network: 'USDT BSC (BEP20)' },
    crypto_payouts_active: true, usd_settlement_active: false, active_cashout: null, ...over,
  }
}

let history: CashoutRecord[] = []
let current: CashoutSummary
const fetchMock = vi.fn()

beforeEach(() => {
  history = []
  current = summary()
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const ok = (data: unknown) => Promise.resolve({ ok: true, json: () => Promise.resolve(data) })
    if (url.endsWith('/wallet/cashout/history?limit=20')) return ok(history)
    if (url.endsWith('/wallet/cashout')) return ok(current)
    if (url.endsWith('/cashout-fee-terms/accept') && init?.method === 'POST') {
      current = summary({ status: 'AUTOMATIC_PAYOUT_PENDING' }, { accepted: true, accepted_at: '2026-10-11T09:00:00' })
      return ok(current)
    }
    if (url.endsWith('/cashout-fee-terms/withdraw') && init?.method === 'POST') {
      current = summary()
      return ok(current)
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({ detail: 'Not found' }) })
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('CashoutPanel: network fee terms', () => {
  it('states that the member pays the fee and the limit, and accepts only after an explicit tick', async () => {
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    const block = await screen.findByTestId('fee-terms')
    expect(block).toHaveTextContent('paid by you')
    expect(block).toHaveTextContent('taken out of the amount sent')
    expect(block).toHaveTextContent('MyHigh5 charges no fee of its own')
    expect(block).toHaveTextContent('10% of the payout or $1.00, whichever is lower')
    expect(screen.getByRole('status')).toHaveTextContent('Accept the network fee terms')
    const accept = within(block).getByRole('button', { name: 'Accept network fee terms' })
    expect(accept).toBeDisabled()                                   // nothing is accepted by default
    fireEvent.click(within(block).getByRole('checkbox'))
    fireEvent.click(accept)
    // Exactly the terms that were shown are sent back.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('https://api.test/api/v1/payments/cashout-fee-terms/accept',
      expect.objectContaining({ method: 'POST',
        body: JSON.stringify({ version: 3, cap_percent: '10', cap_usd: '1', accept: true }) })))
    expect(await screen.findByTestId('fee-terms-accepted')).toHaveTextContent('Accepted on')
    expect(screen.getByRole('status')).toHaveTextContent('sent to your wallet automatically')
  })

  it('lets the member withdraw the acceptance', async () => {
    current = summary({ status: 'AUTOMATIC_PAYOUT_PENDING' }, { accepted: true, accepted_at: '2026-10-11T09:00:00' })
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw acceptance' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('https://api.test/api/v1/payments/cashout-fee-terms/withdraw',
      expect.objectContaining({ method: 'POST' })))
    expect(await screen.findByRole('button', { name: 'Accept network fee terms' })).toBeDisabled()
  })

  it('offers nothing to accept while the terms are not on offer', async () => {
    current = summary({ status: 'AUTOMATIC_PAYOUT_NOT_ACTIVE', crypto_payouts_active: false }, { available: false })
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    await screen.findByTestId('cashout-panel')
    expect(screen.queryByTestId('fee-terms')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('not active yet')
  })

  it('shows the estimate as an estimate, and the actual fee and amount received once known', async () => {
    const base = { method: 'CRYPTO' as const, gross_amount: 5, fee: 0, net_amount: 4.7, network_fee_policy: 'MEMBER_PAYS' as const,
      requested_at: '2026-10-10T08:00:00' }
    history = [
      { ...base, id: 2, status: 'processing', beneficiary_fee: { applies: true, gross: '5.00', estimate: '0.3', actual: null,
        net_received: null, fee_cap: '0.5', status: 'NOT_APPLICABLE' } },
      { ...base, id: 1, status: 'completed', beneficiary_fee: { applies: true, gross: '5.00', estimate: '0.3', actual: '0.2874',
        net_received: '4.7126', fee_cap: '0.5', status: 'RECORDED' } },
    ]
    current = summary({ status: 'IN_PROGRESS' }, { accepted: true, accepted_at: '2026-10-09T09:00:00' })
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    const rows = (await screen.findAllByRole('row')).slice(1)
    expect(rows[0]).toHaveTextContent('about $0.30 network fee (estimate)')
    expect(rows[0]).toHaveTextContent('$4.70')
    expect(rows[1]).toHaveTextContent('$0.2874 network fee')
    expect(rows[1]).toHaveTextContent('$4.7126')
    expect(rows[1]).not.toHaveTextContent('estimate')
  })
})
