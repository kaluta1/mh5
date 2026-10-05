import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const TOKEN = 'pK3v9sQ2xL7mN1bV5cX8zA4dF6gH0jRtYuIoPwEqSdF'
const lookup = (key: string): string =>
  (key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string) || ''

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup }) }))
const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))
const addToast = vi.fn()
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ addToast }) }))
const confirmPasswordReset = vi.fn()
vi.mock('@/lib/api', () => ({ authService: { confirmPasswordReset: (...a: unknown[]) => confirmPasswordReset(...a) } }))

import ResetPasswordPage from './page'

const copy = en.auth.reset_password
const open = (url: string) => window.history.replaceState(null, '', url)

function fill(password: string, confirmation = password) {
  const [first, second] = Array.from(document.querySelectorAll('input')) as HTMLInputElement[]
  fireEvent.change(first, { target: { value: password } })
  fireEvent.change(second, { target: { value: confirmation } })
  fireEvent.submit(document.querySelector('form') as HTMLFormElement)
}

beforeEach(() => {
  confirmPasswordReset.mockReset()
  addToast.mockReset()
  push.mockReset()
})

describe('reset-password page', () => {
  it('an old ?token= link lands on a clear page that offers a new link, and is never sent', async () => {
    open('/reset-password?token=eyJhbGciOiJIUzI1NiJ9.legacy.signature')
    render(<ResetPasswordPage />)
    await waitFor(() => expect(screen.getByText(copy.no_token_title)).toBeInTheDocument())
    expect(screen.getByText(copy.old_link_message)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: copy.request_new_link })).toHaveAttribute('href', '/forgot-password')
    expect(window.location.search).toBe('')
    expect(document.querySelector('form')).toBeNull()                       // no form to submit a dead token with
    expect(confirmPasswordReset).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()                                     // no redirect loop
  })

  it('without any link it explains and offers a new one', async () => {
    open('/reset-password')
    render(<ResetPasswordPage />)
    await waitFor(() => expect(screen.getByText(copy.no_token_message)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: copy.request_new_link })).toHaveAttribute('href', '/forgot-password')
  })

  it('takes the credential from the fragment, scrubs it, and sends it in the request body', async () => {
    confirmPasswordReset.mockResolvedValue(undefined)
    open(`/reset-password#token=${TOKEN}`)
    render(<ResetPasswordPage />)
    await waitFor(() => expect(document.querySelector('form')).not.toBeNull())
    expect(window.location.hash).toBe('')
    fill('Tw3lve*Chars!')
    await waitFor(() => expect(confirmPasswordReset).toHaveBeenCalledTimes(1))
    expect(confirmPasswordReset).toHaveBeenCalledWith({ token: TOKEN, new_password: 'Tw3lve*Chars!' })
  })

  it('applies the 12-character policy before calling the server', async () => {
    open(`/reset-password#token=${TOKEN}`)
    render(<ResetPasswordPage />)
    await waitFor(() => expect(document.querySelector('form')).not.toBeNull())
    fill('Sh0rt*Pw')                                                        // passed the old 6-character check
    await waitFor(() => expect(screen.getByText(copy.password_min_length)).toBeInTheDocument())
    expect(copy.password_min_length).toContain('12')
    fill('twelvecharsnoupper1')
    await waitFor(() => expect(screen.getByText(en.auth.register.errors.password_requirements)).toBeInTheDocument())
    expect(confirmPasswordReset).not.toHaveBeenCalled()
  })

  it('shows a readable message when the link is refused', async () => {
    confirmPasswordReset.mockRejectedValue(
      Object.assign(new Error('Token invalide ou expiré'), { response: { status: 400, data: { detail: 'Token invalide ou expiré' } } }),
    )
    open(`/reset-password#token=${TOKEN}`)
    render(<ResetPasswordPage />)
    await waitFor(() => expect(document.querySelector('form')).not.toBeNull())
    fill('Tw3lve*Chars!')
    await waitFor(() => expect(addToast).toHaveBeenCalledWith(copy.invalid_token, 'error'))
  })
})
