import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'
import fr from '@/lib/translations/fr.json'
import es from '@/lib/translations/es.json'
import de from '@/lib/translations/de.json'
import { lookupTranslation } from '@/lib/translations-loader'

const TOKEN = 'pK3v9sQ2xL7mN1bV5cX8zA4dF6gH0jRtYuIoPwEqSdF'
const BUNDLES: Record<string, Record<string, any>> = { en, fr, es, de, sw: {} }
const state = { lang: 'en' }

// The app's own lookup: the active language first, English otherwise.
vi.mock('@/contexts/language-context', () => ({
  useLanguage: () => ({
    language: state.lang,
    t: (key: string) => lookupTranslation(BUNDLES[state.lang], key) || lookupTranslation(en, key),
  }),
}))

const verifyEmail = vi.fn()
const resendVerification = vi.fn()
vi.mock('@/lib/api', () => ({
  authService: {
    verifyEmail: (...args: unknown[]) => verifyEmail(...args),
    resendVerification: (...args: unknown[]) => resendVerification(...args),
  },
}))

import VerifyEmailPage from './page'

const open = (url: string) => window.history.replaceState(null, '', url)
const v = (lang: string, key: string): string => (BUNDLES[lang] as any).auth.verify_email[key]

beforeEach(() => {
  state.lang = 'en'
  verifyEmail.mockReset()
  resendVerification.mockReset()
})

describe('verify-email page', () => {
  it('exchanges the fragment credential once, over POST, and scrubs the address bar', async () => {
    verifyEmail.mockResolvedValue({ message: 'ok', code: 'EMAIL_VERIFIED' })
    open(`/verify-email#token=${TOKEN}`)
    render(<VerifyEmailPage />)
    expect(screen.getByText(v('en', 'verifying_title'))).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(v('en', 'success_title'))).toBeInTheDocument())
    expect(verifyEmail).toHaveBeenCalledTimes(1)
    expect(verifyEmail).toHaveBeenCalledWith(TOKEN)
    expect(window.location.hash).toBe('')
    expect(window.location.href).not.toContain(TOKEN)
    expect(screen.getByRole('link', { name: v('en', 'continue_to_sign_in') })).toHaveAttribute('href', '/login')
  })

  it('shows one message for every refused link and offers a new one', async () => {
    verifyEmail.mockRejectedValue(Object.assign(new Error('server wording that must not be shown'), { response: { status: 400 } }))
    resendVerification.mockResolvedValue({ message: 'uniform' })
    open(`/verify-email#token=${TOKEN}`)
    render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v('en', 'error_title'))).toBeInTheDocument())
    expect(screen.getByText(v('en', 'error_invalid_link'))).toBeInTheDocument()
    expect(screen.queryByText(/server wording/)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(v('en', 'resend_label')), { target: { value: ' member@example.com ' } })
    fireEvent.click(screen.getByRole('button', { name: v('en', 'resend_button') }))
    await waitFor(() => expect(screen.getByText(v('en', 'resend_sent'))).toBeInTheDocument())
    expect(resendVerification).toHaveBeenCalledWith('member@example.com')
    expect(screen.queryByText('uniform')).not.toBeInTheDocument()      // the page's own (localized) wording
  })

  it('never sends an old ?token= link to the server: safe page, scrubbed URL, resend offered', async () => {
    open('/verify-email?token=eyJhbGciOiJIUzI1NiJ9.legacy.signature&lang=fr')
    render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v('en', 'error_old_link'))).toBeInTheDocument())
    expect(verifyEmail).not.toHaveBeenCalled()
    expect(window.location.search).toBe('?lang=fr')
    expect(window.location.href).not.toContain('eyJ')
    expect(screen.getByRole('button', { name: v('en', 'resend_button') })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: v('en', 'back_to_sign_in') })).toHaveAttribute('href', '/login')
  })

  it('treats a malformed fragment as an unusable link without calling the server', async () => {
    open('/verify-email#token=short')
    render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v('en', 'error_invalid_link'))).toBeInTheDocument())
    expect(verifyEmail).not.toHaveBeenCalled()
  })

  it('opened without a link, it is simply the place to ask for one', async () => {
    open('/verify-email')
    render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v('en', 'request_title'))).toBeInTheDocument())
    expect(screen.queryByText(v('en', 'error_title'))).not.toBeInTheDocument()
    expect(verifyEmail).not.toHaveBeenCalled()
  })

  it('reports a failed or rate-limited resend without leaking details', async () => {
    open('/verify-email')
    resendVerification.mockRejectedValueOnce(Object.assign(new Error('raw'), { response: { status: 429 } }))
    render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v('en', 'request_title'))).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(v('en', 'resend_label')), { target: { value: 'member@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: v('en', 'resend_button') }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(v('en', 'resend_rate_limited')))
    resendVerification.mockRejectedValueOnce(new Error('raw network failure'))
    fireEvent.click(screen.getByRole('button', { name: v('en', 'resend_button') }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(v('en', 'resend_failed')))
    expect(screen.queryByText(/raw/)).not.toBeInTheDocument()
  })
})

