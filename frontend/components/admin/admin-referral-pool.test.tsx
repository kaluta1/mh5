import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
vi.mock('@/lib/api', () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    put: (...a: unknown[]) => put(...a),
  },
}))

import AdminReferralPool, { referralTypeLabel, refundStatusText } from './admin-referral-pool'

function overview(given: { finance: boolean; kyc: boolean } = { finance: false, kyc: false }) {
  const permissions = { ...given, operations: given.finance || given.kyc }
  return {
    features: { multiunit_sales_enabled: false, allocation_enabled: false, worker_enabled: false, activation_available: false },
    limits: { max_units_per_purchase: null, max_units_per_member: null, max_active_units: null },
    units: { ACTIVE: 2 }, eligible_units: 2, units_waiting_for_next_round: 2, unit_holders: 1,
    purchases: { PAID: 1 }, rounds: {}, current_round: null, queue: {}, events: {}, refunds: {},
    risk_reviews: { open: 0, open_blocking: 0 }, round_assignments: 0, permissions,
    amounts: permissions.finance ? { paid: '200.00', refunded: '0.00', currency: 'USD' } : null,
  }
}

const page = (items: unknown[], total = items.length) => ({ items, page: 1, page_size: 25, total })

function serve(routes: Record<string, unknown>) {
  get.mockImplementation((url: string) => {
    const path = url.replace('/api/v1/admin/referral-pool', '')
    if (path in routes) return Promise.resolve({ status: 200, data: routes[path] })
    return Promise.reject({ response: { status: 404, data: { detail: 'not mocked' } } })
  })
}

const calledPaths = () => get.mock.calls.map((c) => String(c[0]).replace('/api/v1/admin/referral-pool', ''))

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  put.mockReset()
})

