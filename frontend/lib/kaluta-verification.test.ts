import { describe, expect, it, vi } from 'vitest'
import { isKalutaVerificationUrl, isUndecided, waitForDecision } from './kaluta-verification'

describe('the verification URL that is opened', () => {
  it("is only an https page of the provider's own host", () => {
    expect(isKalutaVerificationUrl('https://kalutakyc.com/verify/abc123')).toBe(true)
    for (const bad of [
      'http://kalutakyc.com/verify/abc123',
      'https://kalutakyc.com.evil.example/verify/abc123',
      'https://evil.example/kalutakyc.com/verify/abc123',
      'https://user:pass@kalutakyc.com/verify/abc123',
      'https://sub.kalutakyc.com/verify/abc123',
      'https://kalutakyc.com:8443/verify/abc123',
      'javascript:alert(1)',
      '//kalutakyc.com/verify/abc123',
      'data:text/html,<script>alert(1)</script>',
      '',
      null,
      undefined,
    ]) {
      expect(isKalutaVerificationUrl(bad as string)).toBe(false)
    }
  })
})

describe('reading the result after the widget closes', () => {
  const sleep = vi.fn(() => Promise.resolve())

  it('asks the backend again until the decision has arrived', async () => {
    const answers = [{ status: 'in_progress' }, { status: 'in_progress' }, { status: 'pending_proof_of_address' }]
    const read = vi.fn(() => Promise.resolve(answers.shift()!))
    const result = await waitForDecision(read, { sleep, delayMs: 1 })
    expect(result.status).toBe('pending_proof_of_address')
    expect(read).toHaveBeenCalledTimes(3)
  })

  it('reads once when the decision is already there', async () => {
    for (const status of ['approved', 'rejected', 'expired', 'pending_proof_of_address', 'requires_review', null]) {
      const read = vi.fn(() => Promise.resolve({ status }))
      expect((await waitForDecision(read, { sleep })).status).toBe(status)
      expect(read).toHaveBeenCalledTimes(1)
    }
  })

  it('stops after a few tries and leaves the member on an honest "in progress"', async () => {
    const read = vi.fn(() => Promise.resolve({ status: 'in_progress' }))
    const result = await waitForDecision(read, { sleep, attempts: 4 })
    expect(result.status).toBe('in_progress')
    expect(read).toHaveBeenCalledTimes(4)
  })

  it('knows which statuses are still open', () => {
    expect(['pending', 'in_progress'].every(isUndecided)).toBe(true)
    expect(['approved', 'rejected', 'expired', 'pending_proof_of_address', '', null, undefined].some(isUndecided)).toBe(false)
  })
})
