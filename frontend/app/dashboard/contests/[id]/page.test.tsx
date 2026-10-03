/**
 * The contest page's participant area is always in exactly one state:
 * LOADING, EMPTY, ERROR or READY. A failed participant request must render the
 * error message with a retry action -- never the empty state ("0 participants",
 * "Be the first to nominate!"), which would tell the member the request
 * succeeded and found nothing.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const lookup = (key: string): string =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string

const mocks = vi.hoisted(() => ({
  getContest: vi.fn(),
  getContestantsByContest: vi.fn(),
  // One stable instance: the page's effects depend on its identity.
  searchParams: new URLSearchParams('roundId=33&viewOnly=true&country=Tanzania&entryType=nomination'),
  router: { push: vi.fn(), replace: vi.fn(), back: vi.fn() },
  auth: { user: null as null | { id: number; country?: string }, isAuthenticated: false, isLoading: false },
}))

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup, language: 'en' }) }))
vi.mock('@/hooks/use-auth', () => ({ useAuth: () => mocks.auth }))
vi.mock('next/navigation', () => ({
  useRouter: () => mocks.router,
  useParams: () => ({ id: '228' }),
  useSearchParams: () => mocks.searchParams,
}))
vi.mock('@/lib/api-service', () => ({ default: { getContest: mocks.getContest } }))
vi.mock('@/services/contest-service', () => ({
  contestService: { getContestantsByContest: mocks.getContestantsByContest },
}))
vi.mock('@/lib/config', () => ({ getEffectiveApiUrl: () => 'https://example.test' }))
vi.mock('@/components/ui/skeleton', () => ({
  ContestDetailSkeleton: () => <div data-testid="participants-loading" />,
}))
vi.mock('@/components/dashboard/contestants-list', () => ({
  ContestantsList: ({ contestants }: { contestants: unknown[] }) => (
    <div data-testid="participants-ready">{contestants.length} cards</div>
  ),
}))
vi.mock('@/components/dashboard/contestants-sidebar', () => ({ ContestantsSidebar: () => null }))
vi.mock('@/components/dashboard/my-votes-panel', () => ({ default: () => null }))
vi.mock('@/components/dashboard/hover-info-dialog', () => ({ HoverInfoDialog: () => null }))
vi.mock('@/components/dashboard/report-contestant-dialog', () => ({ ReportContestantDialog: () => null }))
vi.mock('@/components/dashboard/contest-info-dialog', () => ({ ContestInfoDialog: () => null }))
vi.mock('@/components/dashboard/location-filter-bar', () => ({ LocationFilterBar: () => null }))

import ContestDetailPage from './page'

const ERROR_COPY = 'Could not load this contest. Please try again.'
const EMPTY_TITLE = 'Be the first to nominate!'
const EMPTY_MESSAGE = /No nominations yet/
const PENDING_TITLE = 'Your entry is pending review'

function contestResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: 228,
    name: 'Freestyle Rap',
    contest_mode: 'nomination',
    display_round_id: 33,
    contestants: [],
    entries_count: 0,
    ...overrides,
  }
}

function expectNoEmptyState() {
  expect(screen.queryByText(EMPTY_TITLE)).not.toBeInTheDocument()
  expect(screen.queryByText(EMPTY_MESSAGE)).not.toBeInTheDocument()
  expect(screen.queryByText(/0 participants/)).not.toBeInTheDocument()
}

beforeEach(() => {
  mocks.getContest.mockReset()
  mocks.getContestantsByContest.mockReset().mockResolvedValue([])
  mocks.auth.user = null
  mocks.auth.isAuthenticated = false
  window.sessionStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('contest page participant states', () => {
  it('LOADING: shows the loading state, not an empty roster, while the request is pending', () => {
    mocks.getContest.mockReturnValue(new Promise(() => {}))
    render(<ContestDetailPage />)

    expect(screen.getByTestId('participants-loading')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expectNoEmptyState()
  })

  it('ERROR: a failed participant request shows the error and a retry, never the empty state', async () => {
    mocks.getContest.mockRejectedValue(new Error('Request failed with status code 500'))
    render(<ContestDetailPage />)

    const alert = await screen.findByRole('alert', undefined, { timeout: 8000 })
    expect(alert).toHaveTextContent(ERROR_COPY)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    // The raw exception text is not shown to the member.
    expect(alert).not.toHaveTextContent('status code 500')

    expectNoEmptyState()
    expect(screen.queryByTestId('participants-ready')).not.toBeInTheDocument()
    expect(screen.queryByTestId('participants-loading')).not.toBeInTheDocument()
  }, 15000)

  it('ERROR: shows the server explanation when it sends one', async () => {
    mocks.getContest.mockRejectedValue({ response: { status: 500, data: { detail: 'Could not load participants. Please try again.' } } })
    render(<ContestDetailPage />)

    const alert = await screen.findByRole('alert', undefined, { timeout: 8000 })
    expect(alert).toHaveTextContent('Could not load participants. Please try again.')
    expectNoEmptyState()
  }, 15000)

  it('ERROR then retry: the retry action reloads and a successful [] then shows the genuine empty state', async () => {
    mocks.getContest.mockRejectedValue(new Error('Network Error'))
    render(<ContestDetailPage />)
    const retry = await screen.findByRole('button', { name: 'Try again' }, { timeout: 8000 })
    expectNoEmptyState()

    const failedCalls = mocks.getContest.mock.calls.length
    mocks.getContest.mockReset().mockResolvedValue(contestResponse())
    fireEvent.click(retry)

    expect(await screen.findByText(EMPTY_TITLE)).toBeInTheDocument()
    expect(mocks.getContest).toHaveBeenCalled()
    expect(failedCalls).toBeGreaterThan(0)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  }, 20000)

  it('EMPTY: a successful [] response renders the legitimate empty state', async () => {
    mocks.getContest.mockResolvedValue(contestResponse())
    render(<ContestDetailPage />)

    expect(await screen.findByText(EMPTY_TITLE)).toBeInTheDocument()
    expect(screen.getByText(EMPTY_MESSAGE)).toBeInTheDocument()
    expect(screen.getByText(/0 participants/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(ERROR_COPY)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('EMPTY for the owner of a held entry: says "pending review", not "be the first"', async () => {
    mocks.auth.user = { id: 9, country: 'Tanzania' }
    mocks.auth.isAuthenticated = true
    mocks.getContest.mockResolvedValue(
      contestResponse({ current_user_contesting: true, current_user_entry_status: 'PENDING_REVIEW' }),
    )
    render(<ContestDetailPage />)

    expect(await screen.findByText(PENDING_TITLE)).toBeInTheDocument()
    expect(screen.queryByText(EMPTY_TITLE)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('READY: returned participants are rendered, with neither the empty nor the error state', async () => {
    mocks.getContest.mockResolvedValue(
      contestResponse({
        contestants: [{ id: 1, user_id: 5, title: 'Entry', description: '<p>Hi</p>', author_name: 'A', author_country: 'Tanzania' }],
      }),
    )
    render(<ContestDetailPage />)

    expect(await screen.findByTestId('participants-ready')).toHaveTextContent('1 cards')
    await waitFor(() => expect(screen.getByText(/1 participants/)).toBeInTheDocument())
    expect(screen.queryByText(EMPTY_TITLE)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
