import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import en from '@/lib/translations/en.json'
import { listViewState, loadList } from '@/lib/participants-state'

const lookup = (key: string): string =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string
vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup }) }))

import { ContestListFeedback } from './contest-list-feedback'

const EMPTY_TEXT = en.contests.no_contests
const ERROR_TEXT = en.dashboard.contests.list_load_failed

/** The list's state after one request, as the contests page derives it. */
async function afterRequest(request: () => Promise<unknown[]>) {
  const result = await loadList(request)
  const rows = result.ok ? result.rows : []
  return { rows, state: listViewState({ loading: false, error: !result.ok, count: rows.length }) }
}

describe('contest list: empty is not the same as failed', () => {
  it('a populated response shows the contests and no message', async () => {
    const { rows, state } = await afterRequest(() => Promise.resolve([{ id: 1 }, { id: 2 }]))
    expect(rows).toHaveLength(2)
    expect(state).toBe('READY')
    const { container } = render(<ContestListFeedback state={state} emptyMessage={EMPTY_TEXT} onRetry={() => undefined} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('a successful empty response shows the normal "no contests" text, with no retry', async () => {
    const { state } = await afterRequest(() => Promise.resolve([]))
    expect(state).toBe('EMPTY')
    render(<ContestListFeedback state={state} emptyMessage={EMPTY_TEXT} onRetry={() => undefined} />)
    expect(screen.getByText(EMPTY_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('a failed request shows an error with a retry action, never "no contests"', async () => {
    const { state } = await afterRequest(() => Promise.reject(new Error('Request failed with status code 500')))
    expect(state).toBe('ERROR')
    render(<ContestListFeedback state={state} emptyMessage={EMPTY_TEXT} onRetry={() => undefined} />)
    expect(screen.getByRole('alert')).toHaveTextContent(ERROR_TEXT)
    expect(screen.queryByText(EMPTY_TEXT)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: en.common.try_again })).toBeInTheDocument()
  })

  it('retry runs the request again and a success replaces the error', async () => {
    const request = vi.fn<() => Promise<unknown[]>>()
      .mockRejectedValueOnce(new Error('Network Error'))
      .mockResolvedValueOnce([{ id: 7 }])
    let current = await afterRequest(request)
    const retry = vi.fn(async () => { current = await afterRequest(request) })
    const view = render(<ContestListFeedback state={current.state} emptyMessage={EMPTY_TEXT} onRetry={retry} />)
    fireEvent.click(screen.getByRole('button', { name: en.common.try_again }))
    expect(retry).toHaveBeenCalledTimes(1)
    await retry.mock.results[0].value
    expect(request).toHaveBeenCalledTimes(2)
    expect(current).toEqual({ rows: [{ id: 7 }], state: 'READY' })
    view.rerender(<ContestListFeedback state={current.state} emptyMessage={EMPTY_TEXT} onRetry={retry} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('a retry that fails again is still an error', async () => {
    const request = vi.fn<() => Promise<unknown[]>>().mockRejectedValue(new Error('timeout of 30000ms exceeded'))
    expect((await afterRequest(request)).state).toBe('ERROR')
    expect((await afterRequest(request)).state).toBe('ERROR')
  })

  it('while loading there is neither an error nor an empty message', () => {
    const state = listViewState({ loading: true, error: true, count: 0 })
    expect(state).toBe('LOADING')
    const { container } = render(<ContestListFeedback state={state} emptyMessage={EMPTY_TEXT} onRetry={() => undefined} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('the contests page uses it', () => {
  const page = readFileSync(join(__dirname, '..', '..', 'app', 'dashboard', 'contests', 'page.tsx'), 'utf8')

  it('marks every failed list request as failed, and clears the mark when a request starts', () => {
    const fetch = page.slice(page.indexOf('const fetchContestsForRound = async'), page.indexOf('fetchContestsForRound()'))
    expect(fetch.indexOf('setContestsLoadFailed(false)')).toBeGreaterThan(-1)
    expect(fetch.indexOf('setContestsLoadFailed(false)')).toBeLessThan(fetch.indexOf('try {'))
    // both ways out of a failure: the general one and "timed out, retried, failed again"
    expect(fetch.match(/setContestsLoadFailed\(true\)/g)).toHaveLength(2)
    expect(fetch).toMatch(/Retry also failed[\s\S]{0,80}setContestsLoadFailed\(true\)/)
    expect(fetch).toMatch(/Failed to fetch contests[\s\S]{0,80}setContestsLoadFailed\(true\)/)
    // an aborted (superseded) request is not a failure
    expect(fetch).toMatch(/AbortError[\s\S]{0,80}return/)
  })

  it('renders the error state from that mark and retries by reloading the list', () => {
    expect(page).toContain('listViewState({ loading: false, error: contestsLoadFailed, count: 0 })')
    expect(page).toMatch(/<ContestListFeedback[\s\S]{0,200}onRetry=\{\(\) => setListRefreshKey\(\(key\) => key \+ 1\)\}/)
    expect(page).toMatch(/\}, \[[^\]]*listRefreshKey[^\]]*\]\)/)              // the list effect reloads on it
    // the "no contests" texts are only ever the EMPTY message
    const outside = page.replace(/<ContestListFeedback[\s\S]*?\/>/, '')
    expect(outside).not.toContain("t('contests.no_contests')")
    expect(outside).not.toContain("t('dashboard.contests.no_nominated_yet')")
  })
})
