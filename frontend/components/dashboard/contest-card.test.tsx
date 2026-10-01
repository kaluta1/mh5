import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import en from '@/lib/translations/en.json'
import { isNominationOpen, nominationCtaState } from '@/lib/nomination-cta'

const lookup = (key: string): string =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup, language: 'en' }) }))
vi.mock('@/contexts/clock-context', () => ({ useClock: () => new Date('2026-10-02T00:00:00Z') }))

import { ContestCard } from './contest-card'

type CardProps = React.ComponentProps<typeof ContestCard>

function renderCard(overrides: Partial<CardProps>) {
  const onViewContestants = vi.fn()
  const onParticipate = vi.fn()
  const props: CardProps = {
    id: '5',
    title: 'Comedy Contest',
    coverImage: '🏆',
    startDate: new Date('2026-07-01'),
    status: 'country',
    received: 0,
    contestants: 0,
    likes: 0,
    comments: 0,
    isOpen: true,
    isFavorite: false,
    isNomination: true,
    onViewContestants,
    onToggleFavorite: vi.fn(),
    onParticipate,
    ...overrides,
  }
  const view = render(<ContestCard {...props} />)
  return { ...view, onViewContestants, onParticipate }
}

const FIRST = 'Be the first nominator!'
const NONE = 'No nominations'

describe('nomination CTA state', () => {
  it('is open only while the submission window is open and not in the Vote view', () => {
    expect(isNominationOpen({ isSubmissionOpen: true })).toBe(true)
    expect(isNominationOpen({})).toBe(true)
    expect(isNominationOpen({ isSubmissionOpen: false })).toBe(false)
    expect(isNominationOpen({ isRoundClosed: true, isSubmissionOpen: true })).toBe(false)
    expect(isNominationOpen({ isVoteMode: true, isSubmissionOpen: true })).toBe(false)
  })

  it('separates "nobody was nominated" from "you can nominate now"', () => {
    expect(nominationCtaState({ contestants: 0, nominationOpen: true })).toBe('be_first')
    expect(nominationCtaState({ contestants: 0, nominationOpen: false })).toBe('none')
    expect(nominationCtaState({ contestants: 1, nominationOpen: false })).toBe('view')
    expect(nominationCtaState({ contestants: 3, nominationOpen: true })).toBe('view')
  })
})

describe('ContestCard nomination CTA', () => {
  it('open nomination round with zero nominees invites the first nominator', () => {
    renderCard({ contestants: 0, isSubmissionOpen: true, isRoundClosed: false })
    expect(screen.getByText(FIRST)).toBeInTheDocument()
    expect(screen.queryByText(NONE)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Nominate/ })).toBeInTheDocument()
  })

  it('closed historical round with zero nominees shows a neutral non-action state', () => {
    const { onViewContestants } = renderCard({ contestants: 0, isSubmissionOpen: false, isRoundClosed: true })
    expect(screen.getByText(NONE)).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    // Not a button, and no nominate action is offered for a closed round.
    expect(screen.getByTestId('contest-card-no-nominations').tagName).toBe('DIV')
    expect(screen.queryByRole('button', { name: /Nominate/ })).not.toBeInTheDocument()
    screen.getByTestId('contest-card-no-nominations').click()
    expect(onViewContestants).not.toHaveBeenCalled()
  })

  it('closed round by the backend flag alone (no client date signal) is still closed', () => {
    renderCard({ contestants: 0, isSubmissionOpen: false, isRoundClosed: false, isOpen: false })
    expect(screen.getByText(NONE)).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
  })

  it('closed historical round with one nominee shows "View 1 Nominator"', () => {
    const { onViewContestants } = renderCard({ contestants: 1, isSubmissionOpen: false, isRoundClosed: true })
    const button = screen.getByRole('button', { name: 'View 1 Nominator' })
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Nominate$/ })).not.toBeInTheDocument()
    button.click()
    expect(onViewContestants).toHaveBeenCalledTimes(1)
  })

  it('closed historical round with several nominees uses the plural', () => {
    renderCard({ contestants: 3, isSubmissionOpen: false, isRoundClosed: true })
    expect(screen.getByRole('button', { name: 'View 3 Nominators' })).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByText(NONE)).not.toBeInTheDocument()
  })

  it('Vote view with zero nominees never invites a nomination', () => {
    renderCard({ contestants: 0, isSubmissionOpen: true, isRoundClosed: false, isVoteMode: true })
    expect(screen.getByText(NONE)).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
  })

  it('participation cards are unchanged', () => {
    renderCard({ contestants: 0, isNomination: false, isSubmissionOpen: false, isRoundClosed: true })
    expect(screen.queryByText(NONE)).not.toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /View 0/ })).toBeInTheDocument()
  })
})
