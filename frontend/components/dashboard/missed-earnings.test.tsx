import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: getMock }, apiService: {} }))

import { MissedEarnings } from './missed-earnings'

const MESSAGE =
  'Only KYC-verified members can earn commissions. These amounts were missed because your verification was not ' +
  'approved when the earning events occurred. Complete KYC to become eligible for future commissions.'

function page(kyc: string, items = 1) {
  return {
    total: items ? '10.00' : '0.00', currency: 'USD', count: items, skip: 0, limit: 20, kyc_status: kyc,
    kyc_url: '/dashboard/kyc', message: MESSAGE,
    items: items
      ? [{ id: 1, category: 'REFERRAL_COMMISSION', source: 'Membership', percentage: '20.00', amount: '10.00',
           currency: 'USD', kyc_status_at_event: 'pending', date: '2026-11-02T10:00:00', status: 'RECORDED',
           payable: false }]
      : [],
  }
}

function show() {
  render(<MissedEarnings endpoint="/api/v1/affiliates/commissions/missed"
                         title="Missed Commissions — KYC Verification Required" emptyText="You have no missed commissions." />)
}

describe('MissedEarnings', () => {
  beforeEach(() => getMock.mockReset())

  it('shows the total, each record and a link to complete KYC for an unverified member', async () => {
    getMock.mockResolvedValue({ data: page('pending') })
    show()
    expect(await screen.findByText('Missed Commissions — KYC Verification Required')).toBeTruthy()
    expect(screen.getByText(MESSAGE)).toBeTruthy()
    expect(screen.getAllByText('10.00 USD').length).toBeGreaterThan(0)
    expect(screen.getByText('Referral commission')).toBeTruthy()
    expect(screen.getByText(/not payable and are not part of your available balance/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /Complete KYC verification/ }).getAttribute('href')).toBe('/dashboard/kyc')
    expect(getMock).toHaveBeenCalledWith('/api/v1/affiliates/commissions/missed', { params: { skip: 0, limit: 20 } })
  })

  it('keeps the history visible after verification, without suggesting it can be reclaimed', async () => {
    getMock.mockResolvedValue({ data: page('approved') })
    show()
    expect(await screen.findByText('Referral commission')).toBeTruthy()
    expect(screen.getByText('Approved')).toBeTruthy()
    expect(screen.queryByRole('link', { name: /Complete KYC/ })).toBeNull()
    expect(screen.queryByText(/reclaim|claim back|recover/i)).toBeNull()
  })

  it('says so when nothing was missed', async () => {
    getMock.mockResolvedValue({ data: page('none', 0) })
    show()
    expect(await screen.findByText('You have no missed commissions.')).toBeTruthy()
  })
})
