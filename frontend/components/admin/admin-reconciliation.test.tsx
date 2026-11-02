import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: getMock, post: postMock }, apiService: {} }))

import AdminReconciliation from './admin-reconciliation'
import { AnnualAdsHistory } from '@/components/dashboard/annual-ads-history'

const DATA: Record<string, unknown> = {
  '/annual-ads': { payments: 2, gross: '200.00', sponsor_commission_total: '20.00', by_commission_status: { RECORDED: 1 },
    issues: [{ type: 'REFUND_FINANCE_REVIEW', payment_id: 4, expected: 'finance decision', actual: 'FINANCE_REVIEW',
      owner_approval: true }] },
  '/referral-pool': { counts: { units_by_status: { ACTIVE: 1 }, holders_with_active_units: 1, assignments: 0 },
    fingerprint: 'abc123', issues: [] },
  '/dsm': { source: 'legacy_import.dsm_members', counts: { SAFE_RESTORATION_CANDIDATE: 8, CONFLICTING_SPONSOR: 110 },
    referral_pool_eligibility: { note: 'DSM membership alone never makes a member eligible' } },
  '/dsm/candidates': { candidates: [{ user_id: 150, dsm_id: 9, dsm_sponsor_user_id: 3670 }] },
}

describe('AdminReconciliation', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    getMock.mockImplementation((url: string) =>
      Promise.resolve({ status: 200, data: DATA[url.replace('/api/v1/admin/reconciliation', '')] }))
  })

  it('shows the three reports with their issues and the DSM classes', async () => {
    render(<AdminReconciliation />)
    expect(await screen.findByTestId('rec-annual')).toHaveTextContent('REFUND_FINANCE_REVIEW')
    expect(screen.getByTestId('rec-annual')).toHaveTextContent('owner approval needed')
    expect(screen.getByTestId('rec-pool')).toHaveTextContent('No issues.')
    expect(screen.getByTestId('rec-dsm')).toHaveTextContent('safe restoration candidate: 8')
  })

  it('restores one sponsor only with evidence and the password', async () => {
    postMock.mockResolvedValue({ status: 200, data: { status: 'APPLIED' } })
    render(<AdminReconciliation />)
    const button = await screen.findByText('Restore sponsor')
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Evidence for member 150'), { target: { value: 'DSM record 9 verified' } })
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'pw' } })
    fireEvent.click(button)
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/api/v1/admin/reconciliation/dsm/restorations',
      { user_id: 150, note: 'DSM record 9 verified', current_password: 'pw' }))
  })

  it('explains when DSM access is not permitted', async () => {
    getMock.mockImplementation((url: string) => url.includes('/dsm')
      ? Promise.resolve({ status: 403, data: {} })
      : Promise.resolve({ status: 200, data: DATA[url.replace('/api/v1/admin/reconciliation', '')] }))
    render(<AdminReconciliation />)
    expect(await screen.findByText('A Super Admin or manage_administrators is required.')).toBeInTheDocument()
  })
})

describe('AnnualAdsHistory', () => {
  it('shows sponsor commissions with rate and status, hidden when empty', async () => {
    getMock.mockReset()
    getMock.mockResolvedValueOnce({ status: 200, data: { purchases: [], sponsor_commissions: [
      { id: 1, date: '2026-11-03T10:00:00', gross_amount: '100.00', rate_percent: '20.0000', amount: '20.00',
        status: 'RECORDED', commission_status: 'APPROVED', refund_status: null },
      { id: 2, date: '2026-11-03T11:00:00', gross_amount: '50.00', rate_percent: '20.0000', amount: '10.00',
        status: 'MISSED_KYC', commission_status: null, refund_status: null }] } })
    render(<AnnualAdsHistory />)
    const box = await screen.findByTestId('annual-ads-history')
    expect(box).toHaveTextContent('20%')
    expect(box).toHaveTextContent('Missed — KYC not approved (not payable)')
  })

  it('renders nothing without history', async () => {
    getMock.mockReset()
    getMock.mockResolvedValue({ status: 200, data: { purchases: [], sponsor_commissions: [] } })
    const { container } = render(<AnnualAdsHistory />)
    await waitFor(() => expect(getMock).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
