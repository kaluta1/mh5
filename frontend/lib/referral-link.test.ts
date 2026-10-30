import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/config', () => ({ getEffectiveAppUrl: () => 'https://myhigh5.com' }))

import { copyText, referralShortUrl } from './referral-link'

describe('referral short URL', () => {
  it('is the full /r/<code> link of the member on the site in use, never the code alone', () => {
    expect(referralShortUrl('ADY7HR0W')).toBe('https://myhigh5.com/r/ADY7HR0W')
    expect(referralShortUrl(' ab c ')).toBe('https://myhigh5.com/r/ab%20c')
  })
})

describe('copyText', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
  })

  it('reports success only when the clipboard took the text', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await expect(copyText('https://myhigh5.com/r/ADY7HR0W')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('https://myhigh5.com/r/ADY7HR0W')
  })

  it('falls back to the older copy, and reports failure when that is refused too', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) }, configurable: true,
    })
    const exec = vi.fn().mockReturnValueOnce(true).mockReturnValueOnce(false)
    Object.defineProperty(document, 'execCommand', { value: exec, configurable: true })
    await expect(copyText('x')).resolves.toBe(true)
    await expect(copyText('x')).resolves.toBe(false)
    expect(document.querySelectorAll('textarea')).toHaveLength(0)
  })
})
