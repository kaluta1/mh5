import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import en from '@/lib/translations/en.json'
import { contestCardState, isNominationOpen, nominationCtaState, ownEntryCardState } from '@/lib/nomination-cta'

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

const PENDING = 'Your entry is pending review'
const REJECTED = 'Your entry was not approved'
const LIVE = 'Your entry is live'
const SUBMITTED = 'Your entry is submitted'

describe('contest card state rule', () => {
  const open = { isNomination: true, nominationOpen: true }

  it('A. no own entry + zero public participants: first nominator', () => {
    expect(contestCardState({ ...open, contestants: 0, hasOwnEntry: false })).toEqual({ view: 'be_first', own: null })
  })

  it('B. held own entry + zero public participants: own pending state, never first nominator', () => {
    expect(contestCardState({ ...open, contestants: 0, hasOwnEntry: true, ownEntryStatus: 'PENDING_REVIEW' })).toEqual({
      view: 'own',
      own: 'pending',
    })
  })

  it('C. rejected own entry is rejected, not pending and not live', () => {
    expect(contestCardState({ ...open, contestants: 0, hasOwnEntry: true, ownEntryStatus: 'REJECTED' })).toEqual({
      view: 'own',
      own: 'rejected',
    })
  })

  it('D. published own entry never yields the first-nominator state', () => {
    expect(contestCardState({ ...open, contestants: 0, hasOwnEntry: true, ownEntryStatus: 'PUBLIC' })).toEqual({
      view: 'own',
      own: 'live',
    })
    expect(contestCardState({ ...open, contestants: 4, hasOwnEntry: true, ownEntryStatus: 'PUBLIC' })).toEqual({
      view: 'view',
      own: 'live',
    })
  })

  it('E. an unknown count is not zero', () => {
    for (const contestants of [null, undefined, Number.NaN]) {
      expect(contestCardState({ ...open, contestants, hasOwnEntry: false }).view).toBe('count_unknown')
    }
  })

  it('an own entry with no status from the server is "submitted", never first nominator', () => {
    expect(contestCardState({ ...open, contestants: 0, hasOwnEntry: true }).own).toBe('submitted')
    expect(ownEntryCardState(false, 'PENDING_REVIEW')).toBeNull()
  })

  it('a status without an own entry in this card round is ignored', () => {
    expect(contestCardState({ ...open, contestants: 0, hasOwnEntry: false, ownEntryStatus: 'PENDING_REVIEW' })).toEqual({
      view: 'be_first',
      own: null,
    })
  })
})

