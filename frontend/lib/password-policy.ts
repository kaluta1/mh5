/**
 * The password rules shown and pre-checked in the browser.
 *
 * The backend is the authority (backend/app/core/security_validators.py,
 * validate_password_strength) and always has the last word. This file is the
 * ONE place the frontend states those rules, so the registration, reset and
 * change-password screens cannot drift apart or advertise a different minimum.
 * password-policy.test.ts fails if this file and the backend disagree.
 */
export const PASSWORD_MIN_LENGTH = 12

/** Same character class as the backend's "special character" rule. */
export const PASSWORD_SPECIAL_CHARACTER = /[!@#$%^&*(),.?":{}|<>_\-+=[\]\\;/]/

export interface PasswordChecks {
  hasMinLength: boolean
  hasUpperCase: boolean
  hasLowerCase: boolean
  hasNumber: boolean
  hasSpecialChar: boolean
}

export function checkPassword(value: string): PasswordChecks {
  const password = value || ''
  return {
    hasMinLength: password.length >= PASSWORD_MIN_LENGTH,
    hasUpperCase: /[A-Z]/.test(password),
    hasLowerCase: /[a-z]/.test(password),
    hasNumber: /\d/.test(password),
    hasSpecialChar: PASSWORD_SPECIAL_CHARACTER.test(password),
  }
}

export function isPasswordAcceptable(value: string): boolean {
  const checks = checkPassword(value)
  return (
    checks.hasMinLength && checks.hasUpperCase && checks.hasLowerCase && checks.hasNumber && checks.hasSpecialChar
  )
}
