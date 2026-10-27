import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const lookup = (key: string): string =>
  (key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as
    | string
    | undefined) ?? key

const push = vi.fn()
const login = vi.fn()
vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup, language: 'en' }) }))
vi.mock('@/hooks/use-auth', () => ({ useAuth: () => ({ login, isAuthenticated: false }) }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }), usePathname: () => '/' }))

import { LoginModal } from './login-modal'

const answer = (status: number, data: unknown) => Object.assign(new Error('rejected'), { response: { status, data } })

function signIn(identifier = 'member@example.com', password = 'Secret-pass-1') {
  const onOpenChange = vi.fn()
  render(<LoginModal open onOpenChange={onOpenChange} />)
  fireEvent.change(screen.getByLabelText(lookup('auth.email')), { target: { value: identifier } })
  fireEvent.change(document.getElementById('password') as HTMLInputElement, { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: lookup('auth.login.submit') }))
  return onOpenChange
}

beforeEach(() => {
  push.mockReset()
  login.mockReset()
})

describe('Login modal', () => {
  it('offers a new confirmation link when the email address is not confirmed yet', async () => {
    login.mockRejectedValue(answer(403, { code: 'EMAIL_NOT_VERIFIED', detail: 'Please confirm your email address.' }))
    const onOpenChange = signIn()
    const notice = await screen.findByTestId('login-email-not-verified')
    expect(notice.textContent).toContain(en.auth.login.errors.email_not_verified)
    fireEvent.click(screen.getByRole('button', { name: en.auth.login.errors.email_not_verified_action }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(push).toHaveBeenCalledWith('/verify-email')
  })

  it('a wrong password or unknown account gets the ordinary answer, never the confirmation notice', async () => {
    login.mockRejectedValue(answer(401, { detail: 'Email/Username or password incorrect.' }))
    signIn('someone', 'wrong-password')
    await waitFor(() => expect(screen.getByText(en.auth.login.errors.invalid_credentials)).toBeTruthy())
    expect(screen.queryByTestId('login-email-not-verified')).toBeNull()
  })

  it('the notice clears when the member signs in again', async () => {
    login.mockRejectedValueOnce(answer(403, { code: 'EMAIL_NOT_VERIFIED' }))
    signIn()
    await screen.findByTestId('login-email-not-verified')
    login.mockRejectedValueOnce(answer(401, { detail: 'Email/Username or password incorrect.' }))
    fireEvent.click(screen.getByRole('button', { name: lookup('auth.login.submit') }))
    await waitFor(() => expect(screen.queryByTestId('login-email-not-verified')).toBeNull())
  })
})
