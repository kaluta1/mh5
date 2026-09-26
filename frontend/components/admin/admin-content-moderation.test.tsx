import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock }, apiService: {} }))

import AdminContentModeration from './admin-content-moderation'

const escalated = {
  id: 7, contestant_id: 70, contest_id: 1, entry_kind: 'PERSONAL_SUBMISSION', exposure_status: 'CHILD_SAFETY_ESCALATED',
  state: 'CHILD_SAFETY_ESCALATED', rating: null, proposed_rating: 'PROHIBITED', findings: ['CHILD_SEXUAL_CONTENT'],
  classifier_status: 'COMPLETED', subject_possibly_minor: true, child_safety_escalated: true, update_required: false,
  coverage: { TEXT_HARM: 'COMPLETED_FINDING' },
}

function setup(detail: Record<string, unknown>) {
  getMock.mockImplementation((url: string) =>
    Promise.resolve(url.endsWith('/queue') ? { status: 200, data: [escalated] } : { status: 200, data: detail }),
  )
}

describe('AdminContentModeration permissions', () => {
  beforeEach(() => { getMock.mockReset(); postMock.mockReset() })

  it('shows a moderator without child_safety_resolve the escalation but no resolution or approve control', async () => {
    setup({ ...escalated, can_moderate: true, can_resolve_child_safety: false, history: [] })
    render(<AdminContentModeration />)
    fireEvent.click(await screen.findByText('#7'))
    await screen.findByText(/Only authorized child-safety reviewers/)
    expect(screen.getAllByText(/Child safety review/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Confirm \(stays prohibited\)/)).toBeNull()
    expect(screen.queryByText(/No child-safety concern/)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
  })

  it('shows resolution controls only to an authorized child-safety resolver', async () => {
    setup({ ...escalated, can_moderate: false, can_resolve_child_safety: true, history: [] })
    render(<AdminContentModeration />)
    fireEvent.click(await screen.findByText('#7'))
    await waitFor(() => expect(screen.getByText(/Confirm \(stays prohibited\)/)).toBeInTheDocument())
    expect(screen.getByText(/No child-safety concern/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
  })

  it('never offers approval for prohibited content', async () => {
    const prohibited = { ...escalated, id: 8, state: 'PROHIBITED', child_safety_escalated: false, rating: 'PROHIBITED' }
    getMock.mockImplementation((url: string) =>
      Promise.resolve(url.endsWith('/queue') ? { status: 200, data: [prohibited] }
        : { status: 200, data: { ...prohibited, can_moderate: true, can_resolve_child_safety: false, history: [] } }),
    )
    render(<AdminContentModeration />)
    fireEvent.click(await screen.findByText('#8'))
    await screen.findByText(/cannot be approved/)
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
  })
})
