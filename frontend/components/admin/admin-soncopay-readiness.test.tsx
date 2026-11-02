import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: getMock }, apiService: {} }))

import AdminSoncoPayReadiness from './admin-soncopay-readiness'

const DATA = {
  checked_at: '2026-11-02T12:00:00Z',
  provider_read: false,
  items: [
    { key: 'webhook_verification', label: 'Webhook verification', status: 'READY', kind: 'code', evidence: 'HMAC-SHA256' },
    { key: 'payout_authorization', label: 'Provider payout authorization', status: 'BLOCKED', kind: 'operational',
      evidence: 'SONCOPAY_PAYOUTS_NOT_AUTHORIZED' },
    { key: 'provider_balance', label: 'Provider balance', status: 'NOT_VERIFIED', kind: 'operational', evidence: 'Not read' },
  ],
  counts: { READY: 1, BLOCKED: 1, NOT_VERIFIED: 1, NOT_APPLICABLE: 0 },
  switches: { automatic_payout_activated: false, annual_ads_enabled: false },
  payment_reconciliation: {
    deposits: { by_status: {}, validated: 0, with_processed_webhook: 0 },
    webhooks: { total: 0, last_received_at: null, by_outcome: {} },
    problems: [{ type: 'PAID_NOT_CONFIRMED', severity: 'critical', message: 'Deposit #5: SoncoPay reports it paid.' }],
    critical: 1,
  },
}

describe('AdminSoncoPayReadiness', () => {
  beforeEach(() => { getMock.mockReset() })

  it('shows every item with its status, the switches and the reconciliation', async () => {
    getMock.mockResolvedValue({ status: 200, data: DATA })
    render(<AdminSoncoPayReadiness />)
    expect(await screen.findByTestId('sp-ready-webhook_verification')).toHaveTextContent('READY')
    expect(screen.getByTestId('sp-ready-payout_authorization')).toHaveTextContent('BLOCKED')
    expect(screen.getByTestId('sp-ready-provider_balance')).toHaveTextContent('NOT VERIFIED')
    expect(screen.getByTestId('sp-readiness-switches')).toHaveTextContent('Automatic payouts activated (server): OFF')
    expect(screen.getByTestId('sp-payment-reconciliation')).toHaveTextContent('Deposit #5')
    expect(getMock).toHaveBeenCalledWith('/api/v1/admin/finance/soncopay/readiness')
  })

  it('reads SoncoPay only when asked', async () => {
    getMock.mockResolvedValue({ status: 200, data: DATA })
    render(<AdminSoncoPayReadiness />)
    await screen.findByTestId('sp-readiness-table')
    fireEvent.click(screen.getByRole('button', { name: 'Read SoncoPay (read-only)' }))
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/api/v1/admin/finance/soncopay/readiness?provider=true'))
  })

  it('shows a refusal without crashing', async () => {
    getMock.mockResolvedValue({ status: 403, data: { detail: { code: 'FORBIDDEN', message: 'A finance permission is required.' } } })
    render(<AdminSoncoPayReadiness />)
    expect(await screen.findByRole('alert')).toHaveTextContent('A finance permission is required.')
  })
})
