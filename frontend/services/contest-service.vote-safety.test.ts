import { beforeEach, describe, expect, it, vi } from 'vitest'

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }))

vi.mock('@/lib/api', () => ({
  default: { post: postMock },
  apiService: {},
}))

vi.mock('@/lib/cache-service', () => ({
  cacheService: { get: vi.fn(), set: vi.fn(), invalidate: vi.fn() },
}))

vi.mock('@/lib/media-url', () => ({ normalizeMediaUrl: (value: string) => value }))

import { contestService, VOTE_UNAVAILABLE_MESSAGE } from './contest-service'

type VoteError = { code?: string; message?: string; response?: { status?: number; data?: { detail?: unknown } } }

describe('Phase 8 vote safety responses', () => {
  beforeEach(() => postMock.mockReset())

  it('turns an unavailable entry (404) into one generic, reason-free message', async () => {
    postMock.mockResolvedValue({ status: 404, data: { detail: 'Submission not found' } })
    const error = (await contestService.voteForContestant(5, { contestId: 3 }).catch((e: VoteError) => e)) as VoteError
    expect(error.code).toBe('vote_unavailable')
    expect(error.message).toBe(VOTE_UNAVAILABLE_MESSAGE)
    expect(error.response?.data?.detail).toBe(VOTE_UNAVAILABLE_MESSAGE)

    const replaced = (await contestService.replaceVote(5, 3).catch((e: VoteError) => e)) as VoteError
    expect(replaced.response?.data?.detail).toBe(VOTE_UNAVAILABLE_MESSAGE)
  })

  it('keeps the existing 409 conflict handling (already voted / five-vote limit)', async () => {
    postMock.mockResolvedValue({
      status: 409,
      data: { detail: { code: 'max_votes_reached', replaced_contestant: { id: 9, name: 'Unavailable entry', position: 5 } } },
    })
    const result = await contestService.voteForContestant(5, { contestId: 3 })
    expect(result).toMatchObject({ success: false, code: 'max_votes_reached' })
  })
})