describe('ContestCard owner entry state (the card on /dashboard/contests)', () => {
  const openRound = { contestants: 0, isSubmissionOpen: true, isRoundClosed: false }

  it('held nomination + 0 public participants: shows pending review with Edit, not "Be the first nominator!"', () => {
    const { onParticipate, onViewContestants } = renderCard({
      ...openRound,
      currentUserContesting: true,
      currentUserEntryStatus: 'PENDING_REVIEW',
    })
    expect(screen.getByText(PENDING)).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByText(NONE)).not.toBeInTheDocument()
    // The existing-entry action is offered, not "Nominate".
    const edit = screen.getByRole('button', { name: /Edit/ })
    expect(screen.queryByRole('button', { name: /Nominate/ })).not.toBeInTheDocument()
    edit.click()
    expect(onParticipate).toHaveBeenCalledTimes(1)
    screen.getByRole('button', { name: PENDING }).click()
    expect(onViewContestants).toHaveBeenCalledTimes(1)
  })

  it('no own entry + 0 public participants: the first-nominator state is still valid', () => {
    renderCard({ ...openRound, currentUserContesting: false })
    expect(screen.getByText(FIRST)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Nominate/ })).toBeInTheDocument()
    expect(screen.queryByText(PENDING)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Edit/ })).not.toBeInTheDocument()
  })

  it('rejected own entry: rejected wording, never pending, approved/live or first nominator', () => {
    renderCard({ ...openRound, currentUserContesting: true, currentUserEntryStatus: 'REJECTED' })
    expect(screen.getByText(REJECTED)).toBeInTheDocument()
    expect(screen.queryByText(PENDING)).not.toBeInTheDocument()
    expect(screen.queryByText(LIVE)).not.toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
  })

  it('published own entry with zero cards in this filter: no first-nominator message', () => {
    renderCard({ ...openRound, currentUserContesting: true, currentUserEntryStatus: 'PUBLIC' })
    expect(screen.getByText(LIVE)).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByText(PENDING)).not.toBeInTheDocument()
  })

  it('published own entry among public entries: the normal "View" action', () => {
    renderCard({ ...openRound, contestants: 3, currentUserContesting: true, currentUserEntryStatus: 'PUBLIC' })
    expect(screen.getByRole('button', { name: /View\s+Nominators/ })).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByTestId('contest-card-own-entry-status')).not.toBeInTheDocument()
  })

  it('held own entry while others are public: "View" action plus a pending note', () => {
    renderCard({ ...openRound, contestants: 2, currentUserContesting: true, currentUserEntryStatus: 'PENDING_REVIEW' })
    expect(screen.getByTestId('contest-card-own-entry-status')).toHaveTextContent(PENDING)
    expect(screen.getByRole('button', { name: /View\s+Nominators/ })).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
  })

  it('own entry whose status the server did not send: "submitted", not first nominator', () => {
    renderCard({ ...openRound, currentUserContesting: true })
    expect(screen.getByText(SUBMITTED)).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
  })

  it('held entry in a closed round: pending state instead of "No nominations"', () => {
    renderCard({
      contestants: 0,
      isSubmissionOpen: false,
      isRoundClosed: true,
      currentUserContesting: true,
      currentUserEntryStatus: 'PENDING_REVIEW',
    })
    expect(screen.getByText(PENDING)).toBeInTheDocument()
    expect(screen.queryByText(NONE)).not.toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
  })

  it('own entry removed because its video is gone: unavailable wording, never first nominator', () => {
    renderCard({ ...openRound, currentUserContesting: true, currentUserEntryStatus: 'CREATIVE_UNAVAILABLE' })
    expect(screen.getByText('Your video is no longer available')).toBeInTheDocument()
    expect(screen.queryByText(PENDING)).not.toBeInTheDocument()
    expect(screen.queryByText(REJECTED)).not.toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
  })

  it('a just-published nomination shows the owner the normal live card, not a pending state', () => {
    renderCard({ ...openRound, contestants: 1, currentUserContesting: true, currentUserEntryStatus: 'PUBLIC' })
    expect(screen.getByRole('button', { name: /Edit/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /View\s+Nominator/ })).toBeInTheDocument()
    expect(screen.queryByText(PENDING)).not.toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByTestId('contest-card-own-entry-status')).not.toBeInTheDocument()
  })

  it('unknown participant count is not shown as zero or as an invitation', () => {
    renderCard({ ...openRound, participantCountKnown: false })
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByText(NONE)).not.toBeInTheDocument()
    expect(screen.queryByText(/View 0/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /View\s+Nominators/ })).toBeInTheDocument()
  })

  it('participation card with a held own entry: pending state and Edit, with no nomination copy', () => {
    renderCard({
      ...openRound,
      isNomination: false,
      currentUserContesting: true,
      currentUserEntryStatus: 'PENDING_REVIEW',
    })
    expect(screen.getByText(PENDING)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Edit/ })).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByText(NONE)).not.toBeInTheDocument()
    expect(screen.queryByText(/nominat/i)).not.toBeInTheDocument()
  })

  it('participation card without an own entry keeps "Participate" and the "View" action', () => {
    renderCard({ ...openRound, isNomination: false, currentUserContesting: false })
    expect(screen.getByRole('button', { name: /Participate/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^View / })).toBeInTheDocument()
    expect(screen.queryByText(FIRST)).not.toBeInTheDocument()
    expect(screen.queryByText(PENDING)).not.toBeInTheDocument()
  })
})
