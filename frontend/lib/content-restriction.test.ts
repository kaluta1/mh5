import { describe, expect, it } from 'vitest'
import { getContentRestriction } from './content-restriction'

const err = (status: number, detail: unknown) => ({ response: { status, data: { detail } } })

describe('getContentRestriction', () => {
  it('reads the backend CONTENT_RESTRICTED answer', () => {
    expect(
      getContentRestriction(err(403, { code: 'CONTENT_RESTRICTED', reason: 'AGE_REQUIRED', message: 'Add your DOB' })),
    ).toEqual({ reason: 'AGE_REQUIRED', message: 'Add your DOB' })
  })

  it('falls back to a safe message and reason', () => {
    expect(getContentRestriction(err(403, { code: 'CONTENT_RESTRICTED', reason: 'weird' }))).toEqual({
      reason: 'AGE_RESTRICTED',
      message: "This content isn't available for your account.",
    })
  })

  it('ignores every other error (hidden entries are a plain 404)', () => {
    expect(getContentRestriction(err(404, 'Submission not found'))).toBeNull()
    expect(getContentRestriction(err(403, 'Forbidden'))).toBeNull()
    expect(getContentRestriction(err(403, { code: 'OTHER' }))).toBeNull()
    expect(getContentRestriction(new Error('network'))).toBeNull()
    expect(getContentRestriction(null)).toBeNull()
  })
})
