import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'

/**
 * The provider's widget is opened with the URL of a session the BACKEND
 * created. Nothing secret is in the browser, only that URL is opened, and what
 * the widget reports is never taken as the result: the page is told the widget
 * finished, once, and then reads the status from the backend.
 */
vi.mock('next/script', () => ({
  default: ({ src }: { src: string }) => <span data-testid="provider-script" data-src={src} />,
}))

import { KalutaVerificationEmbed } from './kaluta-verification-embed'

const URL_OK = 'https://kalutakyc.com/verify/abc123'

describe('Kaluta verification widget', () => {
  const open = vi.fn()

  beforeEach(() => {
    vi.useFakeTimers()
    open.mockReset()
    window.KalutaKYC = { open, redirect: vi.fn() }
  })

  afterEach(() => {
    vi.useRealTimers()
    delete window.KalutaKYC
  })

  it("loads the provider's script and opens the session URL, with nothing else", () => {
    render(<KalutaVerificationEmbed verificationUrl={URL_OK} />)
    expect(screen.getByTestId('provider-script').getAttribute('data-src')).toBe('https://kalutakyc.com/embed.js')
    expect(open).toHaveBeenCalledTimes(1)
    const options = open.mock.calls[0][0]
    expect(options.url).toBe(URL_OK)
    expect(Object.keys(options).sort()).toEqual(['onClose', 'onComplete', 'url'])
    expect(JSON.stringify(options)).not.toMatch(/klt_|api[_-]?key|secret/i)
  })

  it('reports that the widget finished ONCE, whatever the widget says the result is', () => {
    const onFinished = vi.fn()
    render(<KalutaVerificationEmbed verificationUrl={URL_OK} onFinished={onFinished} />)
    const { onComplete, onClose } = open.mock.calls[0][0]
    onComplete({ status: 'approved', score: 99 })
    onClose({ status: 'approved' })
    onComplete({ status: 'approved' })
    expect(onFinished).toHaveBeenCalledTimes(1)
    expect(onFinished).toHaveBeenCalledWith()                      // the claimed status is not passed on
  })

  it('does not open the widget twice when the page renders again', () => {
    const { rerender } = render(<KalutaVerificationEmbed verificationUrl={URL_OK} onFinished={() => {}} />)
    rerender(<KalutaVerificationEmbed verificationUrl={URL_OK} onFinished={() => {}} />)
    rerender(<KalutaVerificationEmbed verificationUrl={URL_OK} onFinished={() => {}} />)
    expect(open).toHaveBeenCalledTimes(1)
  })

  it('opens the widget as soon as a slow script has loaded', () => {
    delete window.KalutaKYC
    render(<KalutaVerificationEmbed verificationUrl={URL_OK} />)
    expect(open).not.toHaveBeenCalled()
    window.KalutaKYC = { open, redirect: vi.fn() }
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(open).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/Continue on the secure page/)).toBeNull()
  })

  it("offers the provider's hosted page when its script never loads", () => {
    delete window.KalutaKYC
    render(<KalutaVerificationEmbed verificationUrl={URL_OK} scriptTimeoutMs={5000} />)
    act(() => {
      vi.advanceTimersByTime(5001)
    })
    const link = screen.getByRole('link', { name: /Continue on the secure page/ })
    expect(link.getAttribute('href')).toBe(URL_OK)
    expect(open).not.toHaveBeenCalled()
  })

  it.each([
    'https://evil.example/verify/abc123',
    'http://kalutakyc.com/verify/abc123',
    'javascript:alert(1)',
    'https://kalutakyc.com.evil.example/verify/abc123',
  ])('never opens %s', (url) => {
    render(<KalutaVerificationEmbed verificationUrl={url} />)
    expect(open).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toMatch(/cannot be opened/)
    expect(screen.queryByTestId('provider-script')).toBeNull()
    expect(screen.queryByRole('link')).toBeNull()
  })
})
