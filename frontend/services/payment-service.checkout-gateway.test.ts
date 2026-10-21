import { afterEach, describe, expect, it, vi } from 'vitest'

import { CheckoutUnavailableError } from '@/lib/payment-gateway'

import { paymentService } from './payment-service'

// Synthetic values only.
const reply = (status: number, body: unknown) =>
  vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body })

afterEach(() => vi.unstubAllGlobals())

describe('paymentService.getCheckoutGateway fails closed', () => {
  it('uses a gateway only when the server confirms it is available', async () => {
    vi.stubGlobal('fetch', reply(200, { provider: 'nowpayments', available: true }))
    expect(await paymentService.getCheckoutGateway('synthetic-token')).toBe('nowpayments')
    vi.stubGlobal('fetch', reply(200, { provider: 'soncopay', available: true }))
    expect(await paymentService.getCheckoutGateway('synthetic-token')).toBe('soncopay')
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    expect(String(fetchMock.mock.calls[0][0])).toContain('/checkout-gateway')
  })

  it('is unavailable when the server says no gateway can take a payment', async () => {
    vi.stubGlobal('fetch', reply(200, { provider: 'none', available: false, message: 'Payments are temporarily unavailable.' }))
    expect(await paymentService.getCheckoutGateway('synthetic-token')).toBe('unavailable')
  })

  it('is unavailable on any HTTP error, never NOWPayments', async () => {
    for (const status of [400, 401, 403, 404, 429, 500, 502, 503]) {
      vi.stubGlobal('fetch', reply(status, { provider: 'nowpayments', available: true }))
      expect(await paymentService.getCheckoutGateway('synthetic-token')).toBe('unavailable')
    }
  })

  it('is unavailable when the request fails on the network', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    expect(await paymentService.getCheckoutGateway('synthetic-token')).toBe('unavailable')
  })

  it('is unavailable when the body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token <') },
    }))
    expect(await paymentService.getCheckoutGateway('synthetic-token')).toBe('unavailable')
  })

  it('is unavailable for any answer it cannot read as a confirmed gateway', async () => {
    for (const body of [null, undefined, 'nowpayments', 1, [], {}, { provider: 'nowpayments' },
      { provider: 'soncopay' }, { provider: 'nowpayments', available: 'true' }, { provider: 'nowpayments', available: 1 },
      { provider: 'paypal', available: true }, { provider: 'none', available: true }, { available: true }]) {
      vi.stubGlobal('fetch', reply(200, body))
      expect(await paymentService.getCheckoutGateway('synthetic-token')).toBe('unavailable')
    }
  })
})

describe('paymentService.createPayment when the server refuses a new payment', () => {
  const request = { amount: 10, currency: 'usd', product_code: 'kyc', pay_currency: 'usdtbsc', recipients: [] }

  it('reports CHECKOUT_UNAVAILABLE as its own error', async () => {
    vi.stubGlobal('fetch', reply(503, { detail: { code: 'CHECKOUT_UNAVAILABLE',
      message: 'Payments are temporarily unavailable. Please try again later.' } }))
    await expect(paymentService.createPayment('synthetic-token', request, 'k-1')).rejects.toBeInstanceOf(CheckoutUnavailableError)
  })

  it('keeps every other refusal an ordinary error', async () => {
    for (const [status, detail] of [[503, 'busy'], [409, { code: 'CHECKOUT_UNAVAILABLE', message: 'x' }],
      [503, { code: 'OTHER', message: 'Other' }]] as const) {
      vi.stubGlobal('fetch', reply(status, { detail }))
      const error = await paymentService.createPayment('synthetic-token', request, 'k-1').catch((e) => e)
      expect(error).toBeInstanceOf(Error)
      expect(error).not.toBeInstanceOf(CheckoutUnavailableError)
    }
  })
})
