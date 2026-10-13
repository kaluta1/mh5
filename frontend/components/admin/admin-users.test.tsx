import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

/**
 * A refused administrator action must look refused.
 *
 * The API client does not throw on a 4xx answer. Before this was checked, a
 * 403 from "make admin" showed "Admin rights updated", and any 403 signed the
 * administrator out. Both are tested here against the REAL response handling
 * (lib/http-error); only the network and the page chrome are replaced.
 */
const { getMock, putMock, deleteMock, addToast } = vi.hoisted(() => ({
  getMock: vi.fn(), putMock: vi.fn(), deleteMock: vi.fn(), addToast: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ default: { get: getMock, put: putMock, delete: deleteMock } }))
vi.mock('@/lib/cache-service', () => ({
  cacheService: { invalidate: vi.fn(), isEnabled: () => false, set: vi.fn(), clear: vi.fn() },
}))
vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: () => '', language: 'en' }) }))
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ addToast }) }))
// The row menu, opened: its items are plain buttons.
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <>{children}</>,
  DropdownMenuContent: ({ children }: any) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: any) => <button type="button" onClick={onClick}>{children}</button>,
  DropdownMenuSeparator: () => null,
}))

import AdminUsers from './admin-users'
import { throwIfApiError } from '@/lib/http-error'

const PASSWORD = 'synthetic-admin-password'
const TOKEN = 'synthetic-session-token'

const user = (over: Record<string, unknown> = {}) => ({
  id: 7, email: 'member@example.com', username: 'member', full_name: 'Synthetic Member', is_active: true,
  is_verified: true, is_admin: false, created_at: '2026-10-01T10:00:00', participations_count: 0, prizes_count: 0,
  contestants_count: 0, contests_participated: 0, ...over,
})

const refused = (status: number, code: string, message: string) =>
  ({ status, data: { detail: { code, message }, code: `HTTP_${status}` }, config: { url: '/api/v1/admin/users/7/role' } })

const successes = () => addToast.mock.calls.filter(([, kind]) => kind === 'success')
const errors = () => addToast.mock.calls.filter(([, kind]) => kind === 'error').map(([text]) => text)

function setup(rows: any[] = [user()]) {
  getMock.mockResolvedValue({ status: 200, data: rows })
}

