import { describe, expect, it } from 'vitest'
import en from './translations/en.json'
import { EMAIL_NOT_VERIFIED_CODE, isEmailNotVerifiedError, resolveAuthLoginErrorMessage } from './auth-login-error-message'

const t = (key: string): string =>
  (key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string) || ''

const failure = (status: number, data: unknown) => ({ response: { status, data }, message: 'Request failed' })

describe('login error messages', () => {
  it('explains that the email must be confirmed (only sent for correct credentials)', () => {
    const err = failure(403, { detail: 'server text', code: EMAIL_NOT_VERIFIED_CODE, message: 'server text' })
    expect(isEmailNotVerifiedError(err)).toBe(true)
    expect(resolveAuthLoginErrorMessage(err, t)).toBe(en.auth.login.errors.email_not_verified)
    expect(resolveAuthLoginErrorMessage(err, () => undefined)).toMatch(/confirm your email address/i)
  })

  it('does not mistake any other failure for it', () => {
    const wrongPassword = failure(401, { detail: 'Email/Username or password incorrect.' })
    const deactivated = failure(403, { detail: 'Your account has been deactivated. Please contact support.' })
    const sameCodeWrongStatus = failure(401, { code: EMAIL_NOT_VERIFIED_CODE })
    for (const err of [wrongPassword, deactivated, sameCodeWrongStatus, failure(403, 'EMAIL_NOT_VERIFIED'), {}, null]) {
      expect(isEmailNotVerifiedError(err)).toBe(false)
    }
    expect(resolveAuthLoginErrorMessage(wrongPassword, t)).toBe(en.auth.login.errors.invalid_credentials)
    expect(resolveAuthLoginErrorMessage(wrongPassword, t)).not.toMatch(/confirm|verif/i)
    expect(resolveAuthLoginErrorMessage(deactivated, t)).toMatch(/deactivated/)
  })
})
