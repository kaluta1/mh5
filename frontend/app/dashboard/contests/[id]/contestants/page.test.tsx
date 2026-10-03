/**
 * "All contestants" page: a failed participant request must render the error
 * with a retry action, never the empty state. A successful [] still renders
 * the legitimate empty state.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const lookup = (key: string): string =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string

const mocks = vi.hoisted(() => ({
  getContest: vi.fn(),
  getRounds: vi.fn(),
  searchParams: new URLSearchParams('roundId=33'),
  router: { push: vi.fn(), replace: vi.fn(), back: vi.fn() },
}))

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup, language: 'en' }) }))
vi.mock('@/hooks/use-auth', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('next/navigation', () => ({
  useRouter: () => mocks.router,
  useParams: () => ({ id: '228' }),
  useSearchParams: () => mocks.searchParams,
}))
vi.mock('@/lib/api-service', () => ({ default: { getContest: mocks.getContest, getRounds: mocks.getRounds } }))
vi.mock('@/services/contest-service', () => ({ contestService: {} }))
vi.mock('@/services/follow-service', () => ({ followService: {} }))
vi.mock('@/lib/config', () => ({ getEffectiveApiUrl: () => 'https://example.test' }))

import ContestantsListPage from './page'

const ERROR_COPY = 'Could not load participants. Please try again.'
const EMPTY_COPY = 'No Nominators Found'

beforeEach(() => {
  mocks.getContest.mockReset()
  mocks.getRounds.mockReset().mockResolvedValue([])
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('all-contestants page participant states', () => {
  it('LOADING: shows neither the empty nor the error state while the request is pending', () => {
    mocks.getContest.mockReturnValue(new Promise(() => {}))
    render(<ContestantsListPage />)

    expect(screen.queryByText(EMPTY_COPY)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('ERROR: a failed request shows the error and a retry, never the empty state', async () => {
    mocks.getContest.mockRejectedValue(new Error('Request failed with status code 500'))
    render(<ContestantsListPage />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(ERROR_COPY)
    expect(alert).not.toHaveTextContent('status code 500')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByText(EMPTY_COPY)).not.toBeInTheDocument()
    expect(screen.queryByText('No Contestants Found')).not.toBeInTheDocument()
  })

  it('ERROR then retry: a successful [] afterwards shows the genuine empty state', async () => {
    mocks.getContest.mockRejectedValue(new Error('Network Error'))
    render(<ContestantsListPage />)
    const retry = await screen.findByRole('button', { name: 'Try again' })

    mocks.getContest.mockReset().mockResolvedValue({ name: 'Freestyle Rap', contest_mode: 'nomination', contestants: [] })
    fireEvent.click(retry)

    expect(await screen.findByText(EMPTY_COPY)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('EMPTY: a successful [] response renders the legitimate empty state', async () => {
    mocks.getContest.mockResolvedValue({ name: 'Freestyle Rap', contest_mode: 'nomination', contestants: [] })
    render(<ContestantsListPage />)

    expect(await screen.findByText(EMPTY_COPY)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(ERROR_COPY)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })
})