describe('verify-email page localization', () => {
  it.each(['fr', 'en', 'es', 'de'])('renders every state in %s', async (lang) => {
    state.lang = lang
    verifyEmail.mockResolvedValue({})
    open(`/verify-email#token=${TOKEN}`)
    const first = render(<VerifyEmailPage />)
    expect(screen.getByText(v(lang, 'verifying_title'))).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(v(lang, 'success_title'))).toBeInTheDocument())
    expect(screen.getByText(v(lang, 'success_message'))).toBeInTheDocument()
    first.unmount()

    verifyEmail.mockRejectedValue(new Error('x'))
    open(`/verify-email#token=${TOKEN}`)
    const second = render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v(lang, 'error_invalid_link'))).toBeInTheDocument())
    expect(screen.getByRole('button', { name: v(lang, 'resend_button') })).toBeInTheDocument()
    second.unmount()

    open('/verify-email?token=old')
    const third = render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v(lang, 'error_old_link'))).toBeInTheDocument())
    third.unmount()

    open('/verify-email')
    render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v(lang, 'request_title'))).toBeInTheDocument())
    expect(screen.getByText(v(lang, 'request_message'))).toBeInTheDocument()
  })

  it('falls back to English for a language without these strings', async () => {
    state.lang = 'sw'
    open('/verify-email')
    render(<VerifyEmailPage />)
    await waitFor(() => expect(screen.getByText(v('en', 'request_title'))).toBeInTheDocument())
    expect(screen.getByRole('button', { name: v('en', 'resend_button') })).toBeInTheDocument()
  })

  it('has the same keys, all translated, in fr / en / es / de', () => {
    const keys = Object.keys(en.auth.verify_email).sort()
    for (const lang of ['fr', 'es', 'de']) {
      const section = (BUNDLES[lang] as any).auth.verify_email
      const required = keys.filter((k) => !['success_toast', 'error_invalid', 'error_user', 'error_generic'].includes(k))
      for (const key of required) {
        expect(typeof section[key], `${lang}.${key}`).toBe('string')
        expect(section[key].trim().length, `${lang}.${key}`).toBeGreaterThan(0)
        if (!['resend_placeholder'].includes(key)) {
          expect(section[key], `${lang}.${key} is still English`).not.toBe((en.auth.verify_email as any)[key])
        }
      }
      for (const key of ['email_not_verified', 'email_not_verified_action']) {
        expect((BUNDLES[lang] as any).auth.login.errors[key]).toBeTruthy()
      }
    }
    // no string distinguishes "expired" from "already used": the server does not either
    for (const lang of ['en', 'fr', 'es', 'de']) {
      const section = (BUNDLES[lang] as any).auth.verify_email
      expect(section.error_expired).toBeUndefined()
      expect(section.error_used).toBeUndefined()
    }
  })
})
