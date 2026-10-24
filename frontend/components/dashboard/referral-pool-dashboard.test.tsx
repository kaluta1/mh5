import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const lookup = (key: string): string =>
  (key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as
    | string
    | undefined) ?? key

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup }) }))

const get = vi.fn()
vi.mock('@/lib/api', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

import { ReferralPoolDashboard, type PoolDashboard } from './referral-pool-dashboard'

const rp = en.referral_pool

function board(overrides: Partial<PoolDashboard> = {}): PoolDashboard {
  return {
    sales_enabled: false,
    allocation_enabled: false,
    units: { purchased: 5, active: 3, suspended: 1, refunded: 1, revoked: 0, pending: 0, waiting_for_next_round: 1 },
    pending_purchases: { count: 1, units: 4 },
    amounts: { paid: '500.00', refunded: '100.00', net_spent: '400.00', currency: 'USD' },
    current_round: null,
    my_slots: { open: 0, filled: 0, void: 0 },
    assignments: { round_based: 0, historical: 2 },
    recent_assignments: [],
    waiting_referrals: 3,
    my_queue_entry: null,
    ...overrides,
  }
}

function serve(data: PoolDashboard, history: unknown[] = [], total?: number) {
  get.mockImplementation((url: string, config?: { params?: { page?: number } }) =>
    Promise.resolve(
      url.endsWith('/dashboard')
        ? { status: 200, data }
        : { status: 200, data: { items: history, page: config?.params?.page ?? 1, page_size: 10, total: total ?? history.length } },
    ),
  )
}

beforeEach(() => {
  get.mockReset()
})

describe('ReferralPoolDashboard', () => {
  it('shows the member totals for every unit state and the net amount spent', async () => {
    serve(board())
    render(<ReferralPoolDashboard />)
    await waitFor(() => expect(screen.getByTestId('stat-purchased')).toHaveTextContent('5'))
    expect(screen.getByTestId('stat-active')).toHaveTextContent('3')
    expect(screen.getByTestId('stat-suspended')).toHaveTextContent('1')
    expect(screen.getByTestId('stat-refunded')).toHaveTextContent('1')
    expect(screen.getByTestId('stat-pending')).toHaveTextContent('1')
    expect(screen.getByTestId('stat-spent')).toHaveTextContent('$400.00')
    expect(screen.getByTestId('stat-next-round')).toHaveTextContent('1')
  })

  it('states that purchases and allocation are unavailable while switched off, and that referrals are not guaranteed', async () => {
    serve(board())
    render(<ReferralPoolDashboard />)
    const status = await screen.findByTestId('pool-launch-status')
    expect(status).toHaveTextContent(rp.status_sales_off)
    expect(status).toHaveTextContent(rp.status_allocation_off)
    expect(status).toHaveTextContent(rp.not_guaranteed)
    expect(screen.getByTestId('pool-no-round')).toHaveTextContent(rp.round_none)
  })

  it('keeps allocation slots in the current round apart from referrals actually received', async () => {
    serve(board({
      allocation_enabled: true,
      current_round: { round_number: 4, status: 'OPEN', total_slots: 20, filled_slots: 6, void_slots: 1, remaining_slots: 13 },
      my_slots: { open: 2, filled: 1, void: 0 },
      assignments: { round_based: 7, historical: 2 },
    }))
    render(<ReferralPoolDashboard />)
    const round = await screen.findByTestId('pool-round')
    expect(round).toHaveTextContent(`${rp.round_number} 4`)
    expect(round).toHaveTextContent(`${rp.round_remaining}: 13`)
    expect(screen.getByTestId('slots-open')).toHaveTextContent('2')
    expect(screen.getByTestId('slots-filled')).toHaveTextContent('1')
    expect(screen.getByTestId('assigned-round')).toHaveTextContent('7')
    expect(screen.getByTestId('assigned-historical')).toHaveTextContent('2')
    expect(screen.getByText(rp.slots_hint)).toBeInTheDocument()
  })

  it('pages through the assignment history and shows the member own queue status', async () => {
    serve(
      board({ my_queue_entry: { status: 'WAITING', enqueued_at: '2026-10-24T10:00:00' } }),
      [
        { id: 3, assigned_at: '2026-10-24T10:00:00', round_number: 2, kind: 'ROUND' },
        { id: 1, assigned_at: '2026-09-01T10:00:00', round_number: null, kind: 'HISTORICAL' },
      ],
      12,
    )
    render(<ReferralPoolDashboard />)
    const list = await screen.findByTestId('assignment-history')
    expect(list).toHaveTextContent(`${rp.kind_ROUND} 2`)
    expect(list).toHaveTextContent(rp.kind_HISTORICAL)
    expect(screen.getByTestId('pool-my-queue')).toHaveTextContent(rp.queue_WAITING)
    fireEvent.click(screen.getByRole('button', { name: rp.page_next }))
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/api/v1/referral-pool/units/assignments', { params: { page: 2, page_size: 10 } }),
    )
  })
})