describe('AdminReferralPool', () => {
  it('shows every feature switch OFF, read-only, with no activation control', async () => {
    serve({ '/overview': overview() })
    render(<AdminReferralPool />)
    const status = await screen.findByTestId('feature-status')
    expect(status).toHaveTextContent('multiunit_sales_enabled OFF')
    expect(status).toHaveTextContent('allocation_enabled OFF')
    expect(status).toHaveTextContent('REFERRAL_POOL_WORKER_ENABLED OFF')
    expect(screen.queryByRole('button', { name: /enable|activate|turn on|start|launch/i })).not.toBeInTheDocument()
    expect(screen.getByText(/Amounts are shown to administrators with a finance permission/)).toBeInTheDocument()
  })

  it('hides financial, operations and sponsor views without the permission and does not request them', async () => {
    serve({ '/overview': overview() })
    render(<AdminReferralPool />)
    await screen.findByTestId('feature-status')
    for (const tab of ['Purchases', 'Units', 'Refunds', 'Reconciliation']) {
      fireEvent.click(screen.getByRole('tab', { name: tab }))
      expect(screen.getByText(/requires the process_cashouts or manage_payment_settings permission/)).toBeInTheDocument()
    }
    fireEvent.click(screen.getByRole('tab', { name: 'Risk reviews' }))
    expect(screen.getByText(/requires the manage_kyc_settings permission/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Sponsors' }))
    expect(screen.getByText(/requires the manage_kyc_settings permission/)).toBeInTheDocument()
    for (const tab of ['Rounds', 'Queue', 'Events']) {
      fireEvent.click(screen.getByRole('tab', { name: tab }))
      expect(screen.getByText(/requires the process_cashouts, manage_payment_settings or manage_kyc_settings permission/)).toBeInTheDocument()
    }
    expect(calledPaths().filter((p) => p !== '/overview')).toEqual([])
  })

  it('pages purchases from the server and shows payment status', async () => {
    serve({
      '/overview': overview({ finance: true, kyc: false }),
      '/purchases': page([{ id: 4, user_id: 9, username: 'm9', quantity: 2, total_amount: '200.00', status: 'PAID',
        payment: { deposit_id: 3, status: 'validated' }, units: { ACTIVE: 2 } }], 60),
    })
    render(<AdminReferralPool />)
    expect(await screen.findByTestId('overview-amounts')).toHaveTextContent('Paid $200.00')
    fireEvent.click(screen.getByRole('tab', { name: 'Purchases' }))
    await waitFor(() => expect(screen.getByText('m9')).toBeInTheDocument())
    expect(screen.getByText(/validated/)).toBeInTheDocument()
    expect(screen.getByText(/Page 1 \/ 3 · 60 rows/)).toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/api/v1/admin/referral-pool/purchases', { params: { page: 1, page_size: 25, status: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/api/v1/admin/referral-pool/purchases', { params: { page: 2, page_size: 25, status: '' } }),
    )
  })

  it('labels manual refunds as administrator claims and decides with a note and password', async () => {
    serve({
      '/overview': overview({ finance: true, kyc: false }),
      '/refunds': page([
        { id: 1, purchase_id: 4, quantity: 1, amount: '100.00', provider_reference: 'np-1', status: 'PROPOSED',
          evidence_label: 'Administrator-entered claim: the provider reference is not independently verified', proposed_by: 2 },
        { id: 2, purchase_id: 5, quantity: 1, amount: '100.00', provider_reference: 'np-2', status: 'APPROVED',
          evidence_label: 'Administrator-entered claim: the provider reference is not independently verified', proposed_by: 2, decided_by: 3 },
      ]),
    })
    post.mockResolvedValue({ status: 200, data: {} })
    render(<AdminReferralPool />)
    await screen.findByTestId('feature-status')
    fireEvent.click(screen.getByRole('tab', { name: 'Refunds' }))
    await waitFor(() => expect(screen.getByText('np-2')).toBeInTheDocument())
    expect(screen.getByText('Approved by a second administrator (claim, not provider-verified)')).toBeInTheDocument()
    expect(screen.queryByText(/^Confirmed$/i)).not.toBeInTheDocument()
    expect(screen.getAllByText(/not independently verified/)).toHaveLength(2)
    const approve = screen.getByRole('button', { name: 'Approve' })
    expect(approve).toBeDisabled()                                                // note and password first
    fireEvent.change(screen.getByLabelText('Decision note'), { target: { value: 'Checked at the provider' } })
    fireEvent.change(screen.getByLabelText('Password to decide'), { target: { value: 'pw' } })
    fireEvent.click(approve)
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/api/v1/admin/referral-pool/refunds/1/decision', { approve: true, note: 'Checked at the provider', password: 'pw' }),
    )
  })

  it('proposes a manual refund priced at $100 a unit and needs the password', async () => {
    serve({ '/overview': overview({ finance: true, kyc: false }), '/refunds': page([]) })
    post.mockResolvedValue({ status: 200, data: {} })
    render(<AdminReferralPool />)
    await screen.findByTestId('feature-status')
    fireEvent.click(screen.getByRole('tab', { name: 'Refunds' }))
    fireEvent.change(screen.getByLabelText('Purchase id'), { target: { value: '4' } })
    fireEvent.change(screen.getByLabelText('Units'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Provider reference'), { target: { value: 'np-9' } })
    fireEvent.change(screen.getByLabelText('Evidence checked'), { target: { value: 'Seen in the provider dashboard' } })
    expect(screen.getByRole('button', { name: 'Propose refund' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Password to propose'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Propose refund' }))
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/api/v1/admin/referral-pool/refunds', {
        purchase_id: 4, quantity: 2, amount: '200.00', provider_reference: 'np-9',
        evidence_note: 'Seen in the provider dashboard', password: 'pw',
      }),
    )
  })

  it('shows anti-abuse cases to manage_kyc_settings holders with ids and a fingerprint only', async () => {
    serve({
      '/overview': overview({ finance: false, kyc: true }),
      '/risk-reviews': page([{ id: 5, user_id: 11, signal: 'DUPLICATE_KYC_IDENTITY', blocking: true, status: 'OPEN',
        related_user_ids: [12], evidence_fingerprint: 'abababababab' }]),
    })
    render(<AdminReferralPool />)
    await screen.findByTestId('feature-status')
    fireEvent.click(screen.getByRole('tab', { name: 'Risk reviews' }))
    await waitFor(() => expect(screen.getByText('DUPLICATE_KYC_IDENTITY')).toBeInTheDocument())
    expect(screen.getByText('abababababab')).toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/api/v1/admin/referral-pool/risk-reviews', { params: { page: 1, page_size: 25, status: 'OPEN' } })
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument()
  })

  it('shows empty limits as Unlimited', async () => {
    serve({ '/overview': overview({ finance: true, kyc: false }) })
    render(<AdminReferralPool />)
    await screen.findByTestId('feature-status')
    expect(screen.getByText('Optional unit limits (empty = Unlimited)')).toBeInTheDocument()
    for (const k of ['max_units_per_purchase', 'max_units_per_member', 'max_active_units']) {
      expect(screen.getByTestId(`limit-${k}`)).toHaveTextContent('Unlimited')
      expect(screen.getByLabelText(k)).toHaveAttribute('placeholder', 'Unlimited')
    }
    fireEvent.change(screen.getByLabelText('max_units_per_member'), { target: { value: '20' } })
    expect(screen.getByTestId('limit-max_units_per_member')).toHaveTextContent('At most 20')
  })

  it('lists sponsors in three columns with profile links and readable referral types', async () => {
    serve({
      '/overview': overview({ finance: false, kyc: true }),
      '/sponsors': {
        ...page([
          { user_id: 11, username: 'alice', sponsor_id: 7, sponsor_username: 'bob', sponsor_source: 'PERSONAL_REFERRAL' },
          { user_id: 12, username: 'carol', sponsor_id: 7, sponsor_username: 'bob', sponsor_source: null },
          { user_id: 13, username: null, sponsor_id: 99, sponsor_username: null, sponsor_source: 'JOIN_CODE' },
        ], 3),
        page_size: 50,
      },
      '/invalid-sponsors': { items: [{ user_id: 14, username: 'dave', sponsor_id: 8, sponsor_username: 'erin', source: 'PERSONAL_REFERRAL' }], page: 1, page_size: 50, checked_total: 6 },
    })
    render(<AdminReferralPool />)
    await screen.findByTestId('feature-status')
    fireEvent.click(screen.getByRole('tab', { name: 'Sponsors' }))
    await screen.findByText('alice')
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['User', 'Sponsor', 'Referral Type'])
    expect(screen.getByRole('link', { name: 'alice' })).toHaveAttribute('href', '/dashboard/users/11')
    expect(screen.getAllByRole('link', { name: 'bob' })[0]).toHaveAttribute('href', '/dashboard/users/7')
    expect(screen.getByText('Personal Referral')).toBeInTheDocument()
    expect(screen.getByText('Not recorded (legacy)')).toBeInTheDocument()
    expect(screen.getByText('Join Code')).toBeInTheDocument()
    expect(screen.getByText('Unknown account (#13)')).toBeInTheDocument()
    expect(screen.getByText('Unknown account (#99)')).toBeInTheDocument()
    expect(screen.queryByText('user_id')).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/api/v1/admin/referral-pool/sponsors', { params: { page: 1, page_size: 50 } })
    fireEvent.change(screen.getByLabelText('Sponsors view'), { target: { value: 'invalid' } })
    expect(await screen.findByRole('link', { name: 'dave' })).toHaveAttribute('href', '/dashboard/users/14')
    expect(screen.getByRole('link', { name: 'erin' })).toHaveAttribute('href', '/dashboard/users/8')
    expect(screen.getByText(/of 6/)).toBeInTheDocument()
    expect(put).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })

  it('saves optional limits with the password (empty means no limit)', async () => {
    serve({ '/overview': overview({ finance: true, kyc: false }) })
    put.mockResolvedValue({ status: 200, data: {} })
    render(<AdminReferralPool />)
    await screen.findByTestId('feature-status')
    fireEvent.change(screen.getByLabelText('max_units_per_member'), { target: { value: '20' } })
    fireEvent.change(screen.getByLabelText('Password for limits'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save limits' }))
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith('/api/v1/admin/referral-pool/limits', {
        password: 'pw', max_units_per_purchase: null, max_units_per_member: 20, max_active_units: null,
      }),
    )
  })
})

describe('referralTypeLabel', () => {
  it('turns stored sources into readable labels without changing them', () => {
    expect(referralTypeLabel('PERSONAL_REFERRAL')).toBe('Personal Referral')
    expect(referralTypeLabel('JOIN_CODE')).toBe('Join Code')
    expect(referralTypeLabel('REFERRAL_POOL')).toBe('Referral Pool')
    expect(referralTypeLabel('NONE')).toBe('None')
    expect(referralTypeLabel(null)).toBe('Not recorded (legacy)')
    expect(referralTypeLabel('')).toBe('Not recorded (legacy)')
    expect(referralTypeLabel('ADMIN_ASSIGNED')).toBe('Admin Assigned')
  })
})

describe('refundStatusText', () => {
  it('never calls an approved administrator claim confirmed', () => {
    expect(refundStatusText({ status: 'APPROVED' })).toMatch(/not provider-verified/)
    expect(refundStatusText({ status: 'APPROVED' })).not.toMatch(/confirmed/i)
    expect(refundStatusText({ status: 'PROPOSED' })).toBe('Awaiting a second administrator')
  })
})
