/**
 * Payment Service - Smart Contract payments integration (BSC)
 */
import { API_URL } from '@/lib/config'

export interface PaymentRecipient {
  username_or_email: string
  product_code: string
  amount: number
}

export interface PaymentRequest {
  amount: number
  currency: string
  product_code: string // kyc, efm_membership, etc.
  recipients?: PaymentRecipient[]
}

export interface VerifiedUser {
  id: number
  username: string
  email: string
  display_name: string
}

export interface PaymentResponse {
  deposit_id: number  // Local deposit ID for status checks
  order_id: string  // Order ID for smart contract payment
  contract_address: string  // Payment contract address
  token_address: string  // USDT token address
  amount_wei: string  // Amount in wei (as string for precision)
  chain_id: number  // BSC chain ID
  price_amount: number  // Amount in USD
  price_currency: string
  status: string
}

export interface VerifyPaymentRequest {
  order_id: string
  tx_hash: string
}

export interface VerifyPaymentResponse {
  valid: boolean
  deposit_id: number
  status: string
  payer?: string
  tx_hash?: string
  message?: string
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
   * Create a payment order for smart contract payment
   * Returns order_id and payment details for frontend wallet integration
   */
  async createPayment(
    token: string,
    request: PaymentRequest
  ): Promise<PaymentResponse> {
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
   * Verify a payment transaction on the blockchain
   */
  async verifyPayment(
    token: string,
    request: VerifyPaymentRequest
  ): Promise<VerifyPaymentResponse> {
    const response = await fetch(`${this.baseUrl}/verify`, {
      method: 'POST',
      headers: this.getHeaders(token),
      body: JSON.stringify(request)
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Failed to verify payment')
    }

    return response.json()
  }

  /**
   * Check payment status by deposit ID
   */
  async checkDepositStatus(token: string, depositId: number): Promise<{
    deposit_id: number
    status: string
    is_confirmed: boolean
    order_id?: string
    tx_hash?: string
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
   * Get payment status and details for a deposit
   */
  async getPaymentStatus(token: string, depositId: number): Promise<{
    deposit_id: number
    status: string
    is_confirmed: boolean
    order_id?: string
    tx_hash?: string
    amount: number
    currency: string
    contract_address: string
    token_address: string
    chain_id: number
  }> {
    const response = await fetch(`${this.baseUrl}/check-status/${depositId}`, {
      headers: this.getHeaders(token)
    })

    if (!response.ok) {
      throw new Error('Failed to get payment status')
    }

    return response.json()
  }
}

export const paymentService = new PaymentService()
