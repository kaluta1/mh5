import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import en from './translations/en.json'
import fr from './translations/fr.json'
import es from './translations/es.json'
import de from './translations/de.json'
import { PASSWORD_MIN_LENGTH, PASSWORD_SPECIAL_CHARACTER, checkPassword, isPasswordAcceptable } from './password-policy'

const root = resolve(__dirname, '..')
const read = (path: string) => readFileSync(resolve(root, path), 'utf-8')

describe('password policy', () => {
  it('agrees with the backend, which is the authority', () => {
    const backend = read('../backend/app/core/security_validators.py')
    const minimum = backend.match(/if len\(value\) < (\d+):/)
    expect(minimum).not.toBeNull()
    expect(Number(minimum![1])).toBe(PASSWORD_MIN_LENGTH)
    expect(PASSWORD_MIN_LENGTH).toBe(12)
    // the same special-character class as the backend's rule
    const special = backend.match(/re\.search\(r'\[(.+)\]', value\)/)
    expect(special).not.toBeNull()
    const backendClass = new RegExp(`[${special![1]}]`)
    for (const ch of '!@#$%^&*(),.?":{}|<>_-+=[]\\;/') {
      expect(backendClass.test(ch)).toBe(true)
      expect(PASSWORD_SPECIAL_CHARACTER.test(ch)).toBe(true)
    }
    for (const ch of 'aZ0 ~`\'') {
      expect(PASSWORD_SPECIAL_CHARACTER.test(ch)).toBe(backendClass.test(ch))
    }
  })

  it('accepts exactly what the rules describe', () => {
    expect(isPasswordAcceptable('Tw3lve*Chars')).toBe(true)
    expect(isPasswordAcceptable('Elev3n*Char')).toBe(false) // 11 characters
    expect(isPasswordAcceptable('Sh0rt*Pw')).toBe(false) // the old 8-character hint
    expect(isPasswordAcceptable('abc123')).toBe(false) // the old 6-character hint
    expect(isPasswordAcceptable('nouppercase1*aa')).toBe(false)
    expect(isPasswordAcceptable('NOLOWERCASE1*AA')).toBe(false)
    expect(isPasswordAcceptable('NoDigitsHere*aa')).toBe(false)
    expect(isPasswordAcceptable('NoSpecial12345a')).toBe(false)
    expect(isPasswordAcceptable('Exclam4tion!ok')).toBe(true) // "!" was refused by the old hint (*_/@= only)
    expect(checkPassword('')).toEqual({
      hasMinLength: false, hasUpperCase: false, hasLowerCase: false, hasNumber: false, hasSpecialChar: false,
    })
  })

  it('is the only statement of the minimum in the auth screens', () => {
    const screens = ['app/register/page.tsx', 'app/reset-password/page.tsx', 'components/dashboard/settings-password-tab.tsx']
    for (const path of screens) {
      const source = read(path)
      expect(source, path).toContain("@/lib/password-policy")
      expect(source, path).not.toMatch(/length\s*(>=|<)\s*(6|8)\b/)
      expect(source, path).not.toMatch(/\b(6|8) (caractères|characters)/)
      expect(source, path).not.toContain('*_/@=')
    }
  })

  it('shows the same minimum in every supported language', () => {
    for (const [lang, bundle] of Object.entries({ en, fr, es, de })) {
      const auth = (bundle as any).auth
      for (const text of [
        auth.register.password_requirement_length,
        auth.register.errors.password_min_length,
        auth.reset_password.password_min_length,
      ]) {
        expect(text, lang).toContain(String(PASSWORD_MIN_LENGTH))
        expect(text, lang).not.toMatch(/\b(6|8)\b/)
      }
    }
    expect((en as any).auth.register.password_requirement_min_length).toContain('12')
    expect(JSON.stringify((en as any).auth)).not.toMatch(/At least 8 characters|Password Min Length/)
  })
})
