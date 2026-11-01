import { describe, expect, it } from 'vitest'
import { inFeedAdCount, interleave, isAdRoute } from './placement'

describe('ad placement rules', () => {
  it('one in-feed ad after every five organic items, at most five, none for short lists', () => {
    expect([0, 4, 5, 9, 10, 26, 100].map((n) => inFeedAdCount(n))).toEqual([0, 0, 1, 1, 2, 5, 5])
  })

  it('never adjacent, never more ads than organic items, first ad after item five', () => {
    for (const n of [0, 3, 5, 6, 11, 25, 31, 60]) {
      const out = interleave(Array.from({ length: n }, (_, i) => i))
      const ads = out.filter((x) => x.kind === 'ad').length
      expect(ads).toBeLessThanOrEqual(Math.min(5, n))
      out.forEach((x, i) => {
        if (x.kind === 'ad') {
          expect(out[i - 1]?.kind).toBe('item')
          expect(out[i + 1]?.kind === 'ad').toBe(false)
        }
      })
      const firstAd = out.findIndex((x) => x.kind === 'ad')
      if (firstAd >= 0) expect(firstAd).toBe(5)
    }
  })

  it('infinite scroll keeps the 5-item spacing and the per-page cap across batches', () => {
    const pos = (xs: ReturnType<typeof interleave>) => xs.map((x, i) => (x.kind === 'ad' ? i : -1)).filter((i) => i >= 0)
    const batch1 = interleave(Array.from({ length: 12 }, (_, i) => i))
    const batch2 = interleave(Array.from({ length: 40 }, (_, i) => i))
    expect(pos(batch2).slice(0, pos(batch1).length)).toEqual(pos(batch1))
    expect(pos(batch2).length).toBe(5)
  })

  it('allows public content routes and excludes sensitive areas', () => {
    for (const ok of ['/contests', '/contests/12/entry/34', '/dashboard/contests', '/dashboard/feed', '/feed/9',
      '/profile/amina', '/dashboard/marketplace']) expect(isAdRoute(ok)).toBe(true)
    for (const no of ['/dashboard/messages', '/dashboard/messages/4', '/dashboard/settings', '/dashboard/admin',
      '/dashboard/admin/advertising', '/dashboard/wallet', '/dashboard/wallet/transactions', '/payout-wallet/confirm',
      '/dashboard/kyc', '/nominations/claim', '/login', '/register', '/dashboard/commissions', '/dashboard/ad-earnings',
      '/dashboard/advertise', '/dashboard/sponsored', '/payments/checkout', '/dashboard/marketplace/seller', '/']) {
      expect(isAdRoute(no)).toBe(false)
    }
    expect(isAdRoute(null)).toBe(false)
    expect(isAdRoute(undefined)).toBe(false)
  })
})
