/**
 * Payment Service - Crypto payments integration
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://mh5-sbe4.onrender.com'

export interface PaymentRecipient {
  username_or_email: string
  product_code: string
  amount: number
}

export interface CryptoPaymentRequest {
  amount: number
  currency: string
  pay_currency: string // btc, eth, usdt, etc.
  product_code: string // kyc, efm_membership, etc.
  recipients?: PaymentRecipient[]
}

export interface VerifiedUser {
  id: number
  username: string
  email: string
  display_name: string
}

export interface CryptoPaymentResponse {
  deposit_id: number  // Local deposit ID for status checks
  payment_id: number  // External payment provider ID
  pay_address: string
  pay_amount: number
  pay_currency: string
  price_amount: number
  price_currency: string
  order_id: string
  status: string
}

export interface InvoiceRequest {
  amount: number
  currency: string
  product_code: string
}

export interface InvoiceResponse {
  invoice_id: string
  invoice_url: string
  order_id: string
}

export interface PaymentEstimate {
  estimated_amount: number
  currency_from: string
  currency_to: string
}

class PaymentService {
  private baseUrl: string

  constructor() {
    this.baseUrl = `${API_URL}/api/v1/payments`
  }

  private getHeaders(token: string): HeadersInit {
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    }
  }

  /**
   * Verify if a user exists by username or email
   */
  async verifyUser(token: string, usernameOrEmail: string): Promise<VerifiedUser> {
    const params = new URLSearchParams({ username_or_email: usernameOrEmail })
    const response = await fetch(`${this.baseUrl}/verify-user?${params}`, {
      headers: this.getHeaders(token)
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
   * Get available cryptocurrencies for payment
   */
  async getAvailableCurrencies(token: string): Promise<string[]> {
    const response = await fetch(`${this.baseUrl}/currencies`, {
      headers: this.getHeaders(token)
    })

    if (!response.ok) {
      throw new Error('Failed to get currencies')
    }

    const data = await response.json()
    return data.currencies || []
  }

  /**
   * Get payment estimate (crypto amount for fiat amount)
   */
  async getEstimate(
    token: string,
    amount: number,
    currencyFrom: string = 'usd',
    currencyTo: string = 'btc'
  ): Promise<PaymentEstimate> {
    const params = new URLSearchParams({
      amount: amount.toString(),
      currency_from: currencyFrom,
      currency_to: currencyTo
    })

    const response = await fetch(`${this.baseUrl}/estimate?${params}`, {
      headers: this.getHeaders(token)
    })

    if (!response.ok) {
      throw new Error('Failed to get estimate')
    }

    return response.json()
  }

  /**
   * Create a crypto payment
   * Returns payment address and amount to send
   */
  async createPayment(
    token: string,
    request: CryptoPaymentRequest
  ): Promise<CryptoPaymentResponse> {
    const response = await fetch(`${this.baseUrl}/create`, {
      method: 'POST',
      headers: this.getHeaders(token),
      body: JSON.stringify(request)
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Failed to create payment')
    }

    return response.json()
  }

  /**
   * Create a payment invoice (hosted page)
   * User is redirected to choose crypto and pay
   */
  async createInvoice(
    token: string,
    request: InvoiceRequest
  ): Promise<InvoiceResponse> {
    const response = await fetch(`${this.baseUrl}/invoice`, {
      method: 'POST',
      headers: this.getHeaders(token),
      body: JSON.stringify(request)
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Failed to create invoice')
    }

    return response.json()
  }

  /**
   * Get payment status
   */
  async getPaymentStatus(token: string, paymentId: number): Promise<any> {
    const response = await fetch(`${this.baseUrl}/status/${paymentId}`, {
      headers: this.getHeaders(token)
    })

    if (!response.ok) {
      throw new Error('Failed to get payment status')
    }

    return response.json()
  }

  /**
   * Check and refresh deposit status
   * Called when user clicks "I have paid" button
   */
  async checkDepositStatus(token: string, depositId: number): Promise<{
    deposit_id: number
    status: string
    payment_status?: string
    is_confirmed: boolean
    error?: string
  }> {
    const response = await fetch(`${this.baseUrl}/check/${depositId}`, {
      method: 'POST',
      headers: this.getHeaders(token)
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Failed to check deposit status')
    }

    return response.json()
  }

  /**
   * Get deposit info
   */
  async getDepositInfo(token: string, depositId: number): Promise<{
    deposit_id: number
    status: string
    is_confirmed: boolean
    amount: number
    currency: string
    created_at?: string
    validated_at?: string
  }> {
    const response = await fetch(`${this.baseUrl}/deposit/${depositId}`, {
      headers: this.getHeaders(token)
    })

    if (!response.ok) {
      throw new Error('Failed to get deposit info')
    }

    return response.json()
  }
}

export const paymentService = new PaymentService()
