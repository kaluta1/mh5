import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { service } = vi.hoisted(() => ({
  service: {
    getCheckoutGateway: vi.fn(),
    getAvailableCurrencies: vi.fn(),
    createPayment: vi.fn(),
    getPaymentStatus: vi.fn(),
    syncPayment: vi.fn(),
    verifyUser: vi.fn(),
  },
}))

// One stable language object, as the real context gives: a new `t` per render would re-run the
// dialogs' data effects on every render.
const { language } = vi.hoisted(() => ({ language: { t: () => '', language: 'en' } }))
vi.mock('@/contexts/language-context', () => ({ useLanguage: () => language }))
vi.mock('@/hooks/use-auth', () => ({ useAuth: () => ({ user: { username: 'buyer', email: 'buyer@example.test' } }) }))
const { kyc } = vi.hoisted(() => ({ kyc: { getKycFee: vi.fn() } }))
vi.mock('@/services/kyc-service', () => ({ kycService: kyc }))
vi.mock('@/services/payment-service', () => ({ paymentService: service }))

import { CheckoutUnavailableError } from '@/lib/payment-gateway'
import { PaymentDialog } from './payment-dialog-v2'
import { ResumePaymentDialog } from './resume-payment-dialog'

// Synthetic values only.
const CHECKOUT = 'https://soncopay.com/pay/pay_00000000000000000001'
const soncopayPayment = {
  deposit_id: 41, order_id: 'mh5-idem-synthetic', payment_id: 'pay_00000000000000000001', payment_status: 'new',
  pay_address: '', pay_amount: '', pay_currency: '', price_amount: 10, price_currency: 'usd', invoice_url: CHECKOUT,
  status: 'pending', provider: 'soncopay', checkout_url: CHECKOUT,
}

beforeEach(() => {
  kyc.getKycFee.mockReset().mockResolvedValue({ amount: 5, currency: 'USD', is_free: false })     // the configured member fee
  localStorage.setItem('access_token', 'synthetic-token')
  for (const fn of Object.values(service)) fn.mockReset()
  service.getAvailableCurrencies.mockResolvedValue(['usdtbsc'])
  service.getPaymentStatus.mockResolvedValue({ deposit_id: 41, status: 'pending', payment_status: 'new',
    payment_state: 'pending', is_confirmed: false, provider: 'soncopay', price_amount: 10, price_currency: 'usd' })
})

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

async function toMethodStep() {
  render(<PaymentDialog open onOpenChange={() => {}} initialProductCode="kyc" />)
  await waitFor(() => expect(service.getCheckoutGateway).toHaveBeenCalled())
  const next = await screen.findByRole('button', { name: /Continuer/ })
  await waitFor(() => expect(next).toBeEnabled())                       // once the server's fee has arrived
  fireEvent.click(next)
}

