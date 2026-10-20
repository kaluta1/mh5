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
vi.mock('@/services/kyc-service', () => ({ kycService: { getKycFee: vi.fn().mockResolvedValue(null) } }))
vi.mock('@/services/payment-service', () => ({ paymentService: service }))

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
  fireEvent.click(await screen.findByRole('button', { name: /Continuer/ }))
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

  it('keeps the NOWPayments currencies when NOWPayments is the gateway', async () => {
    service.getCheckoutGateway.mockResolvedValue('nowpayments')
    await toMethodStep()
    expect(await screen.findByText('USDT (BSC / BEP20)')).toBeInTheDocument()
    expect(screen.queryByTestId('pay-with-soncopay')).toBeNull()
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
  })
})
