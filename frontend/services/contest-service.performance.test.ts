import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))

vi.mock('@/lib/api', () => ({
  default: { get: getMock },
  apiService: {},
}))

vi.mock('@/lib/cache-service', () => ({
  cacheService: { get: vi.fn(), set: vi.fn() },
}))

vi.mock('@/lib/media-url', () => ({ normalizeMediaUrl: (value: string) => value }))

import { contestService } from './contest-service'

describe('TopHigh5 request coalescing', () => {
  beforeEach(() => getMock.mockReset())

  it('shares one HTTP call between simultaneous identical requests', async () => {
    let resolveRequest!: (value: unknown) => void
    getMock.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve
      }),
    )

    const params = { roundId: 9, country: 'Tanzania', level: 'country' as const }
    const first = contestService.getTopHigh5ByCountry(params)
    const second = contestService.getTopHigh5ByCountry(params)

    expect(getMock).toHaveBeenCalledTimes(1)
    resolveRequest({ data: { round_id: 9, contests: [] } })
    await expect(Promise.all([first, second])).resolves.toEqual([
      { round_id: 9, contests: [] },
      { round_id: 9, contests: [] },
    ])
  })
})
