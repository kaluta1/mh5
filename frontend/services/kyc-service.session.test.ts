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