describe('Payment dialog with SoncoPay as the gateway', () => {
  it('offers one SoncoPay choice, then the secure SoncoPay page, never an address', async () => {
    service.getCheckoutGateway.mockResolvedValue('soncopay')
    service.createPayment.mockResolvedValue(soncopayPayment)
    await toMethodStep()
    fireEvent.click(await screen.findByTestId('pay-with-soncopay'))
    await screen.findByTestId('soncopay-payment-step')
    expect(service.getAvailableCurrencies).not.toHaveBeenCalled()       // NOWPayments currencies are not loaded
    expect(service.createPayment.mock.calls[0][1].pay_currency).toBeUndefined()
    const link = screen.getByTestId('soncopay-checkout-link') as HTMLAnchorElement
    expect(link.href).toBe(CHECKOUT)
    expect(link.target).toBe('_blank')
    expect(link.rel).toContain('noopener')
    expect(screen.queryByText(/Receiving address/)).toBeNull()
    expect(await screen.findByTestId('soncopay-status')).toHaveTextContent('Waiting for your payment')
  })

  it('shows the confirmation only when OUR server reports the payment confirmed', async () => {
    service.getCheckoutGateway.mockResolvedValue('soncopay')
    service.createPayment.mockResolvedValue(soncopayPayment)
    service.getPaymentStatus.mockResolvedValue({ deposit_id: 41, status: 'validated', payment_status: 'paid',
      payment_state: 'paid', is_confirmed: true, provider: 'soncopay', price_amount: 10, price_currency: 'usd' })
    await toMethodStep()
    fireEvent.click(await screen.findByTestId('pay-with-soncopay'))
    expect((await screen.findAllByText('Payment confirmed!')).length).toBeGreaterThan(0)
  })

  it('never opens a checkout page that is not https on SoncoPay', async () => {
    service.getCheckoutGateway.mockResolvedValue('soncopay')
    service.createPayment.mockResolvedValue({ ...soncopayPayment, checkout_url: 'javascript:alert(1)' })
    await toMethodStep()
    fireEvent.click(await screen.findByTestId('pay-with-soncopay'))
    await screen.findByTestId('soncopay-payment-step')
    expect(screen.queryByTestId('soncopay-checkout-link')).toBeNull()
    expect(screen.getByText(/payment page is not available/)).toBeInTheDocument()
  })

  it('offers nothing and says payments are unavailable when no gateway can take a payment', async () => {
    service.getCheckoutGateway.mockResolvedValue('unavailable')
    await toMethodStep()
    expect(await screen.findByTestId('checkout-unavailable')).toHaveTextContent('temporarily unavailable')
    expect(screen.queryByTestId('pay-with-soncopay')).toBeNull()
    expect(screen.queryByText('USDT (BSC / BEP20)')).toBeNull()
    expect(service.getAvailableCurrencies).not.toHaveBeenCalled()      // no silent NOWPayments fallback
    expect(service.createPayment).not.toHaveBeenCalled()
  })

  it('keeps the NOWPayments currencies when NOWPayments is the gateway', async () => {
    service.getCheckoutGateway.mockResolvedValue('nowpayments')
    await toMethodStep()
    expect(await screen.findByText('USDT (BSC / BEP20)')).toBeInTheDocument()
    expect(screen.queryByTestId('pay-with-soncopay')).toBeNull()
  })

  it('offers nothing and loads no currencies until the server has confirmed a gateway', async () => {
    service.getCheckoutGateway.mockReturnValue(new Promise(() => {}))   // the answer never arrives
    await toMethodStep()
    expect(await screen.findByTestId('checkout-checking')).toBeInTheDocument()
    expect(screen.queryByTestId('pay-with-soncopay')).toBeNull()
    expect(screen.queryByText('USDT (BSC / BEP20)')).toBeNull()
    expect(screen.queryByTestId('checkout-unavailable')).toBeNull()
    expect(service.getAvailableCurrencies).not.toHaveBeenCalled()
    expect(service.createPayment).not.toHaveBeenCalled()
  })

  it('shows the configured KYC fee, never an assumed one, and pays exactly that amount', async () => {
    service.getCheckoutGateway.mockResolvedValue('soncopay')
    service.createPayment.mockResolvedValue({ ...soncopayPayment, price_amount: 5 })
    await toMethodStep()
    fireEvent.click(await screen.findByTestId('pay-with-soncopay'))
    await waitFor(() => expect(service.createPayment).toHaveBeenCalledTimes(1))
    expect(service.createPayment.mock.calls[0][1].amount).toBe(5)
  })

  it('offers no KYC payment while the fee is unknown', async () => {
    kyc.getKycFee.mockResolvedValue(null)
    service.getCheckoutGateway.mockResolvedValue('soncopay')
    render(<PaymentDialog open onOpenChange={() => {}} initialProductCode="kyc" />)
    await waitFor(() => expect(kyc.getKycFee).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: /Continuer/ })).toBeDisabled()
    expect(screen.queryByText('$10')).toBeNull()
    expect(screen.getByText('$…')).toBeInTheDocument()
    expect(service.createPayment).not.toHaveBeenCalled()
  })

  it('is unavailable without a session, and asks no gateway', async () => {
    localStorage.clear()
    render(<PaymentDialog open onOpenChange={() => {}} initialProductCode="kyc" />)
    expect(await screen.findByRole('button', { name: /Continuer/ })).toBeDisabled()   // no fee without a session
    expect(kyc.getKycFee).not.toHaveBeenCalled()
    expect(service.getCheckoutGateway).not.toHaveBeenCalled()
    expect(service.getAvailableCurrencies).not.toHaveBeenCalled()
  })

  it('a stale method button cannot start a payment once checkout became unavailable', async () => {
    // Confirmed when the dialog opened; switched off before the member clicks (the button is still on screen).
    service.getCheckoutGateway.mockResolvedValueOnce('nowpayments').mockResolvedValue('unavailable')
    await toMethodStep()
    fireEvent.click(await screen.findByText('USDT (BSC / BEP20)'))
    expect(await screen.findByTestId('checkout-unavailable')).toHaveTextContent('temporarily unavailable')
    expect(service.getCheckoutGateway).toHaveBeenCalledTimes(2)          // asked again at the click
    expect(service.createPayment).not.toHaveBeenCalled()
    expect(screen.queryByText('USDT (BSC / BEP20)')).toBeNull()
  })

  it('a stale NOWPayments button does not pay through NOWPayments once SoncoPay became the gateway', async () => {
    service.getCheckoutGateway.mockResolvedValueOnce('nowpayments').mockResolvedValue('soncopay')
    await toMethodStep()
    fireEvent.click(await screen.findByText('USDT (BSC / BEP20)'))
    expect(await screen.findByTestId('pay-with-soncopay')).toBeInTheDocument()
    expect(service.createPayment).not.toHaveBeenCalled()
  })

  it('shows the unavailable state when the server refuses the new payment (503 CHECKOUT_UNAVAILABLE)', async () => {
    service.getCheckoutGateway.mockResolvedValue('nowpayments')
    service.createPayment.mockRejectedValue(new CheckoutUnavailableError())
    await toMethodStep()
    fireEvent.click(await screen.findByText('USDT (BSC / BEP20)'))
    expect(await screen.findByTestId('checkout-unavailable')).toBeInTheDocument()
    expect(service.createPayment).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('USDT (BSC / BEP20)')).toBeNull()
  })

  it('creates a NOWPayments USDT BEP20 payment when the server confirmed NOWPayments', async () => {
    service.getCheckoutGateway.mockResolvedValue('nowpayments')
    service.createPayment.mockResolvedValue({ ...soncopayPayment, provider: 'nowpayments', checkout_url: undefined,
      pay_address: '0xsyntheticaddress', pay_amount: '10.0', pay_currency: 'usdtbsc', payment_status: 'waiting' })
    await toMethodStep()
    fireEvent.click(await screen.findByText('USDT (BSC / BEP20)'))
    await waitFor(() => expect(service.createPayment).toHaveBeenCalledTimes(1))
    expect(service.createPayment.mock.calls[0][1].pay_currency).toBe('usdtbsc')
  })
})

