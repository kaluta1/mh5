import { describe, expect, it } from 'vitest'

import { applicationStatus, ownEntryPendingReview } from './application-status'
import { listViewState, loadList } from './participants-state'

describe('participant list state', () => {
  it('is LOADING while the request is in flight, whatever is already on screen', () => {
    expect(listViewState({ loading: true, count: 0 })).toBe('LOADING')
    expect(listViewState({ loading: true, count: 3, error: 'old' })).toBe('LOADING')
  })

  it('is EMPTY only when a request succeeded and returned nothing', () => {
    expect(listViewState({ loading: false, count: 0 })).toBe('EMPTY')
    expect(listViewState({ loading: false, count: 0, error: null })).toBe('EMPTY')
  })

  it('is ERROR when the request failed, never EMPTY', () => {
    expect(listViewState({ loading: false, count: 0, error: new Error('500') })).toBe('ERROR')
    expect(listViewState({ loading: false, count: 0, error: 'Load failed' })).toBe('ERROR')
    // stale rows from an earlier success do not hide a failed refresh
    expect(listViewState({ loading: false, count: 4, error: 'Load failed' })).toBe('ERROR')
  })

  it('is READY when rows were returned', () => {
    expect(listViewState({ loading: false, count: 2 })).toBe('READY')
  })
})

describe('loadList', () => {
  it('reports a failed participant request as a failure', async () => {
    const failure = new Error('Request failed with status code 500')
    const result = await loadList(() => Promise.reject(failure))
    expect(result).toEqual({ ok: false, error: failure })
    const state = listViewState({ loading: false, count: 0, error: result.ok === false ? result.error : null })
    expect(state).toBe('ERROR')
    expect(state).not.toBe('EMPTY')
  })

  it('reports a malformed response as a failure, not as an empty list', async () => {
    const result = await loadList(() => Promise.resolve(undefined))
    expect(result.ok).toBe(false)
  })

  it('reports a successful empty response as empty', async () => {
    const result = await loadList(() => Promise.resolve([]))
    expect(result).toEqual({ ok: true, rows: [] })
    expect(listViewState({ loading: false, count: 0 })).toBe('EMPTY')
  })

  it('returns the rows of a successful response', async () => {
    const result = await loadList(() => Promise.resolve([{ id: 1 }, { id: 2 }]))
    expect(result).toEqual({ ok: true, rows: [{ id: 1 }, { id: 2 }] })
  })
})

describe('application status shown to its owner', () => {
  it('is pending while the entry is on hold, even though is_qualified defaults to true', () => {
    expect(applicationStatus({ is_qualified: true, public_status: 'PENDING_REVIEW' })).toBe('pending')
  })

  it('is approved once the entry is public', () => {
    expect(applicationStatus({ is_qualified: true, public_status: 'PUBLIC' })).toBe('approved')
  })

  it('keeps the previous meaning when the server sends no publication status', () => {
    expect(applicationStatus({ is_qualified: true })).toBe('approved')
    expect(applicationStatus({ is_qualified: false })).toBe('pending')
    expect(applicationStatus({ is_qualified: false, public_status: 'PUBLIC' })).toBe('pending')
  })

  it('treats any non-public status as pending', () => {
    expect(applicationStatus({ is_qualified: true, public_status: 'SOMETHING_NEW' })).toBe('pending')
  })

  it('tells the owner their entry is pending only when the server says so', () => {
    expect(ownEntryPendingReview({ current_user_entry_status: 'PENDING_REVIEW' })).toBe(true)
    expect(ownEntryPendingReview({ current_user_entry_status: 'PUBLIC' })).toBe(false)
    expect(ownEntryPendingReview({ current_user_entry_status: null })).toBe(false)
    expect(ownEntryPendingReview(null)).toBe(false)
  })
})

describe('rejected application', () => {
  it('is rejected, never approved, even though is_qualified is true', () => {
    expect(applicationStatus({ is_qualified: true, public_status: 'REJECTED' })).toBe('rejected')
    expect(applicationStatus({ is_qualified: true, public_status: 'REJECTED' })).not.toBe('approved')
  })

  it('is distinct from a pending application', () => {
    expect(applicationStatus({ is_qualified: true, public_status: 'REJECTED' })).not.toBe(
      applicationStatus({ is_qualified: true, public_status: 'PENDING_REVIEW' }),
    )
    expect(ownEntryPendingReview({ current_user_entry_status: 'REJECTED' })).toBe(false)
  })
})

describe('entry removed because its video no longer exists', () => {
  it('is "unavailable": not approved, not pending, not rejected', () => {
    expect(applicationStatus({ is_qualified: true, public_status: 'CREATIVE_UNAVAILABLE' })).toBe('unavailable')
    expect(ownEntryPendingReview({ current_user_entry_status: 'CREATIVE_UNAVAILABLE' })).toBe(false)
  })
})

describe('a nomination is published immediately', () => {
  it('is shown to its owner as approved/live, never as pending review', () => {
    expect(applicationStatus({ is_qualified: true, public_status: 'PUBLIC' })).toBe('approved')
    expect(ownEntryPendingReview({ current_user_entry_status: 'PUBLIC' })).toBe(false)
  })
})
