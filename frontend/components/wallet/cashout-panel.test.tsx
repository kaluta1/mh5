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
  minimum_received: 0.01, provider: 'NOWPayments', limit_applies_to: 'ESTIMATE' as const, actual_fee_guaranteed: false,
  accepted: false, accepted_at: null, expires_at: null, ...over })

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
    expect(block).toHaveTextContent('You pay the blockchain network fee')                   // who pays
    expect(block).toHaveTextContent('NOWPayments deducts the fee from the amount sent to you')   // who deducts
    expect(block).toHaveTextContent('You receive the remaining amount')                     // what arrives
    expect(block).toHaveTextContent('gives an estimate of the fee')                         // what is shown
    expect(block).toHaveTextContent('MyHigh5 charges no fee of its own')
    expect(block).toHaveTextContent('10% of the payout or $1.00, whichever is lower')
    // The limit is on the estimate. Nothing here may read as a limit on the actual fee.
    const caveat = screen.getByTestId('fee-terms-not-guaranteed')
    expect(caveat).toHaveTextContent('This limit applies to the estimate only')
    expect(caveat).toHaveTextContent('may differ from the estimate')
    expect(caveat).toHaveTextContent('can be higher than the limit')
    expect(caveat).toHaveTextContent('not guaranteed to stay below it')
    const consent = within(block).getByRole('checkbox').closest('label')!
    expect(consent).toHaveTextContent('I pay the network fee')
    expect(consent).toHaveTextContent('NOWPayments deducts it and I receive the remaining amount')
    expect(consent).toHaveTextContent('is checked against an estimate')
    expect(consent).toHaveTextContent('not guaranteed to stay below it')
    expect(block.textContent).not.toMatch(/up to \$|up to 10%|never more than|at most/i)
    expect(screen.getByRole('status')).toHaveTextContent('accept the network fee terms')
    const accept = within(block).getByRole('button', { name: 'Accept network fee terms' })
    expect(accept).toBeDisabled()                                   // nothing is accepted by default
    fireEvent.click(within(block).getByRole('checkbox'))
    fireEvent.click(accept)
    // Exactly the terms that were shown are sent back.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('https://api.test/api/v1/payments/cashout-fee-terms/accept',
      expect.objectContaining({ method: 'POST',
        body: JSON.stringify({ version: 3, cap_percent: '10', cap_usd: '1', accept: true }) })))
    expect(await screen.findByTestId('fee-terms-accepted')).toHaveTextContent('Accepted on')
    expect(addToast).toHaveBeenCalledWith(expect.stringContaining('the actual fee may differ'), 'success')
    expect(screen.getByRole('status')).toHaveTextContent('less the network fee')
    expect(screen.getByRole('status')).toHaveTextContent('the actual fee may differ')
  })

  it('lets the member withdraw the acceptance', async () => {
    current = summary({ status: 'AUTOMATIC_PAYOUT_PENDING' }, { accepted: true, accepted_at: '2026-10-11T09:00:00' })
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw acceptance' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('https://api.test/api/v1/payments/cashout-fee-terms/withdraw',
      expect.objectContaining({ method: 'POST' })))
    expect(await screen.findByRole('button', { name: 'Accept network fee terms' })).toBeDisabled()
  })

  it('names the provider the server names, and falls back to a neutral wording', async () => {
    current = summary({}, { provider: undefined })
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    const block = await screen.findByTestId('fee-terms')
    expect(block).toHaveTextContent('The payment provider deducts the fee from the amount sent to you')
    expect(block).not.toHaveTextContent('NOWPayments')
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

  it('never shows historical held commissions as available, and shows the wallet approval', async () => {
    current = summary({
      status: 'WALLET_APPROVAL_PENDING',
      balances: { total_earned: 9.6, pending: 0, available: 2, reserved: 1, paid: 1, held: 15.6,
        available_unpaid: 2, awaiting_wallet_approval: 2, processing: 1 },
      wallet_approval: { status: 'PENDING', wallet: '0xaaaa...aaaa', network: 'USDT BSC (BEP20)',
        submitted_at: '2026-10-18T09:00:00', decided_at: null, reason: null },
    })
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    await screen.findByTestId('cashout-panel')
    expect(screen.getByTestId('balance-available')).toHaveTextContent('$2.00')
    expect(screen.getByTestId('balance-awaiting')).toHaveTextContent('$2.00')
    expect(screen.getByTestId('balance-processing')).toHaveTextContent('$1.00')
    expect(screen.getByTestId('balance-paid')).toHaveTextContent('$1.00')
    expect(screen.getByTestId('balance-held')).toHaveTextContent('$15.60')
    expect(screen.getByTestId('held-note')).toHaveTextContent('not available')
    expect(screen.getByTestId('wallet-approval')).toHaveTextContent('waiting for approval')
    expect(screen.getByRole('status')).toHaveTextContent('waiting for approval by MyHigh5')
  })

  it('shows the reason of a rejected wallet', async () => {
    current = summary({
      status: 'WALLET_REJECTED',
      wallet_approval: { status: 'REJECTED', wallet: '0xaaaa...aaaa', network: 'USDT BSC (BEP20)',
        submitted_at: '2026-10-18T09:00:00', decided_at: '2026-10-18T10:00:00', reason: 'Exchange deposit address' },
    })
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    expect(await screen.findByTestId('wallet-approval')).toHaveTextContent('Reason: Exchange deposit address')
  })

  it('links each individual payout to its blockchain transaction', async () => {
    const hash = '0x' + 'a'.repeat(64)
    history = [{ id: 7, method: 'CRYPTO', status: 'completed', gross_amount: 1, fee: 0, net_amount: 0.98,
      requested_at: '2026-10-18T09:00:00', commission_id: 42, tx_hash: hash,
      explorer_url: `https://bscscan.com/tx/${hash}` }]
    current = summary({ status: 'AUTOMATIC_PAYOUT_PENDING' }, { accepted: true, accepted_at: '2026-10-09T09:00:00' })
    render(<CashoutPanel onRequestUsd={() => undefined} />)
    const link = await screen.findByTestId('tx-link')
    expect(link).toHaveAttribute('href', `https://bscscan.com/tx/${hash}`)
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveTextContent('0xaaaaaa...aaaaaa')
    expect(screen.getByText('Commission #42')).toBeInTheDocument()
  })
})
