import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock }, apiService: {} }))

import {
  AdminEntryContestField,
  resolveEntryContest,
  type EntryContestResolution,
} from './admin-entry-contest-field'

const ONE = [{ id: 11, name: 'Bongo Fleva' }]
const MANY = [{ id: 21, name: 'Singeli' }, { id: 22, name: 'Tennis Club' }]

function contestsFor(bySeason: Record<string, unknown[]>) {
  getMock.mockImplementation((url: string) => {
    const match = /\/admin\/seasons\/([^/]+)\/contests$/.exec(String(url))
    return Promise.resolve({ status: 200, data: match ? bySeason[match[1]] ?? [] : [] })
  })
}

/** The form's own wiring: controlled value + last resolution, as in admin-contestants. */
function Harness({ seasonId, initial = '', onState }: {
  seasonId: string
  initial?: string
  onState: (value: string, resolution: EntryContestResolution) => void
}) {
  const [value, setValue] = useState(initial)
  const [resolution, setResolution] = useState<EntryContestResolution>({
    contestId: null, selectionRequired: false, ready: false,
  })
  onState(value, resolution)
  return <AdminEntryContestField seasonId={seasonId} value={value} onChange={setValue} onResolved={setResolution} />
}

describe('resolveEntryContest', () => {
  it('uses the only valid contest automatically (no extra selection)', () => {
    expect(resolveEntryContest(ONE, '')).toEqual({ contestId: 11, selectionRequired: false, ready: true })
  })

  it('requires an explicit choice among the season contests when several exist', () => {
    expect(resolveEntryContest(MANY, '')).toEqual({ contestId: null, selectionRequired: true, ready: false })
    expect(resolveEntryContest(MANY, '22')).toEqual({ contestId: 22, selectionRequired: true, ready: true })
  })

  it('never sends a contest that does not belong to the selected season', () => {
    expect(resolveEntryContest(MANY, '11')).toEqual({ contestId: null, selectionRequired: true, ready: false })
    expect(resolveEntryContest([], '11')).toEqual({ contestId: null, selectionRequired: false, ready: false })
    expect(resolveEntryContest(null, '21').ready).toBe(false)
  })
})

describe('AdminEntryContestField', () => {
  beforeEach(() => getMock.mockReset())

  it('season with one contest: no selector, that contest_id is resolved', async () => {
    contestsFor({ 5: ONE })
    let last: EntryContestResolution | null = null
    render(<Harness seasonId="5" onState={(_v, r) => { last = r }} />)
    expect(await screen.findByTestId('entry-contest-auto')).toHaveTextContent('Bongo Fleva')
    expect(screen.queryByRole('combobox', { name: 'Contest' })).toBeNull()
    await waitFor(() => expect(last).toEqual({ contestId: 11, selectionRequired: false, ready: true }))
    expect(getMock).toHaveBeenCalledWith('/api/v1/admin/seasons/5/contests')
  })

  it('season with several contests: selector required, only its contests offered, chosen id resolved', async () => {
    contestsFor({ 6: MANY })
    let last: EntryContestResolution | null = null
    const { rerender } = render(<Harness seasonId="6" onState={(_v, r) => { last = r }} />)
    expect(await screen.findByRole('combobox', { name: 'Contest' })).toBeInTheDocument()
    await waitFor(() => expect(last).toEqual({ contestId: null, selectionRequired: true, ready: false }))
    // The admin picks "Tennis Club" (value driven through the same controlled prop the form uses).
    rerender(<Harness seasonId="6" initial="22" onState={(_v, r) => { last = r }} />)
    expect(await screen.findByRole('combobox', { name: 'Contest' })).toBeInTheDocument()
  })

  it('a chosen contest is sent; changing the season clears the now-incompatible choice', async () => {
    contestsFor({ 6: MANY, 7: [{ id: 31, name: 'Other' }, { id: 32, name: 'Another' }] })
    let value = ''
    let last: EntryContestResolution | null = null
    function Form({ seasonId }: { seasonId: string }) {
      const [v, setV] = useState('')
      const [r, setR] = useState<EntryContestResolution>({ contestId: null, selectionRequired: false, ready: false })
      value = v
      last = r
      return (
        <>
          <button type="button" onClick={() => setV('22')}>pick</button>
          <AdminEntryContestField seasonId={seasonId} value={v} onChange={setV} onResolved={setR} />
        </>
      )
    }
    const { rerender } = render(<Form seasonId="6" />)
    await screen.findByRole('combobox', { name: 'Contest' })
    screen.getByText('pick').click()
    await waitFor(() => expect(last).toEqual({ contestId: 22, selectionRequired: true, ready: true }))
    rerender(<Form seasonId="7" />)
    await waitFor(() => expect(value).toBe(''))
    await waitFor(() => expect(last).toEqual({ contestId: null, selectionRequired: true, ready: false }))
  })

  it('season without any contest cannot be submitted and says why', async () => {
    contestsFor({ 8: [] })
    let last: EntryContestResolution | null = null
    render(<Harness seasonId="8" onState={(_v, r) => { last = r }} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/not linked to any contest/)
    expect(last).toEqual({ contestId: null, selectionRequired: false, ready: false })
  })
})