describe('AdminUsers: a refused action looks refused', () => {
  const signedOut = vi.fn()

  beforeEach(() => {
    getMock.mockReset(); putMock.mockReset(); deleteMock.mockReset(); addToast.mockReset(); signedOut.mockReset()
    localStorage.setItem('access_token', TOKEN)
    window.addEventListener('auth:unauthorized', signedOut)
    return () => window.removeEventListener('auth:unauthorized', signedOut)
  })

  it('does not report a role change the server refused, keeps the dialog and the session', async () => {
    setup()
    putMock.mockResolvedValue(refused(403, 'PERMISSION_REQUIRED', 'The manage_administrators permission is required.'))
    render(<AdminUsers />)
    fireEvent.click(await screen.findByRole('button', { name: /Make admin/ }))
    const dialog = await screen.findByTestId('privileged-dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Confirm' })
    expect(confirm).toBeDisabled()                                   // never sent without the password
    expect(putMock).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    const loads = getMock.mock.calls.length
    fireEvent.click(confirm)

    await waitFor(() => expect(errors()).toEqual(['The manage_administrators permission is required.']))
    expect(putMock).toHaveBeenCalledWith('/api/v1/admin/users/7/role', { is_admin: true, current_password: PASSWORD })
    expect(successes()).toEqual([])                                  // "Admin rights updated" was shown here before
    expect(getMock.mock.calls.length).toBe(loads)                    // nothing reloaded as if it had changed
    expect(screen.getByTestId('privileged-dialog')).toBeInTheDocument()
    expect((within(dialog).getByLabelText('Your current password') as HTMLInputElement).value).toBe('')
    // B2: a refusal is not a sign-out.
    expect(localStorage.getItem('access_token')).toBe(TOKEN)
    expect(signedOut).not.toHaveBeenCalled()
  })

  it('treats a wrong password and a paused confirmation as errors, without signing out', async () => {
    setup()
    render(<AdminUsers />)
    fireEvent.click(await screen.findByRole('button', { name: /Make admin/ }))
    const dialog = await screen.findByTestId('privileged-dialog')
    for (const answer of [
      refused(403, 'REAUTH_REQUIRED', 'Enter your current password to confirm this action.'),
      refused(429, 'REAUTH_LOCKED', 'Too many incorrect passwords.'),
      refused(403, 'SELF_ACTION_FORBIDDEN', 'An administrator cannot perform this action on their own account.'),
      { status: 500, data: {}, config: { url: '/x' } },
    ]) {
      addToast.mockReset()
      putMock.mockResolvedValueOnce(answer)
      fireEvent.change(within(dialog).getByLabelText('Your current password'), { target: { value: 'a-guess' } })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }))
      await waitFor(() => expect(errors().length).toBe(1))
      expect(successes()).toEqual([])
    }
    expect(localStorage.getItem('access_token')).toBe(TOKEN)
    expect(signedOut).not.toHaveBeenCalled()
  })

  it('reports and reloads only after the server confirmed the change', async () => {
    setup()
    putMock.mockResolvedValue({ status: 200, data: { id: 7, is_admin: true } })
    render(<AdminUsers />)
    fireEvent.click(await screen.findByRole('button', { name: /Make admin/ }))
    const dialog = await screen.findByTestId('privileged-dialog')
    fireEvent.change(within(dialog).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    const loads = getMock.mock.calls.length
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(successes().length).toBe(1))
    await waitFor(() => expect(screen.queryByTestId('privileged-dialog')).toBeNull())
    expect(getMock.mock.calls.length).toBe(loads + 1)
    expect(errors()).toEqual([])
  })

  it('asks for the password to switch an administrator account, and not for an ordinary member', async () => {
    setup([user({ id: 7 }), user({ id: 8, email: 'admin@example.com', username: 'other', is_admin: true })])
    putMock.mockResolvedValue(refused(403, 'PERMISSION_REQUIRED', 'The manage_administrators permission is required.'))
    render(<AdminUsers />)
    const buttons = await screen.findAllByRole('button', { name: /Deactivate/ })
    fireEvent.click(buttons[1])                                      // the administrator's row
    expect(await screen.findByTestId('privileged-dialog')).toBeInTheDocument()
    expect(putMock).not.toHaveBeenCalled()
    fireEvent.click(within(screen.getByTestId('privileged-dialog')).getByRole('button', { name: 'Cancel' }))

    addToast.mockReset()
    fireEvent.click(buttons[0])                                      // an ordinary member: sent at once ...
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/admin/users/7/status', { is_active: false }))
    await waitFor(() => expect(errors()).toEqual(['The manage_administrators permission is required.']))
    expect(successes()).toEqual([])                                  // ... and a refusal of it is shown as one
  })

  it('does not report an identity verification or a deletion the server refused', async () => {
    setup()
    putMock.mockResolvedValue(refused(403, 'SELF_ACTION_FORBIDDEN', 'An administrator cannot perform this action on their own account.'))
    deleteMock.mockResolvedValue(refused(409, 'ADMIN_ACCOUNT_PROTECTED', 'An administrator account cannot be deleted.'))
    render(<AdminUsers />)
    fireEvent.click((await screen.findAllByRole('button', { name: /KYC/ }))[0])
    await waitFor(() => expect(errors()).toEqual(['An administrator cannot perform this action on their own account.']))
    expect(successes()).toEqual([])
  })
})

describe('the session and a refusal (lib/http-error)', () => {
  const signedOut = vi.fn()

  beforeEach(() => {
    signedOut.mockReset()
    localStorage.setItem('access_token', TOKEN)
    window.addEventListener('auth:unauthorized', signedOut)
    return () => window.removeEventListener('auth:unauthorized', signedOut)
  })

  it('ends the session on 401 and only on 401', () => {
    const answer = (status: number, url = '/api/v1/admin/users') => ({ status, data: { detail: 'x' }, config: { url } }) as any
    for (const status of [400, 403, 404, 409, 422, 429]) {
      expect(() => throwIfApiError(answer(status))).toThrow()
      expect(localStorage.getItem('access_token')).toBe(TOKEN)
    }
    expect(signedOut).not.toHaveBeenCalled()
    expect(() => throwIfApiError(answer(401, '/api/v1/auth/login'))).toThrow()   // a failed sign-in attempt
    expect(localStorage.getItem('access_token')).toBe(TOKEN)
    expect(() => throwIfApiError(answer(401))).toThrow()                         // the session really is over
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(signedOut).toHaveBeenCalledTimes(1)
  })
})
