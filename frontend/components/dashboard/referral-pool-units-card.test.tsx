import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const lookup = (key: string): string =>
  (key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as
    | string
    | undefined) ?? key

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup }) }))

const get = vi.fn()
const post = vi.fn()
vi.mock('@/lib/api', () => ({ default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }))

import { ReferralPoolUnitsCard, allowedNow, unitsTotal, validQuantity } from './referral-pool-units-card'

function serve(eligibility: Record<string, unknown>, purchases: unknown[] = [], active = 0, total?: number) {
  get.mockImplementation((url: string) =>
    Promise.resolve(
      url.endsWith('/eligibility')
        ? {
            status: 200,
            data: {
              sales_enabled: true,
              unit_price: '100.00',
              currency: 'USD',
              eligible: true,
              reason: null,
              max_units_per_purchase: null,
              max_units_per_member: null,
              units_reserved: 0,
              kyc_approved: true,
              ...eligibility,
            },
          }
        : { status: 200, data: { active_units: active, purchases, page: 1, page_size: 10, total: total ?? purchases.length } },
    ),
  )
}

const bm = en.business_model

beforeEach(() => {
  get.mockReset()
  post.mockReset()
})

describe('ReferralPoolUnitsCard', () => {
  it('says purchases are currently unavailable and shows no payment button while sales are off', async () => {
    serve({ sales_enabled: false })
    render(<ReferralPoolUnitsCard />)
    await waitFor(() => expect(screen.getByTestId('units-unavailable')).toHaveTextContent('Purchases are currently unavailable.'))
    expect(screen.queryByRole('button', { name: bm.units_buy })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: bm.units_confirm })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(bm.units_quantity)).not.toBeInTheDocument()
  })

  it('explains a KYC restriction and shows the KYC status instead of offering the purchase', async () => {
    serve({ eligible: false, reason: 'KYC_REQUIRED', kyc_approved: false })
    render(<ReferralPoolUnitsCard />)
    await waitFor(() => expect(screen.getByTestId('units-ineligible')).toHaveTextContent(bm.units_reason_KYC_REQUIRED))
    expect(screen.getByTestId('units-kyc')).toHaveTextContent(bm.units_kyc_missing)
    expect(screen.queryByRole('button', { name: bm.units_buy })).not.toBeInTheDocument()
  })

  it('calculates the total, asks for confirmation, then starts one payment for the chosen quantity', async () => {
    serve({}, [], 2)
    post.mockResolvedValue({ status: 200, data: { checkout_url: null, invoice_url: null } })
    render(<ReferralPoolUnitsCard />)
    const input = await screen.findByLabelText(bm.units_quantity)
    expect(screen.getByTestId('units-kyc')).toHaveTextContent(bm.units_kyc_approved)
    fireEvent.change(input, { target: { value: '3' } })
    expect(screen.getByTestId('units-total')).toHaveTextContent('$300.00')
    expect(screen.getByTestId('units-active')).toHaveTextContent('2')
    fireEvent.click(screen.getByRole('button', { name: bm.units_buy }))
    expect(post).not.toHaveBeenCalled()                                       // review first
    expect(screen.getByTestId('units-review')).toHaveTextContent('3 x $100.00 = $300.00')
    expect(screen.getByTestId('units-review')).toHaveTextContent(bm.units_confirm_note)
    fireEvent.click(screen.getByRole('button', { name: bm.units_confirm }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
    const [url, body, config] = post.mock.calls[0]
    expect(url).toBe('/api/v1/payments/create')
    expect(body).toEqual({ product_code: 'referral_pool_entry', quantity: 3, amount: '300.00', currency: 'usd' })
    expect((config as { headers: Record<string, string> }).headers['Idempotency-Key']).toBeTruthy()
  })

  it('shows optional limits and refuses a non-integer, zero or over-limit quantity', async () => {
    serve({ max_units_per_purchase: 5, max_units_per_member: 8, units_reserved: 2 })
    render(<ReferralPoolUnitsCard />)
    const input = await screen.findByLabelText(bm.units_quantity)
    expect(screen.getByTestId('units-limit-purchase')).toHaveTextContent('5')
    expect(screen.getByTestId('units-limit-member')).toHaveTextContent('8')
    for (const bad of ['0', '2.5', '-1', 'abc', '6']) {
      fireEvent.change(input, { target: { value: bad } })
      expect(screen.getByRole('button', { name: bm.units_buy })).toBeDisabled()
    }
    fireEvent.change(input, { target: { value: '5' } })
    expect(screen.getByRole('button', { name: bm.units_buy })).toBeEnabled()
  })

  it('shows no limit when none is set, and a member at the limit cannot buy', async () => {
    serve({ max_units_per_member: 4, units_reserved: 4 })
    render(<ReferralPoolUnitsCard />)
    await waitFor(() => expect(screen.getByTestId('units-ineligible')).toHaveTextContent(bm.units_reason_MEMBER_LIMIT))
    expect(screen.getByTestId('units-limit-purchase')).toHaveTextContent(bm.units_no_limit)
    expect(screen.queryByRole('button', { name: bm.units_buy })).not.toBeInTheDocument()
  })

  it('lists purchase history with payment and refund status, one page at a time', async () => {
    serve(
      {},
      [
        { id: 7, quantity: 3, total_amount: '300.00', status: 'PARTIALLY_REFUNDED', payment: { deposit_id: 9, status: 'validated' },
          units: { ACTIVE: 1, REFUNDED: 1 }, refund: { refunded_units: 1, in_review_units: 1 } },
      ],
      1,
      25,
    )
    render(<ReferralPoolUnitsCard />)
    await waitFor(() => expect(screen.getByTestId('units-history')).toHaveTextContent(bm.units_status_PARTIALLY_REFUNDED))
    expect(screen.getByTestId('units-history')).toHaveTextContent('validated')
    expect(screen.getByTestId('units-refund-7')).toHaveTextContent(`1 ${bm.units_refunded}, 1 ${bm.units_refund_review}`)
    expect(get).toHaveBeenCalledWith('/api/v1/referral-pool/units/purchases', { params: { page: 1, page_size: 10 } })
    fireEvent.click(screen.getByRole('button', { name: en.referral_pool.page_next }))
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/api/v1/referral-pool/units/purchases', { params: { page: 2, page_size: 10 } }),
    )
  })
})

describe('unit helpers', () => {
  it('totals in cents and validates the quantity', () => {
    expect(unitsTotal(3, '100.00')).toBe('300.00')
    expect(unitsTotal(10000, '100.00')).toBe('1000000.00')
    expect(validQuantity('7', null)).toBe(7)
    expect(validQuantity('10001', null)).toBeNull()
    expect(validQuantity('3', 2)).toBeNull()
  })

  it('combines the per-purchase limit with what is left of the per-member limit', () => {
    expect(allowedNow({ max_units_per_purchase: null, max_units_per_member: null, units_reserved: 9 })).toBeNull()
    expect(allowedNow({ max_units_per_purchase: 5, max_units_per_member: 8, units_reserved: 6 })).toBe(2)
    expect(allowedNow({ max_units_per_purchase: 5, max_units_per_member: null, units_reserved: 6 })).toBe(5)
    expect(allowedNow({ max_units_per_purchase: null, max_units_per_member: 3, units_reserved: 5 })).toBe(0)
  })
})
