import { describe, expect, it } from 'vitest'

import { assertSafeRemoteUrl } from '@/lib/safe-remote-url'

describe('link preview SSRF policy', () => {
  it.each([
    'http://127.0.0.1/admin',
    'http://10.0.0.1/',
    'http://172.16.1.2/',
    'http://192.168.1.2/',
    'http://169.254.169.254/latest/meta-data/',
    'http://[::1]/',
    'file:///etc/passwd',
    'http://user:pass@8.8.8.8/',
  ])('rejects unsafe target %s', async (value) => {
    await expect(assertSafeRemoteUrl(new URL(value))).rejects.toThrow('URL not allowed')
  })

  it('allows a public literal address', async () => {
    await expect(assertSafeRemoteUrl(new URL('https://8.8.8.8/'))).resolves.toBeUndefined()
  })
})
