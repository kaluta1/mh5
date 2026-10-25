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
  DropdownMenuItem: ({ children, onClick, disabled, 'data-testid': testId }: any) => (
    <button type="button" onClick={onClick} disabled={disabled} data-testid={testId}>{children}</button>),
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

  it('offers no way to verify or revoke an identity by hand (KYC is decided by the provider only)', async () => {
    setup()
    render(<AdminUsers />)
    await screen.findAllByRole('button')
    expect(screen.queryByText('Verify KYC')).toBeNull()
    expect(screen.queryByText('Revoke KYC')).toBeNull()
    expect(putMock).not.toHaveBeenCalledWith(expect.stringMatching(/\/kyc\/(verify|unverify)$/))
    expect(successes()).toEqual([])
  })
})

describe('AdminUsers: the Super Admin role', () => {
  beforeEach(() => {
    getMock.mockReset(); putMock.mockReset(); deleteMock.mockReset(); addToast.mockReset()
    localStorage.setItem('access_token', TOKEN)
  })

  const rows = [user({ id: 7 }), user({ id: 8, email: 'admin@example.com', username: 'admin', is_admin: true }),
    user({ id: 19, email: 'boss@example.com', username: 'boss', is_admin: true, is_super_admin: true })]

  const ROLES = [{ id: 3, name: 'finance_manager_m' }, { id: 4, name: 'moderator' }, { id: 5, name: 'user' }]

  function serve(canManage: boolean, previous: { id: number; name: string } | null = { id: 3, name: 'finance_manager_m' },
    seats: { seats_used: number; max_super_admins: number; can_grant: boolean } | null = null) {
    getMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/admin/super-admins') {
        return { status: 200, data: { can_manage: canManage, super_admins: [{ id: 19 }], ...(seats ?? {}) } }
      }
      if (url.endsWith('/super-admin/demotion-options')) {
        return { status: 200, data: { previous_role: previous, previous_role_valid: previous !== null, roles: ROLES } }
      }
      return { status: 200, data: rows }
    })
  }

  async function openRevoke(id = 19) {
    fireEvent.click(await screen.findByTestId(`super-admin-toggle-${id}`))
    const dialog = await screen.findByTestId('privileged-dialog')
    await waitFor(() => expect(within(dialog).getByTestId('replacement-role')).not.toBeDisabled())
    fireEvent.change(within(dialog).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    return dialog
  }

  it('shows who is a Super Admin, and offers the role only to a Super Admin, only for administrators', async () => {
    serve(true)
    render(<AdminUsers />)
    expect(await screen.findByTestId('super-admin-badge-19')).toBeInTheDocument()
    expect(screen.queryByTestId('super-admin-badge-8')).toBeNull()
    await waitFor(() => expect(screen.getByTestId('super-admin-toggle-8')).toHaveTextContent('Make Super Admin'))
    expect(screen.getByTestId('super-admin-toggle-19')).toHaveTextContent('Revoke Super Admin')
    expect(screen.queryByTestId('super-admin-toggle-7')).toBeNull()                 // an ordinary member
    // "Remove admin" is not offered on a Super Admin (the server refuses it until the role is revoked).
    expect(screen.getAllByRole('button', { name: /Remove admin/ })).toHaveLength(1)
  })

  it('shows the seats taken and offers no grant once all 5 are taken, while revoking stays possible', async () => {
    serve(true, undefined, { seats_used: 5, max_super_admins: 5, can_grant: false })
    render(<AdminUsers />)
    expect(await screen.findByTestId('super-admin-seats')).toHaveTextContent('Super Admins: 5 of 5')
    const grant = await screen.findByTestId('super-admin-toggle-8')
    expect(grant).toBeDisabled()
    expect(grant).toHaveTextContent('Make Super Admin (limit of 5 reached)')
    fireEvent.click(grant)
    expect(screen.queryByTestId('privileged-dialog')).toBeNull()
    expect(screen.getByTestId('super-admin-toggle-19')).not.toBeDisabled()
    expect(putMock).not.toHaveBeenCalled()
  })

  it('offers the grant while a seat is free', async () => {
    serve(true, undefined, { seats_used: 4, max_super_admins: 5, can_grant: true })
    render(<AdminUsers />)
    expect(await screen.findByTestId('super-admin-seats')).toHaveTextContent('Super Admins: 4 of 5')
    const grant = await screen.findByTestId('super-admin-toggle-8')
    expect(grant).not.toBeDisabled()
    expect(grant).toHaveTextContent(/^Make Super Admin$/)
  })

  it('does not offer the role to an administrator who is not a Super Admin', async () => {
    serve(false)
    render(<AdminUsers />)
    expect(await screen.findByTestId('super-admin-badge-19')).toBeInTheDocument()
    expect(screen.queryByTestId('super-admin-toggle-8')).toBeNull()
    expect(screen.queryByTestId('super-admin-toggle-19')).toBeNull()
    expect(screen.queryByTestId('super-admin-seats')).toBeNull()
  })

  it('sends the password with the grant and shows a refusal as a refusal', async () => {
    serve(true)
    putMock.mockResolvedValueOnce(refused(409, 'LAST_SUPER_ADMIN', 'The last active Super Admin cannot be removed.'))
    render(<AdminUsers />)
    fireEvent.click(await screen.findByTestId('super-admin-toggle-19'))
    const dialog = await screen.findByTestId('privileged-dialog')
    expect(dialog).toHaveTextContent('Revoke Super Admin')
    expect(within(dialog).getByRole('button', { name: 'Confirm' })).toBeDisabled()
    await waitFor(() => expect(within(dialog).getByTestId('replacement-role')).not.toBeDisabled())
    fireEvent.change(within(dialog).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(errors()).toEqual(['The last active Super Admin cannot be removed.']))
    expect(putMock).toHaveBeenCalledWith('/api/v1/admin/users/19/super-admin',
      { is_super_admin: false, current_password: PASSWORD })
    expect(successes()).toEqual([])

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    putMock.mockResolvedValueOnce({ status: 200, data: { id: 8, is_super_admin: true } })
    fireEvent.click(screen.getByTestId('super-admin-toggle-8'))
    const again = await screen.findByTestId('privileged-dialog')
    fireEvent.change(within(again).getByLabelText('Your current password'), { target: { value: PASSWORD } })
    fireEvent.click(within(again).getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(successes().length).toBe(1))
    expect(putMock).toHaveBeenLastCalledWith('/api/v1/admin/users/8/super-admin',
      { is_super_admin: true, current_password: PASSWORD })
    expect(getMock).not.toHaveBeenCalledWith('/api/v1/admin/users/8/super-admin/demotion-options')
  })

  it('restores the previous role by default when revoking', async () => {
    serve(true)
    putMock.mockResolvedValueOnce({ status: 200, data: { id: 19, is_super_admin: false } })
    render(<AdminUsers />)
    const dialog = await openRevoke()
    const select = within(dialog).getByTestId('replacement-role') as HTMLSelectElement
    expect(select.value).toBe('')
    expect(select.options[0].textContent).toContain('finance_manager_m')
    // The previous role is offered once, as the restore option.
    expect(Array.from(select.options).filter((o) => o.textContent?.includes('finance_manager_m'))).toHaveLength(1)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(successes().length).toBe(1))
    expect(putMock).toHaveBeenCalledWith('/api/v1/admin/users/19/super-admin',
      { is_super_admin: false, current_password: PASSWORD })                 // no replacement: the server restores
  })

  it('sends the role the Super Admin chose instead', async () => {
    serve(true)
    putMock.mockResolvedValueOnce({ status: 200, data: { id: 19, is_super_admin: false } })
    render(<AdminUsers />)
    const dialog = await openRevoke()
    fireEvent.change(within(dialog).getByTestId('replacement-role'), { target: { value: '4' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(successes().length).toBe(1))
    expect(putMock).toHaveBeenCalledWith('/api/v1/admin/users/19/super-admin',
      { is_super_admin: false, current_password: PASSWORD, replacement_role_id: 4 })
  })

  it('cannot revoke without a role to go to when there is no previous role', async () => {
    serve(true, null)
    putMock.mockResolvedValueOnce(refused(422, 'REPLACEMENT_ROLE_GRANTS_SUPER_ADMIN',
      'The chosen role is, or inherits from, the Super Admin role.'))
    render(<AdminUsers />)
    const dialog = await openRevoke()
    const confirm = within(dialog).getByRole('button', { name: 'Confirm' })
    expect(confirm).toBeDisabled()                                          // the password alone is not enough
    expect(putMock).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByTestId('replacement-role'), { target: { value: '5' } })
    expect(confirm).not.toBeDisabled()
    fireEvent.click(confirm)
    // Whatever the page offered, the server decides; its refusal is shown as one.
    await waitFor(() => expect(errors()).toEqual(['The chosen role is, or inherits from, the Super Admin role.']))
    expect(successes()).toEqual([])
    expect(putMock).toHaveBeenCalledWith('/api/v1/admin/users/19/super-admin',
      { is_super_admin: false, current_password: PASSWORD, replacement_role_id: 5 })
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
