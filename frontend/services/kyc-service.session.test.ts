import { afterEach, describe, expect, it, vi } from 'vitest'

import { kycService } from './kyc-service'

// Synthetic values only.
const answer = (body: Record<string, unknown>) =>
  vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body })

afterEach(() => vi.unstubAllGlobals())

describe('kycService.getKYCStatus: attempts and provider sessions', () => {
  it('passes on the session state the KYC page needs', async () => {
    vi.stubGlobal('fetch', answer({
      status: 'in_progress', can_continue: true, can_restart: false, attempts_count: 3, max_attempts: 3,
      attempts_remaining: 0, max_attempts_reached: true, session_expired: true, sessions_remaining: 0,
      session_limit_reached: true, needs_payment: false,
    }))
    const status = await kycService.getKYCStatus('synthetic-token') as unknown as Record<string, unknown>
    expect(status).toMatchObject({
      attempts_count: 3, max_attempts: 3, attempts_remaining: 0, max_attempts_reached: true,
      session_expired: true, sessions_remaining: 0, session_limit_reached: true, needs_payment: false,
    })
  })

  it('an older server without the fields reads as no limit reached', async () => {
    vi.stubGlobal('fetch', answer({ status: 'in_progress', can_continue: true }))
    const status = await kycService.getKYCStatus('synthetic-token') as unknown as Record<string, unknown>
    expect(status).toMatchObject({ session_expired: false, sessions_remaining: null, session_limit_reached: false })
  })
})

describe('kycService.initiateVerification: provider unavailable', () => {
  it('shows the fixed sentence of a structured 503 (KYC_PROVIDER_UNAVAILABLE)', async () => {
    const message = 'Identity verification is temporarily unavailable. Please try again later.'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 503,
      json: async () => ({ detail: { code: 'KYC_PROVIDER_UNAVAILABLE', message }, code: 'HTTP_503', message }),
    }))
    await expect(kycService.initiateVerification('synthetic-token', 'en', 'Synthetic street 1'))
      .rejects.toThrow(new Error(message))
  })
})

describe('kycService: the provider proof-of-address step', () => {
  it('passes on where the address step stands', async () => {
    const step = { provider: 'kaluta', session_open: false, verification_url: null, sessions_left: 0, address_not_checked: true }
    vi.stubGlobal('fetch', answer({ status: 'pending_proof_of_address', needs_proof_of_address: true, address_step: step }))
    const status = await kycService.getKYCStatus('synthetic-token') as unknown as Record<string, unknown>
    expect(status.address_step).toEqual(step)
  })

  it('asks the server for a provider address session, and nothing else', async () => {
    const fetchMock = answer({ verification_url: 'https://kalutakyc.com/verify/sess-1', verification_id: 5, reused: false,
      status: 'address_in_progress' })
    vi.stubGlobal('fetch', fetchMock)
    const result = await kycService.initiateAddressVerification('synthetic-token')
    expect(result.verification_url).toBe('https://kalutakyc.com/verify/sess-1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/kyc\/address\/initiate$/)
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()                                    // no document or typed text is sent
  })

  it('shows the server sentence when the address check is not available', async () => {
    const message = 'The provider has not checked your address yet.'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 409, json: async () => ({ detail: { code: 'KYC_ADDRESS_CHECK_NOT_AVAILABLE', message } }),
    }))
    await expect(kycService.initiateAddressVerification('synthetic-token')).rejects.toThrow(new Error(message))
  })
})
