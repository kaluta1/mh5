/**
 * Payment Service — member checkout (NOWPayments or SoncoPay; the server decides
 * the gateway of a new payment and every payment keeps its own).
 */
import { API_URL, getEffectiveApiUrl } from '@/lib/config'
import { apiErrorText } from '@/lib/financial-eligibility'
import { CheckoutUnavailableError, parseCheckoutGateway, parseSoncoPayMethods, type CheckoutAvailability, type CheckoutGateway, type PaymentState, type SoncoPayMethod } from '@/lib/payment-gateway'

export interface PaymentRecipient {
  username_or_email: string
  product_code: string
  amount: number
}

export interface PaymentRequest {
  amount: number
  currency: string
  product_code: string
  pay_currency?: string
  recipients?: PaymentRecipient[]
  /** SoncoPay only: how the member pays (the server refuses a method SoncoPay does not offer now). */
  payment_method?: SoncoPayMethod
}

/** What the server returns to confirm a recipient: public names only. */
export interface VerifiedUser {
  username: string
  display_name: string
}

export interface PaymentResponse {
  deposit_id: number
  order_id: string
  payment_id: string
  payment_status: string
  pay_address: string
  pay_amount: string
  pay_currency: string
  price_amount: number
  price_currency: string
  invoice_url?: string | null
  status: string
  /** nowpayments: show pay_address/pay_amount. soncopay: the member continues on checkout_url. */
  provider?: CheckoutGateway
  checkout_url?: string | null
  payment_method?: SoncoPayMethod | null
}

export interface PaymentStatusResponse {
  deposit_id: number
  status: string
  payment_status: string
  is_confirmed: boolean
  order_id?: string
  payment_id?: string
  pay_address?: string
  pay_amount?: string
  pay_currency?: string
  price_amount: number
  price_currency: string
  tx_hash?: string
  invoice_url?: string | null
  provider?: CheckoutGateway
  checkout_url?: string | null
  /** SoncoPay only. */
  payment_state?: PaymentState
  expires_at?: string | null
}

class PaymentService {
  private getBaseUrl(): string {
    const origin = typeof window === 'undefined' ? API_URL : getEffectiveApiUrl()
    return `${origin.replace(/\/+$/, '')}/api/v1/payments`
  }

  private getHeaders(token: string): HeadersInit {
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    }
  }

  async verifyUser(token: string, usernameOrEmail: string): Promise<VerifiedUser> {
    const params = new URLSearchParams({ username_or_email: usernameOrEmail })
    const response = await fetch(`${this.getBaseUrl()}/verify-user?${params}`, {
      headers: this.getHeaders(token),
    })

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('User not found')
      }
      throw new Error('Failed to verify user')
    }

    return response.json()
  }

  /**
   * The gateway a NEW payment uses now. Fails closed: 'unavailable' unless the server explicitly confirms a
   * gateway (HTTP error, network failure or an unreadable answer never fall back to NOWPayments).
   */
  async getCheckoutGateway(token: string): Promise<CheckoutAvailability> {
    try {
      const response = await fetch(`${this.getBaseUrl()}/checkout-gateway`, { headers: this.getHeaders(token) })
      if (!response.ok) return 'unavailable'
      return parseCheckoutGateway(await response.json())
    } catch {
      return 'unavailable'
    }
  }

  /** The SoncoPay methods a NEW payment may use (USDT on BSC only when the server cannot be read). */
  async getSoncoPayMethods(token: string): Promise<SoncoPayMethod[]> {
    try {
      const response = await fetch(`${this.getBaseUrl()}/checkout-gateway`, { headers: this.getHeaders(token) })
      if (!response.ok) return ['usdt_bsc']
      return parseSoncoPayMethods(await response.json())
    } catch {
      return ['usdt_bsc']
    }
  }

  async getAvailableCurrencies(token: string): Promise<string[]> {
    const response = await fetch(`${this.getBaseUrl()}/currencies`, {
      headers: this.getHeaders(token),
    })

    if (!response.ok) {
      throw new Error('Failed to get currencies')
    }

    const data = await response.json()
    return data.currencies || []
  }

  async createPayment(
    token: string,
    request: PaymentRequest,
    idempotencyKey?: string
  ): Promise<PaymentResponse> {
    const response = await fetch(`${this.getBaseUrl()}/create`, {
      method: 'POST',
      headers: {
        ...this.getHeaders(token),
        ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      if (response.status === 503 && error?.detail?.code === 'CHECKOUT_UNAVAILABLE') {
        throw new CheckoutUnavailableError()
      }
      throw new Error(apiErrorText(error.detail, 'Failed to create payment'))
    }

    return response.json()
  }

  async syncPayment(token: string, depositId: number): Promise<PaymentStatusResponse> {
    const response = await fetch(`${this.getBaseUrl()}/sync/${depositId}`, {
      method: 'POST',
      headers: this.getHeaders(token),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Failed to sync payment')
    }

    return response.json()
  }

  async checkDepositStatus(
    token: string,
    depositId: number
  ): Promise<{
    deposit_id: number
    status: string
    is_confirmed: boolean
    order_id?: string
    payment_id?: string
  }> {
    const response = await fetch(`${this.getBaseUrl()}/check/${depositId}`, {
      method: 'POST',
      headers: this.getHeaders(token),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Failed to check deposit status')
    }

    return response.json()
  }

  async getPaymentStatus(token: string, depositId: number): Promise<PaymentStatusResponse> {
    const response = await fetch(`${this.getBaseUrl()}/check-status/${depositId}`, {
      headers: this.getHeaders(token),
    })

    if (!response.ok) {
      throw new Error('Failed to get payment status')
    }

    return response.json()
  }
}

export const paymentService = new PaymentService()
