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

import { contestService } from './contest-service'

describe('Phase 5 nomination / eligibility payloads', () => {
  beforeEach(() => postMock.mockReset())

  it('sends the nominee age statement only when one is given', async () => {
    postMock.mockResolvedValue({ status: 201, data: { public_status: 'PENDING_REVIEW' } })
    await contestService.submitContestant(7, 'Title', 'Description', [], ['https://youtu.be/x'], undefined,
      'Tanzania', 3, 'nomination', 'MINOR')
    expect(postMock.mock.calls[0][1]).toMatchObject({ entry_type: 'nomination', nominee_age_declaration: 'MINOR' })

    await contestService.submitContestant(7, 'Title', 'Description', [], [], undefined, undefined, 3, 'participation')
    expect(postMock.mock.calls[1][1]).not.toHaveProperty('nominee_age_declaration')
  })

  it('keeps a structured backend error (e.g. a locked entry) on the error for the page to render safely', async () => {
    // Eligibility itself never refuses (unmet requirements put the entry ON HOLD);
    // structured errors such as CONTEST_ENTRY_LOCKED must still reach the page intact.
    const detail = { code: 'CONTEST_ENTRY_LOCKED', message: "This entry can't be changed right now." }
    postMock.mockResolvedValue({ status: 403, data: { detail } })
    const error = await contestService
      .submitContestant(7, 'Title', 'Description', [], [], undefined, undefined, 3, 'participation')
      .catch((e: { response?: { data?: { detail?: unknown } } }) => e)
    expect(error.response?.data?.detail).toEqual(detail)
  })

  it('passes the HOLD response (pending review, next step, one-time claim token) through unchanged', async () => {
    const data = { public_status: 'PENDING_REVIEW', next_step: 'ADD_DATE_OF_BIRTH', eligibility_reasons: ['AGE_REQUIRED'] }
    postMock.mockResolvedValue({ status: 201, data })
    await expect(
      contestService.submitContestant(7, 'Title', 'Description', [], [], undefined, undefined, 3, 'participation'),
    ).resolves.toEqual(data)
  })
})