describe('Resume payment dialog', () => {
  const answer = (body: Record<string, unknown>) =>
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => body }))

  it('sends a SoncoPay payment back to its secure page and shows its state', async () => {
    answer({ deposit_id: 41, status: 'pending', payment_status: 'confirming', payment_state: 'awaiting_confirmation',
      is_confirmed: false, provider: 'soncopay', checkout_url: CHECKOUT, price_amount: 10, price_currency: 'usd',
      order_id: 'mh5-idem-synthetic', pay_address: null })
    render(<ResumePaymentDialog open onOpenChange={() => {}} depositId={41} amount={10} productCode="kyc" />)
    expect(await screen.findByTestId('resume-soncopay-link')).toHaveAttribute('href', CHECKOUT)
    expect(screen.getByText(/Payment detected/)).toBeInTheDocument()
    expect(screen.queryByText(/Receiving Address/)).toBeNull()
  })

  it('still shows the address of a NOWPayments payment', async () => {
    answer({ deposit_id: 42, status: 'pending', payment_status: 'waiting', is_confirmed: false, provider: 'nowpayments',
      pay_address: '0xsyntheticaddress', pay_amount: '10.0', pay_currency: 'usdtbsc', price_amount: 10,
      price_currency: 'usd', order_id: 'mh5-np' })
    render(<ResumePaymentDialog open onOpenChange={() => {}} depositId={42} amount={10} productCode="kyc" />)
    expect(await screen.findByText('0xsyntheticaddress')).toBeInTheDocument()
    expect(screen.queryByTestId('resume-soncopay')).toBeNull()
    // Resuming an existing payment never depends on the checkout switches.
    const urls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0]))
    expect(urls.some((u) => u.includes('/checkout-gateway'))).toBe(false)
    expect(service.getCheckoutGateway).not.toHaveBeenCalled()
  })
})
