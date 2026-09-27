import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock, postMock, deleteMock, toast } = vi.hoisted(() => ({
  getMock: vi.fn(), postMock: vi.fn(), deleteMock: vi.fn(), toast: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock, delete: deleteMock }, apiService: {} }))
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ addToast: toast }) }))

import { ThreadSafetyControls } from './thread-safety-controls'
import { INTERACTION_UNAVAILABLE_MESSAGE, interactionErrorMessage } from '@/services/interaction-service'

describe('Phase 9 messaging safety controls', () => {
  beforeEach(() => {
    getMock.mockReset(); postMock.mockReset(); deleteMock.mockReset(); toast.mockReset()
  })

  it('maps a blocked interaction to one generic message and never renders a raw object', () => {
    const blocked = { response: { status: 403, data: { detail: { code: 'INTERACTION_UNAVAILABLE', message: 'x' } } } }
    expect(interactionErrorMessage(blocked)).toBe(INTERACTION_UNAVAILABLE_MESSAGE)
    const text = { response: { status: 422, data: { detail: { code: 'CONTENT_NOT_ALLOWED', message: "For safety, don't share contact details" } } } }
    expect(interactionErrorMessage(text)).toMatch(/don't share contact details/)
    expect(interactionErrorMessage({}, 'fallback')).toBe('fallback')
  })

  it('reports the backend contact decision and fails closed if it cannot be loaded', async () => {
    const onStatus = vi.fn()
    getMock.mockResolvedValue({ status: 200, data: { user_id: 5, can_message: false, blocked_by_me: false } })
    render(<ThreadSafetyControls partnerId={5} onStatus={onStatus} />)
    await waitFor(() => expect(onStatus).toHaveBeenCalledWith({ user_id: 5, can_message: false, blocked_by_me: false }))
    onStatus.mockReset()
    getMock.mockRejectedValue(new Error('down'))
    render(<ThreadSafetyControls partnerId={6} onStatus={onStatus} />)
    await waitFor(() => expect(onStatus).toHaveBeenCalledWith({ user_id: 6, can_message: false, blocked_by_me: false }))
  })

  it('blocks, unblocks and reports through the backend', async () => {
    getMock.mockResolvedValue({ status: 200, data: { user_id: 7, can_message: true, blocked_by_me: false } })
    postMock.mockResolvedValue({ status: 200, data: {} })
    render(<ThreadSafetyControls partnerId={7} onStatus={() => undefined} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Block' }))
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/interactions/blocks/7'))
    fireEvent.change(screen.getByLabelText('Report reason'), { target: { value: 'CHILD_SAFETY' } })
    fireEvent.click(screen.getByRole('button', { name: 'Report' }))
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/interactions/reports',
      { target_type: 'user', target_id: 7, reason: 'CHILD_SAFETY' }))
    getMock.mockResolvedValue({ status: 200, data: { user_id: 7, can_message: false, blocked_by_me: true } })
    deleteMock.mockResolvedValue({ status: 200, data: {} })
    fireEvent.click(screen.getByRole('button', { name: 'Block' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Unblock' }))
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('/api/v1/interactions/blocks/7'))
  })
})
