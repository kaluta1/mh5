import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const lookup = (key: string): string =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string

const auth: { user: Record<string, unknown> | null } = { user: null }
vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup }) }))
vi.mock('@/hooks/use-auth', () => ({ useAuth: () => auth }))
const resendVerification = vi.fn()
vi.mock('@/lib/api', () => ({ authService: { resendVerification: (...a: unknown[]) => resendVerification(...a) } }))

import { EmailVerificationBanner } from './email-verification-banner'

const copy = en.auth.verify_email

beforeEach(() => {
  resendVerification.mockReset()
})

describe('EmailVerificationBanner', () => {
  it('shows "Verify your email" with a resend action to a signed-in unverified member', async () => {
    auth.user = { id: 7, email: 'legacy.member@example.com', email_verified: false, email_verification_required: false }
    resendVerification.mockResolvedValue({ message: 'uniform' })
    render(<EmailVerificationBanner />)
    expect(screen.getByText(copy.banner_title)).toBeInTheDocument()
    expect(screen.getByText(copy.banner_message)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: copy.banner_button }))
    await waitFor(() => expect(screen.getByText(copy.banner_sent)).toBeInTheDocument())
    expect(resendVerification).toHaveBeenCalledTimes(1)
    expect(resendVerification).toHaveBeenCalledWith('legacy.member@example.com')
    expect(screen.queryByRole('button', { name: copy.banner_button })).not.toBeInTheDocument()
  })

  it('renders nothing for a verified member, a guest, or a response without the field', () => {
    for (const user of [
      { id: 1, email: 'a@example.com', email_verified: true },
      { id: 2, email: 'b@example.com' },
      null,
    ]) {
      auth.user = user
      const { container, unmount } = render(<EmailVerificationBanner />)
      expect(container).toBeEmptyDOMElement()
      unmount()
    }
    expect(resendVerification).not.toHaveBeenCalled()
  })

  it('says so when the email could not be sent, and lets the member retry', async () => {
    auth.user = { id: 7, email: 'legacy.member@example.com', email_verified: false }
    resendVerification.mockRejectedValueOnce(new Error('raw failure'))
    render(<EmailVerificationBanner />)
    fireEvent.click(screen.getByRole('button', { name: copy.banner_button }))
    await waitFor(() => expect(screen.getByText(copy.banner_failed)).toBeInTheDocument())
    expect(screen.queryByText(/raw failure/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: copy.banner_button })).toBeEnabled()
  })
})
